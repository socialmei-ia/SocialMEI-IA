"""Account-bound inbound source gate, with a fresh activation watermark."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Request
def valid_token(value):
    return isinstance(value, str) and re.fullmatch(r'sm:[0-9a-f]{32}:[0-9]', value) is not None

import settings

original_contact_scope = settings.whatsapp_bot_allowed_contacts
import public_app as original

PUBLIC = os.getenv('SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE') == 'YES'
settings.whatsapp_bot_allowed_contacts = (lambda: None) if PUBLIC else original_contact_scope
app = original.app
START = datetime.fromisoformat(os.environ['SOCIALMEI_CONTINUOUS_START_UTC'])
if START.tzinfo is None:
    raise RuntimeError('Activation timezone required')
SESSION = os.getenv('SOCIALMEI_MENU_SESSION', '01')
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,159}', SESSION):
    raise RuntimeError('Invalid bound session')
CONTACTS = [] if PUBLIC else json.loads(Path('/run/socialmei/pilot/allowed-contacts.json').read_text())
if not PUBLIC and (not isinstance(CONTACTS, list) or len(CONTACTS) != 1 or set(CONTACTS) != set(original_contact_scope() or [])):
    raise RuntimeError('Contact authorization mismatch')


def sources(request: Request):
    if datetime.now(timezone.utc) < START:
        raise HTTPException(409, 'Ativação pendente.')
    original.require_bot()
    with original.operation_database() as conn:
        channel = original.authorize(conn, request)
        if (channel['workspace_id'], channel['channel_id'], channel['instancia'], channel['sessao']) != (1, 1, 'socialmei-equipe-piloto', SESSION):
            raise HTTPException(403, 'Canal fora da autorização.')
        rows = conn.execute(
            "SELECT e.mensagem_externa_id AS external_message_id,COALESCE(e.dados_normalizados->>'wa_selection',m.text) AS text,s.state "
            "FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id AND m.origin='waha' "
            "JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_conversations s ON s.workspace_id=e.workspace_id AND s.channel_id=e.canal_id AND s.conversation_id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_decisions d ON d.workspace_id=e.workspace_id AND d.channel_id=e.canal_id AND d.source_message_id=m.id "
            "WHERE e.workspace_id=1 AND e.canal_id=1 AND e.tipo='message' AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s "
            + ("" if PUBLIC else "AND v.contact_ref=ANY(%s::text[]) ") +
            "AND d.id IS NULL AND e.recebido_em>=%s AND m.occurred_at>=%s "
            "AND m.occurred_at<=NOW()+INTERVAL '30 seconds' AND m.occurred_at>=NOW()-INTERVAL '2 minutes' "
            "AND (SELECT COUNT(*) FROM socialmei.wa_bot_decisions q "
            "WHERE q.workspace_id=e.workspace_id AND q.channel_id=e.canal_id "
            "AND q.conversation_id=v.id AND q.status IN ('claimed','confirmed','uncertain') "
            + ("AND q.created_at>=NOW()-INTERVAL '15 minutes')<10 " if PUBLIC
               else "AND q.created_at>=NOW()-INTERVAL '45 minutes')<5 ") +
            "ORDER BY m.occurred_at,m.id LIMIT 40",
            tuple([channel['identificador_conta'], 'waha:' + channel['identificador_conta']]
                  + ([] if PUBLIC else [CONTACTS]) + [START, START]),
        ).fetchall()
        for row in rows:
            if original.permitted_text(row['text'], row['state']) or valid_token(row['text']):
                return {'sources': [{'instance': channel['instancia'], 'external_message_id': row['external_message_id']}]}
    return {'sources': []}


app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', None) != '/internal/whatsapp/bot/sources']
app.add_api_route('/internal/whatsapp/bot/sources', sources, methods=['GET'])
