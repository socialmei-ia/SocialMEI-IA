"""Explicit owner-requested credential renewal. No worker, posting or messaging."""
from datetime import datetime, timedelta, timezone
import logging

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request

import settings
from account_auth import Strict, throttle
from instagram_meta_adapter import ProviderError, TokenGrant
from instagram_persistent_oauth import _authorize, _lock, _request_identity, db, oauth_service
from instagram_token_vault import TokenBinding, VaultError

router = APIRouter(prefix='/api/v1/instagram/meta', tags=['Instagram token maintenance'])
LOGGER = logging.getLogger('socialmei.instagram.maintenance')


class EmptyInput(Strict):
    pass


def transaction_limits(conn):
    conn.execute("SET LOCAL lock_timeout='3s'")
    conn.execute("SET LOCAL statement_timeout='5s'")


def refresh_connection(service, user, session_hash):
    if not settings.instagram_token_refresh_enabled():
        raise HTTPException(503, 'Renovação do Instagram ainda não habilitada.')
    database_failed = False
    try:
        with db() as conn:
            transaction_limits(conn)
            # A separate session lease blocks only competing renewals. OAuth/disconnect
            # may continue while the provider is contacted; final authorization is fresh.
            acquired = conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS acquired',
                                    (f'instagram-token-refresh:{user["workspace_id"]}',)).fetchone()['acquired']
            if not acquired:
                raise HTTPException(409, 'Já existe uma renovação em andamento. Consulte a conexão.')
            _lock(conn, user['workspace_id'])
            _authorize(conn, user, session_hash)
            previous = conn.execute("SELECT * FROM socialmei.ig_meta_connections WHERE workspace_id=%s "
                                    "AND status='connected' FOR UPDATE", (user['workspace_id'],)).fetchone()
            now = datetime.now(timezone.utc)
            if not previous or previous['expires_at'] <= now:
                raise HTTPException(409, 'Conecte novamente o Instagram profissional.')
            if previous['issued_at'] > now - timedelta(hours=24):
                raise HTTPException(409, 'A conexão só pode ser renovada após 24 horas da emissão do token.')
            # Commit releases session/member/connection row locks, retaining only the
            # renewal lease until this dedicated DB connection closes on every path.
            conn.commit()
            throttle(str(user['workspace_id']), 'instagram-token-refresh', timeout_seconds=3)
            binding = TokenBinding(user['workspace_id'], previous['id'], previous['external_account_id'])
            failure = None
            sealed = None
            try:
                token = service.vault.open(previous['encrypted_token'], binding)
                grant = TokenGrant(token, previous['external_account_id'], frozenset(previous['scopes']),
                                   int(previous['issued_at'].timestamp()), int(previous['expires_at'].timestamp()), 'long')
                fresh = service.adapter.refresh_token(grant)
                if (fresh.user_id != grant.user_id or fresh.scopes != grant.scopes or fresh.kind != 'long'
                    or fresh.issued_at < grant.issued_at or fresh.expires_at <= grant.expires_at):
                    raise ProviderError()
                identity = service.adapter.get_identity(fresh)
                if identity.user_id != previous['external_account_id']:
                    raise ProviderError()
                sealed = service.vault.seal(fresh.access_token, binding)
            except ProviderError:
                failure = 'provider'
            except VaultError:
                failure = 'vault'
            finally:
                token = None
                grant = None
            if failure:
                LOGGER.warning('instagram_refresh_failed reason=%s', failure)
                raise HTTPException(503, 'Não foi possível confirmar a renovação. A conexão anterior foi preservada.')
            transaction_limits(conn)
            _lock(conn, user['workspace_id'])
            _authorize(conn, user, session_hash)
            current = conn.execute("SELECT * FROM socialmei.ig_meta_connections WHERE workspace_id=%s AND id=%s "
                                   "FOR UPDATE", (user['workspace_id'], previous['id'])).fetchone()
            if (not current or current['status'] != 'connected' or current['revision'] != previous['revision']
                or current['external_account_id'] != previous['external_account_id']
                or current['encrypted_token'] != previous['encrypted_token']):
                raise HTTPException(409, 'A conexão mudou durante a renovação. Consulte o estado atual.')
            result = conn.execute("UPDATE socialmei.ig_meta_connections SET encrypted_token=%s,issued_at=%s,expires_at=%s,"
                                  "account_type=%s,revision=revision+1 WHERE workspace_id=%s AND id=%s RETURNING revision,expires_at",
                                  (sealed, datetime.fromtimestamp(fresh.issued_at, timezone.utc),
                                   datetime.fromtimestamp(fresh.expires_at, timezone.utc), identity.account_type,
                                   user['workspace_id'], previous['id'])).fetchone()
            conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'instagram_token_refreshed')", (user['id'],))
            return {'status': 'refreshed', 'provider': 'instagram', 'connection_id': str(previous['id']),
                    'revision': result['revision'], 'expires_at': result['expires_at'].isoformat()}
    except psycopg.Error:
        database_failed = True
    if database_failed:
        raise HTTPException(503, 'Renovação temporariamente indisponível. Consulte a conexão antes de repetir.')


@router.post('/connection/refresh-token')
def refresh_token(payload: EmptyInput, request: Request, service=Depends(oauth_service)):
    user, session_hash = _request_identity(request)
    return refresh_connection(service, user, session_hash)
