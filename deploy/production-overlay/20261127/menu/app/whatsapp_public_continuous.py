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
        import settings as pilot_settings
        import os as pilot_os

        if pilot_os.getenv("SOCIALMEI_WAHA_PILOT_BINDING_SHA256"):
            authorized = pilot_settings.waha_pilot_binding_allowed(
                channel["workspace_id"],
                channel["channel_id"],
                channel["instancia"],
                channel["sessao"],
                channel["identificador_conta"],
                channel["versao"],
                pilot_os.getenv("SOCIALMEI_MENU_WAHA_ENGINE","WEBJS")
            )
        else:
            authorized = (
                channel["workspace_id"],
                channel["channel_id"],
                channel["instancia"],
                channel["sessao"]
            ) == (1,1,"socialmei-equipe-piloto",SESSION)

        if not authorized or channel["sessao"] != SESSION:
            raise HTTPException(403, 'Canal fora da autorização.')
        import re as capacity_re
        excluded_raw = request.headers.get(
            'X-SocialMEI-Excluded-Contacts', ''
        )
        excluded = excluded_raw.split(',') if excluded_raw else []
        if len(excluded) > 60 or any(
            not capacity_re.fullmatch(r'[0-9a-f]{64}', item)
            for item in excluded
        ):
            raise HTTPException(400, 'Filtro de capacidade invalido')

        cutoff = START
        cutoff_raw = request.headers.get('X-SocialMEI-Source-Cutoff')
        if cutoff_raw:
            try:
                value = datetime.fromisoformat(cutoff_raw)
                if value.utcoffset() is None:
                    raise ValueError()
                if value.timestamp() > datetime.now(timezone.utc).timestamp() + 30:
                    raise ValueError()
                cutoff = max(START, value)
            except ValueError:
                raise HTTPException(400, 'Corte invalido')

        rows = conn.execute(
            "SELECT e.mensagem_externa_id AS external_message_id,COALESCE(e.dados_normalizados->>'wa_selection',m.text) AS text,s.state "
            "FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id AND m.origin='waha' "
            "JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_conversations s ON s.workspace_id=e.workspace_id AND s.channel_id=e.canal_id AND s.conversation_id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_decisions d ON d.workspace_id=e.workspace_id AND d.channel_id=e.canal_id AND d.source_message_id=m.id "
            "WHERE e.workspace_id=%s AND e.canal_id=%s AND e.tipo='message' AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s "
            + ("" if PUBLIC else "AND v.contact_ref=ANY(%s::text[]) ") +
             "AND NOT (encode(sha256(convert_to(substring(v.contact_ref from 6),'UTF8')),'hex') = ANY(%s::text[])) "
            "AND NOT EXISTS (SELECT 1 FROM socialmei.wa_bot_decisions q WHERE q.workspace_id=e.workspace_id AND q.channel_id=e.canal_id AND q.conversation_id=v.id AND q.status IN ('claimed','uncertain') AND q.id NOT IN ('d095f540-7071-4045-a6d1-6b283e5a15cd'::uuid,'a3da1993-97c3-4856-bfb0-061452a70d57'::uuid)) AND (e.workspace_id<>60 OR e.canal_id<>3 OR e.recebido_em<=NOW()-INTERVAL '4 seconds') AND d.id IS NULL AND e.recebido_em>=%s AND m.occurred_at>=%s " 
            "AND m.occurred_at<=NOW()+INTERVAL '30 seconds' AND m.occurred_at>=NOW()-INTERVAL '2 minutes' "
            "AND (SELECT COUNT(*) FROM socialmei.wa_bot_decisions q "
            "WHERE q.workspace_id=e.workspace_id AND q.channel_id=e.canal_id "
            "AND q.conversation_id=v.id AND q.status IN ('claimed','confirmed','uncertain') "
            + ("AND q.created_at>=NOW()-INTERVAL '15 minutes')<10 " if PUBLIC
               else "AND q.created_at>=NOW()-INTERVAL '45 minutes')<5 ") +
            "ORDER BY m.occurred_at,m.id LIMIT 40",
            tuple([channel['workspace_id'],channel['channel_id'],channel['identificador_conta'], 'waha:' + channel['identificador_conta']]
                  + ([] if PUBLIC else [CONTACTS]) + [excluded, cutoff, cutoff]),
        ).fetchall()
        for row in rows:
            if original.permitted_text(row['text'], row['state']) or valid_token(row['text']):
                return {'isolation_version':'conversation-v1','sources': [{'instance': channel['instancia'], 'external_message_id': row['external_message_id']}]}
    return {'isolation_version':'conversation-v1','sources': []}


app.router.routes[:] = [route for route in app.router.routes if getattr(route, 'path', None) != '/internal/whatsapp/bot/sources']
app.add_api_route('/internal/whatsapp/bot/sources', sources, methods=['GET'])
