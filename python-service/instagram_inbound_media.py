"""Private, bounded Instagram image/audio intake."""

import base64
import hashlib
import http.client
import ipaddress
import os
import re
import socket
import ssl
import tempfile
import time
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

ROOT = Path('/run/socialmei/private/inbound-media-v1/instagram')
MAX_BYTES = 10 * 1024 * 1024
MEDIA = {
    'image/jpeg': ('image', '.jpg'), 'image/png': ('image', '.png'),
    'image/webp': ('image', '.webp'), 'audio/ogg': ('audio', '.ogg'),
    'audio/mp4': ('audio', '.m4a'), 'audio/mpeg': ('audio', '.mp3'),
    'audio/wav': ('audio', '.wav'),
}


@dataclass(frozen=True)
class Attachment:
    position: int
    kind: str
    url: str = field(repr=False)


def enabled():
    return os.getenv('SOCIALMEI_INSTAGRAM_INBOUND_MEDIA_ENABLED') == 'YES'


def cdn_url(value):
    if (not isinstance(value, str) or len(value) > 4096 or not value.isascii()
            or any(ord(char) <= 32 or ord(char) == 127 for char in value) or '\\' in value):
        raise ValueError('Invalid attachment URL')
    url = urlsplit(value)
    host = url.hostname or ''
    allowed = host.endswith(('.cdninstagram.com', '.fbcdn.net')) or (
        host == 'lookaside.fbsbx.com' and url.path.startswith('/ig_messaging_cdn/'))
    if (url.scheme != 'https' or not allowed or url.netloc.lower() not in {host, host+':443'}
            or url.fragment or not url.path.startswith('/')):
        raise ValueError('Invalid attachment URL')
    return url


def supported_attachments(message):
    entries = message.get('attachments')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 4 or message.get('is_deleted'):
        return ()
    result = []
    for position, entry in enumerate(entries):
        if not isinstance(entry, dict) or entry.get('type') not in ('image', 'audio'):
            continue
        payload = entry.get('payload')
        if not isinstance(payload, dict):
            continue
        try:
            cdn_url(payload.get('url'))
        except ValueError:
            continue
        result.append(Attachment(position, entry['type'], payload['url']))
    return tuple(result)


def enqueue(conn, workspace, event, message_id):
    for attachment in event.attachments:
        conn.execute(
            'INSERT INTO socialmei.ig_inbound_media(workspace_id,external_account_id,event_key,message_id,position,kind,source_url) '
            'VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,message_id,position) DO NOTHING',
            (workspace, event.account_id, event.event_key, message_id, attachment.position, attachment.kind, attachment.url),
        )


def public_ip(host):
    addresses = [ipaddress.ip_address(row[4][0]) for row in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
    def safe(address):
        address = getattr(address, 'ipv4_mapped', None) or address
        return address.is_global and not address.is_multicast and not address.is_reserved
    if not addresses or not all(map(safe, addresses)):
        raise ValueError('Invalid attachment address')
    return str(addresses[0])


class PinnedHTTPS(http.client.HTTPSConnection):
    def connect(self):
        sock = socket.create_connection((public_ip(self.host), 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def matches_type(content, mime):
    if MEDIA[mime][0] == 'image':
        try:
            with Image.open(BytesIO(content)) as image:
                if image.get_format_mimetype() != mime or image.width * image.height > 16000000:
                    return False
                image.verify()
                return True
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
            return False
    return {
        'audio/ogg': content.startswith(b'OggS'),
        'audio/mp4': content[4:8] == b'ftyp',
        'audio/mpeg': content.startswith(b'ID3') or (len(content) > 4 and content[0] == 255 and content[1] & 224 == 224),
        'audio/wav': content.startswith(b'RIFF') and content[8:12] == b'WAVE',
    }[mime]


def download(value, kind):
    url = cdn_url(value)
    target = url.path + ('?' + url.query if url.query else '')
    deadline = time.monotonic() + 25
    connection = PinnedHTTPS(url.hostname, timeout=5, context=ssl.create_default_context())
    try:
        connection.request('GET', target, headers={'Accept-Encoding': 'identity'})
        with connection.getresponse() as response:
            if response.status in {408, 429} or response.status >= 500:
                raise OSError('CDN temporarily unavailable')
            mime = response.getheader('Content-Type', '').split(';')[0].strip().lower()
            length = response.getheader('Content-Length')
            if (response.status != 200 or mime not in MEDIA or MEDIA[mime][0] != kind
                    or response.getheader('Content-Encoding', 'identity') != 'identity'
                    or (length is not None and (not length.isdecimal() or not 0 < int(length) <= MAX_BYTES))):
                raise ValueError('Invalid attachment response')
            content = bytearray()
            while chunk := response.read1(min(65536, MAX_BYTES + 1 - len(content))):
                content.extend(chunk)
                if len(content) > MAX_BYTES:
                    raise ValueError('Attachment exceeds size limit')
                if time.monotonic() > deadline:
                    raise OSError('Attachment deadline exceeded')
    finally:
        connection.close()
    if not content or (length is not None and len(content) != int(length)) or not matches_type(content, mime):
        raise ValueError('Attachment does not match its content type')
    return bytes(content), mime


def store(workspace, content, mime):
    folder = ROOT / str(workspace)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    digest = hashlib.sha256(content).hexdigest()
    name = folder / (digest + MEDIA[mime][1])
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as temporary:
        path = Path(temporary.name)
        try:
            temporary.write(content)
            temporary.close()
            path.replace(name)
        finally:
            path.unlink(missing_ok=True)
    return digest


def claim(conn, workspace):
    conn.execute(
        "UPDATE socialmei.ig_inbound_media SET status='failed',source_url=NULL,lease_id=NULL "
        "WHERE workspace_id=%s AND status IN ('pending','fetching') AND available_at<=now() "
        "AND (expires_at<=now() OR attempts>=3)", (workspace,),
    )
    return conn.execute(
        "WITH due AS (SELECT a.id FROM socialmei.ig_inbound_media a JOIN socialmei.ig_meta_ingress_events e "
        "USING(workspace_id, external_account_id, event_key, message_id) "
        "JOIN socialmei.ig_meta_connections c ON c.workspace_id=e.workspace_id AND c.id=e.connection_id "
        "AND c.external_account_id=e.external_account_id "
        "WHERE a.workspace_id=%s AND a.status IN ('pending','fetching') AND a.attempts<3 "
        "AND a.available_at<=now() AND a.expires_at>now() AND e.kind='media' "
        "AND c.status='connected' AND c.expires_at>now() "
        "AND c.scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[] "
        "ORDER BY a.available_at,a.id LIMIT 1 FOR UPDATE OF a SKIP LOCKED) "
        "UPDATE socialmei.ig_inbound_media a SET status='fetching',attempts=attempts+1,lease_id=%s,"
        "available_at=now()+INTERVAL '2 minutes' FROM due WHERE a.id=due.id "
        "RETURNING a.id,a.workspace_id,a.kind,a.source_url,a.lease_id,a.attempts",
        (workspace, uuid4()),
    ).fetchone()


def media_connection():
    from psycopg import connect
    from settings import database_url

    return connect(database_url(), connect_timeout=5,
                   options='-c statement_timeout=5000 -c lock_timeout=3000')


def process_one(workspace):
    from psycopg.rows import dict_row

    with media_connection() as conn:
        conn.row_factory = dict_row
        locked = conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired",
            (f"instagram-inbound-media:{workspace}",),
        ).fetchone()
        if not locked['acquired']:
            return False
        job = claim(conn, workspace)
        conn.commit()
        if not job:
            return False
        status, digest, mime, size = 'failed', None, None, None
        try:
            content, mime = download(job['source_url'], job['kind'])
            digest = store(workspace, content, mime)
            size, status = len(content), 'ready'
        except ValueError:
            pass
        except (OSError, http.client.HTTPException):
            if job['attempts'] < 3:
                status = 'pending'
        conn.execute(
            "UPDATE socialmei.ig_inbound_media SET status=%s,sha256=%s,mime=%s,size_bytes=%s,lease_id=NULL,"
            "source_url=CASE WHEN %s='pending' THEN source_url END, available_at=now()+INTERVAL '1 minute' "
            "WHERE workspace_id=%s AND id=%s AND lease_id=%s",
            (status, digest, mime if size else None, size, status, workspace, job['id'], job['lease_id']),
        )
    return True


def metadata(conn, workspace, message_ids):
    return conn.execute(
        "SELECT id,message_id,CASE kind WHEN 'image' THEN 'imagem' ELSE 'audio' END AS media_kind,size_bytes "
        "FROM socialmei.ig_inbound_media WHERE workspace_id=%s AND message_id=ANY(%s) AND status='ready' "
        "ORDER BY message_id,position", (workspace, message_ids),
    ).fetchall()


def file_data(conn, workspace, attachment_id):
    if not 1 <= attachment_id <= 9007199254740991:
        raise HTTPException(404, 'Anexo não encontrado.')
    row = conn.execute(
        "SELECT sha256,mime,size_bytes FROM socialmei.ig_inbound_media "
        "WHERE workspace_id=%s AND id=%s AND status='ready'", (workspace, attachment_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, 'Anexo não encontrado.')
    mime = row['mime']
    try:
        if not re.fullmatch('[a-f0-9]{64}', row['sha256']):
            raise ValueError('Invalid attachment digest')
        path = ROOT / str(workspace) / (row['sha256'] + MEDIA[mime][1])
        if path.is_symlink():
            raise ValueError('Invalid attachment path')
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)), 'rb') as stream:
            content = stream.read(MAX_BYTES+1)
        if len(content) != row['size_bytes'] or hashlib.sha256(content).hexdigest() != row['sha256']:
            raise ValueError('Attachment checksum does not match')
    except (KeyError, OSError, ValueError):
        raise HTTPException(503, 'Anexo indisponível.') from None
    return {'id': attachment_id, 'mime': mime, 'data': base64.b64encode(content).decode()}


def main():
    import argparse
    from psycopg import Error

    parser = argparse.ArgumentParser(description='Fetch one due Instagram attachment for the configured workspace.')
    parser.add_argument('--workspace', type=int, required=True)
    args = parser.parse_args()
    if not enabled() or not 1 <= args.workspace <= 9007199254740991:
        parser.error('Instagram attachment processing is disabled or the workspace is invalid.')
    try:
        process_one(args.workspace)
    except (RuntimeError, Error):
        parser.exit(1, 'Fila de anexos do Instagram indisponível.\n')


if __name__ == '__main__':
    main()
