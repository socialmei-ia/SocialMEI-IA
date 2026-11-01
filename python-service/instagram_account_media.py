"""Read the connected professional account's media without enabling publishing."""
import re
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlsplit

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.rows import dict_row

from account_auth import COOKIE, current, digest, require_enabled
from database import connect
from instagram_http_transport import ACCOUNT_MEDIA_FIELDS
from instagram_meta_adapter import ProviderError, ProviderRequest
from instagram_persistent_oauth import _authorize
from instagram_token_vault import TokenBinding, VaultError

router = APIRouter(prefix='/api/v1/instagram', tags=['Instagram account media'])
CURSOR = re.compile(r'[A-Za-z0-9_+/-]{1,2048}={0,2}\Z')
PAGE_SIZE = 5


def media_service(request: Request):
    from instagram_runtime import runtime_service
    return runtime_service(request, 'oauth')


def public_url(value, *, permalink=False):
    """Only provider-owned HTTPS links, without OAuth credentials or fragments."""
    if not isinstance(value, str) or not 1 <= len(value) <= 4096 or not value.isascii():
        return None
    if '\\' in value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        return None
    try:
        url = urlsplit(value)
        host = url.hostname or ''
        if (url.scheme != 'https' or url.port not in {None, 443} or url.username is not None or url.password is not None
                or url.fragment or not url.path.startswith('/') or url.path.startswith('//')):
            return None
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}', host):
            return None
        if permalink:
            if host not in {'instagram.com', 'www.instagram.com'} or not re.fullmatch(
                r'/(?:p|reel|tv)/[A-Za-z0-9_-]{1,100}/?', url.path
            ):
                return None
        elif not (host.endswith('.cdninstagram.com') or host.endswith('.fbcdn.net')):
            return None
        if any(key.lower() in {'access_token', 'token', 'authorization', 'code', 'appsecret_proof'}
               for key, _ in parse_qsl(url.query, keep_blank_values=True)):
            return None
        return value
    except (ValueError, UnicodeError):
        return None


def media_item(item):
    if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not re.fullmatch(r'[0-9]{1,40}', item['id']):
        raise ProviderError()
    if not isinstance(item.get('media_type'), str) or item['media_type'] not in {'IMAGE', 'VIDEO', 'CAROUSEL_ALBUM'}:
        raise ProviderError()
    caption = item.get('caption', '')
    if not isinstance(caption, str):
        raise ProviderError()
    try:
        caption.encode('utf-8')
    except UnicodeEncodeError:
        raise ProviderError() from None
    caption = ''.join(c for c in caption[:2200] if ord(c) >= 32 or c in '\n\r\t')
    timestamp = item.get('timestamp')
    if timestamp is not None:
        try:
            if not isinstance(timestamp, str) or not 1 <= len(timestamp) <= 40:
                raise ValueError()
            parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                raise ValueError()
            timestamp = parsed.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError):
            raise ProviderError() from None
    return {
        'id': item['id'], 'caption': caption, 'media_type': item['media_type'],
        'media_url': public_url(item.get('media_url')),
        'thumbnail_url': public_url(item.get('thumbnail_url')),
        'permalink': public_url(item.get('permalink'), permalink=True), 'timestamp': timestamp,
    }


def provider_page(adapter, token, account_id, after):
    if not isinstance(account_id, str) or not re.fullmatch(r'[0-9]{1,40}', account_id):
        raise ProviderError()
    if after is not None and (not isinstance(after, str) or len(after) > 2048 or not CURSOR.fullmatch(after)):
        raise ProviderError()
    params = {'fields': ACCOUNT_MEDIA_FIELDS, 'limit': str(PAGE_SIZE)}
    if after is not None:
        params['after'] = after
    response = adapter._request(ProviderRequest(
        'GET', f'https://graph.instagram.com/{adapter._version}/{account_id}/media',
        params=params, headers={'Authorization': 'Bearer ' + token},
    ), retryable=True)
    data = response.get('data')
    if not isinstance(data, list) or len(data) > PAGE_SIZE:
        raise ProviderError()
    items = [media_item(item) for item in data]
    if len({item['id'] for item in items}) != len(items):
        raise ProviderError()
    next_cursor = None
    paging = response.get('paging')
    # The provider's next URL may contain an access token. Never return or follow it.
    if isinstance(paging, dict) and isinstance(paging.get('next'), str) and paging['next']:
        cursors = paging.get('cursors')
        candidate = cursors.get('after') if isinstance(cursors, dict) else None
        if isinstance(candidate, str) and len(candidate) <= 2048 and CURSOR.fullmatch(candidate) and candidate != after:
            next_cursor = candidate
    return {'items': items, 'next_cursor': next_cursor}


def account_media(user, session, service, after=None):
    if after is not None and (len(after) > 2048 or not CURSOR.fullmatch(after)):
        raise HTTPException(422, 'Cursor de publicações inválido.')
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute("SET LOCAL lock_timeout='3s'")
            conn.execute("SET LOCAL statement_timeout='5s'")
            _authorize(conn, user, session, manage=False)
            role = conn.execute('SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s',
                                (user['workspace_id'], user['id'])).fetchone()
            if not role or role['role'] not in {'owner', 'admin', 'member', 'viewer'}:
                raise HTTPException(403, 'Sem permissão para consultar publicações.')
            row = conn.execute(
                'SELECT id,external_account_id,encrypted_token,expires_at FROM socialmei.ig_meta_connections '
                "WHERE workspace_id=%s AND status='connected' AND expires_at>NOW() "
                "AND scopes @> ARRAY['instagram_business_basic']::text[] "
                'ORDER BY created_at DESC,id DESC LIMIT 1 FOR SHARE', (user['workspace_id'],),
            ).fetchone()
            if not row:
                raise HTTPException(409, 'Conecte o Instagram profissional com permissão para consultar publicações.')
            token = service.vault.open(row['encrypted_token'], TokenBinding(
                user['workspace_id'], row['id'], row['external_account_id'],
            ))
            result = provider_page(service.adapter, token, row['external_account_id'], after)
            if row['expires_at'] <= datetime.now(timezone.utc):
                raise HTTPException(409, 'Conexão Instagram expirada. Renove a conexão.')
            return result
    except (ProviderError, VaultError):
        raise HTTPException(503, 'Publicações Instagram indisponíveis. Verifique a conexão e as permissões.') from None
    except psycopg.Error:
        raise HTTPException(503, 'Consulta de publicações indisponível. Tente novamente.') from None


@router.get('/media')
def listing(request: Request, after: str | None = Query(default=None, max_length=2048), service=Depends(media_service)):
    require_enabled()
    return account_media(current(), digest(request.cookies.get(COOKIE, '')), service, after)
