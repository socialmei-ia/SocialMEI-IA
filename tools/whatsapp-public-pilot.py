"""Read/claim gate for an explicitly authorized, existing-contact menu pilot."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import settings

original_contact_scope = settings.whatsapp_bot_allowed_contacts
import public_app as original

settings.whatsapp_bot_allowed_contacts = original_contact_scope
app = original.app
START = original.START
END = START + timedelta(seconds=600)
CONTACTS = json.loads(Path('/run/socialmei/pilot/allowed-contacts.json').read_text())
if not CONTACTS or not isinstance(CONTACTS, list):
    raise RuntimeError('Pilot contacts required')
if set(CONTACTS) != set(original_contact_scope() or []):
    raise RuntimeError('Pilot contact scope differs from existing authorization')


def sources(request: Request):
    if not START <= datetime.now(timezone.utc) < END:
        raise HTTPException(410, 'Piloto encerrado.')
    original.require_bot()
    with original.operation_database() as conn:
        channel = original.authorize(conn, request)
        if (channel['workspace_id'], channel['channel_id'], channel['instancia'], channel['sessao']) != (1, 1, 'socialmei-equipe-piloto', '01'):
            raise HTTPException(403, 'Canal fora do piloto.')
        rows = conn.execute(
            "SELECT e.mensagem_externa_id AS external_message_id,m.text,s.state "
            "FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id AND m.origin='waha' "
            "JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_conversations s ON s.workspace_id=e.workspace_id AND s.channel_id=e.canal_id AND s.conversation_id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_decisions d ON d.workspace_id=e.workspace_id AND d.channel_id=e.canal_id AND d.source_message_id=m.id "
            "WHERE e.workspace_id=1 AND e.canal_id=1 AND e.tipo='message' AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s AND v.contact_ref=ANY(%s::text[]) "
            "AND d.id IS NULL AND e.recebido_em>=%s AND m.occurred_at>=%s "
            "AND m.occurred_at<=NOW()+INTERVAL '30 seconds' AND m.occurred_at>=NOW()-INTERVAL '2 minutes' "
            "ORDER BY m.occurred_at,m.id LIMIT 40",
            (channel['identificador_conta'], 'waha:' + channel['identificador_conta'], CONTACTS, START, START),
        ).fetchall()
        for row in rows:
            if original.permitted_text(row['text'], row['state']):
                return {'sources': [{'instance': channel['instancia'], 'external_message_id': row['external_message_id']}]}
    return {'sources': []}


app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', None) != '/internal/whatsapp/bot/sources']
app.add_api_route('/internal/whatsapp/bot/sources', sources, methods=['GET'])


@app.middleware('http')
async def pilot_window(request: Request, call_next):
    receipt = request.method == 'POST' and request.url.path.endswith('/receipt')
    if not receipt and not START <= datetime.now(timezone.utc) < END:
        return JSONResponse({'detail': 'Piloto encerrado.'}, status_code=410)
    return await call_next(request)
