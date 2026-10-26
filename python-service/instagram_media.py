"""Expiring unguessable JPEG delivery for Meta. No credentials or original filenames."""
import base64
import binascii
import hashlib
import io
import re
import secrets
import warnings
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from psycopg.rows import dict_row
from pydantic import Field

from account_auth import Strict, origin
from database import connect
from instagram_persistent_oauth import _authorize
from instagram_publishing import actor, service

router = APIRouter()
MAX_IMAGE_BYTES = 2 * 1024 * 1024
KEY = re.compile(r'[A-Za-z0-9_-]{43}\Z')


def normalize_image(encoded):
    if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
        raise HTTPException(413, 'A foto deve ter até 2 MiB.')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(413, 'A foto deve ter até 2 MiB.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError()
                width, height = image.size
                if width * height > 16_000_000 or not 0.8 <= width / height <= 1.91:
                    raise ValueError()
                image.load()
                image = ImageOps.exif_transpose(image)
                if not 0.8 <= image.width / image.height <= 1.91:
                    raise ValueError()
                image.thumbnail((1440, 1440))
                # A new RGB surface deliberately drops EXIF, GPS and embedded metadata.
                clean = Image.new('RGB', image.size, 'white')
                if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                    rgba = image.convert('RGBA')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    clean.paste(image.convert('RGB'))
                output = io.BytesIO()
                clean.save(output, format='JPEG', quality=90)
                result = output.getvalue()
                if len(result) > MAX_IMAGE_BYTES:
                    raise ValueError()
                return result
    except (ValueError, OSError, binascii.Error, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'Use uma foto JPEG, PNG ou WebP estática, com proporção de 4:5 a 1,91:1 e até 16 megapixels.') from None


class ImageUpload(Strict):
    request_id: UUID
    image_base64: str = Field(min_length=1, max_length=2796204)


@router.post('/api/v1/instagram/publishing/upload')
def upload(payload: ImageUpload, request: Request, publisher=Depends(service)):
    user, session = actor(request)
    raw = normalize_image(payload.image_base64)
    fingerprint = hashlib.sha256(raw).hexdigest()
    with connect() as conn:
        conn.row_factory = dict_row
        _authorize(conn, user, session)
        publisher._connection(conn, user)
        conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                     ('instagram-media:' + str(user['workspace_id']),))
        # Cleanup is bounded per call; a scheduled cleanup command is also supplied.
        conn.execute('DELETE FROM socialmei.ig_meta_media WHERE id IN '
                     '(SELECT id FROM socialmei.ig_meta_media WHERE expires_at<=NOW() LIMIT 100)')
        row = conn.execute('SELECT * FROM socialmei.ig_meta_media WHERE workspace_id=%s AND request_id=%s',
                           (user['workspace_id'], payload.request_id)).fetchone()
        if row:
            if row['created_by'] != user['id'] or row['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Identificador usado para outra foto.')
        else:
            count = conn.execute('SELECT count(*) AS n FROM socialmei.ig_meta_media WHERE workspace_id=%s',
                                 (user['workspace_id'],)).fetchone()['n']
            if count >= 20:
                raise HTTPException(429, 'Limite temporário de fotos atingido. Aguarde a expiração.')
            row = conn.execute(
                'INSERT INTO socialmei.ig_meta_media '
                '(id,workspace_id,created_by,request_id,public_key,fingerprint,image_bytes) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                (uuid4(), user['workspace_id'], user['id'], payload.request_id,
                 secrets.token_urlsafe(32), fingerprint, raw),
            ).fetchone()
    return {'media_id': str(row['id']), 'expires_at': row['expires_at'].isoformat()}


@router.get('/media/instagram/{key}.jpg')
def deliver(key: str):
    if not KEY.fullmatch(key):
        raise HTTPException(404, 'Foto indisponível.')
    with connect() as conn:
        row = conn.execute('SELECT image_bytes FROM socialmei.ig_meta_media '
                           'WHERE public_key=%s AND expires_at>NOW()', (key,)).fetchone()
    if not row:
        raise HTTPException(404, 'Foto indisponível.')
    return Response(bytes(row[0]), media_type='image/jpeg', headers={
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': 'inline; filename="instagram.jpg"',
        'Referrer-Policy': 'no-referrer',
    })


def resolve_media(conn, user, media_id):
    row = conn.execute('SELECT public_key FROM socialmei.ig_meta_media '
                       'WHERE id=%s AND workspace_id=%s AND created_by=%s AND expires_at>NOW()',
                       (media_id, user['workspace_id'], user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'Foto indisponível ou expirada. Selecione novamente.')
    return origin().rstrip('/') + '/media/instagram/' + row['public_key'] + '.jpg'


class InstagramMediaPrivacy:
    """Mask the bearer media path before Uvicorn's response-time access logging."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get('type') != 'http' or not scope.get('path', '').startswith('/media/instagram/'):
            return await self.app(scope, receive, send)
        def redact():
            scope['path'] = '/media/instagram/[redacted].jpg'
            scope['raw_path'] = b'/media/instagram/[redacted].jpg'
            scope['query_string'] = b''
        async def private_send(message):
            if message['type'] == 'http.response.start':
                # Routing/lookup has completed. The server logs this scope at send().
                redact()
            await send(message)
        try:
            await self.app(scope, receive, private_send)
        finally:
            # ServerErrorMiddleware can emit a 500 outside private_send.
            redact()
