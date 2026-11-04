"""Read-only receipt evidence scoped to the authenticated business; no provider I/O."""
from datetime import datetime, timezone

import psycopg
from fastapi import APIRouter, HTTPException, Request, Response

from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix='/api/v1/whatsapp', tags=['WhatsApp receiving evidence'])


@router.get('/receiving-status')
def receiving_status(request: Request, response: Response):
    require_enabled()
    user = current()
    if user['role'] not in {'owner', 'admin', 'member', 'viewer'}:
        raise HTTPException(403, 'Permissão insuficiente para consultar o recebimento.')
    if request.query_params:
        raise HTTPException(422, 'A consulta utiliza somente o negócio autenticado.')
    try:
        with connect() as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL statement_timeout='2s'")
            # EXISTS avoids counting duplicated event envelopes as new messages.
            row = conn.execute(
                'SELECT count(*),count(DISTINCT m.conversation_id),'
                'max((SELECT max(e.processado_em) FROM socialmei.crm_eventos_canal e '
                "WHERE e.workspace_id=m.workspace_id AND e.inbox_message_id=m.id "
                "AND e.tipo='message' AND e.status='processado' AND e.inbox_origin='waha')) "
                'FROM socialmei.me_messages m JOIN socialmei.me_conversations c '
                'ON c.workspace_id=m.workspace_id AND c.id=m.conversation_id '
                "WHERE m.workspace_id=%s AND m.origin='waha' AND c.origin='waha' "
                "AND c.channel='whatsapp' AND EXISTS(SELECT 1 FROM socialmei.crm_eventos_canal e "
                'WHERE e.workspace_id=m.workspace_id AND e.inbox_message_id=m.id '
                "AND e.tipo='message' AND e.status='processado' AND e.inbox_origin='waha')",
                (user['workspace_id'],),
            ).fetchone()
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível consultar o recebimento. Tente novamente.') from None
    response.headers['Cache-Control'] = 'no-store'
    return {
        'source': 'postgresql',
        'workspace_id': user['workspace_id'],
        'message_count': row[0],
        'conversation_count': row[1],
        'last_persisted_at': row[2].isoformat() if row[2] and row[0] else None,
        'historical_receiving_confirmed': row[0] > 0,
        'session_live_verified': False,
        'sending_available': False,
        'observed_at': datetime.now(timezone.utc).isoformat(),
    }
