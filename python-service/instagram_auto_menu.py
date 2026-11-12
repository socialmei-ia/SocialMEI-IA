"""Opt-in server automation for authenticated, persisted Direct messages. No user impersonation."""
import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from account_auth import current, require_enabled
from database import connect
from instagram_meta_adapter import ProviderError
from instagram_persistent_oauth import _lock
from instagram_token_vault import TokenBinding
from whatsapp_bot import answer
import channel_booking_flow
import instagram_booking_flow

router = APIRouter(prefix='/api/v1/instagram/menu', tags=['Instagram automatic menu'])


def enabled(workspace):
    return (os.getenv('SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED') == 'true'
            and str(workspace) in os.getenv('SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACES', '').split(','))


@contextmanager
def db():
    with connect() as conn:
        conn.row_factory = dict_row
        yield conn


def manual_pause(conn, workspace, conversation):
    if not enabled(workspace):
        return
    if conn.execute("SELECT 1 FROM socialmei.ig_menu_replies WHERE workspace_id=%s AND conversation_id=%s "
                    "AND status IN ('dispatching','uncertain') LIMIT 1", (workspace, conversation)).fetchone():
        raise HTTPException(409, 'Resposta automática em andamento ou incerta. Concilie antes de responder.')
    conn.execute("INSERT INTO socialmei.ig_menu_conversations(workspace_id,conversation_id,state,revision) "
                 "VALUES(%s,%s,'human',1) ON CONFLICT(workspace_id,conversation_id) DO UPDATE "
                 "SET state='human',revision=ig_menu_conversations.revision+1,updated_at=NOW()",
                 (workspace, conversation))


def source(conn, workspace, message):
    return conn.execute(
        "SELECT m.id,m.conversation_id,m.text,m.occurred_at,v.contact_ref,c.id AS connection_id,c.external_account_id,c.encrypted_token "
        "FROM socialmei.me_messages m JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
        "JOIN socialmei.ig_meta_ingress_events e ON e.workspace_id=m.workspace_id AND e.message_id=m.id "
        "JOIN socialmei.ig_meta_connections c ON c.workspace_id=e.workspace_id AND c.id=e.connection_id "
        "AND c.external_account_id=e.external_account_id "
        "WHERE m.workspace_id=%s AND m.id=%s AND m.origin='instagram' AND v.origin='instagram' "
        "AND e.kind='message' AND e.status='processed' AND c.status='connected' AND c.expires_at>NOW() "
        "AND c.scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[] "
        "AND v.account_ref='instagram:' || c.external_account_id "
        "AND v.contact_ref ~ '^instagram:[0-9]{1,40}$' "
        "AND m.occurred_at>=NOW()-INTERVAL '2 minutes' AND m.occurred_at<=NOW()+INTERVAL '30 seconds' "
        "FOR SHARE OF c,v", (workspace, message),
    ).fetchone()


def next_source(workspace, start):
    if not enabled(workspace):
        return None
    with db() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        row = conn.execute(
            "SELECT m.id FROM socialmei.me_messages m "
            "JOIN socialmei.ig_meta_ingress_events e ON e.workspace_id=m.workspace_id AND e.message_id=m.id "
            "WHERE m.workspace_id=%s AND m.origin='instagram' AND e.kind='message' AND e.status='processed' "
            "AND e.received_at>=%s AND m.occurred_at>=%s "
            "AND m.occurred_at>=NOW()-INTERVAL '2 minutes' AND m.occurred_at<=NOW()+INTERVAL '30 seconds' "
            "AND NOT EXISTS(SELECT 1 FROM socialmei.ig_menu_replies r WHERE r.workspace_id=m.workspace_id AND r.source_message_id=m.id) "
            "AND (SELECT COUNT(*) FROM socialmei.ig_menu_replies r WHERE r.workspace_id=m.workspace_id "
            "AND r.conversation_id=m.conversation_id AND r.status IN ('dispatching','confirmed','uncertain') "
            "AND r.created_at>NOW()-INTERVAL '15 minutes')<10 "
            "AND (SELECT COUNT(*) FROM socialmei.ig_menu_replies r WHERE r.workspace_id=m.workspace_id "
            "AND r.status IN ('dispatching','confirmed','uncertain') AND r.created_at>NOW()-INTERVAL '15 minutes')<60 "
            "ORDER BY m.occurred_at,m.id LIMIT 1", (workspace, start, start),
        ).fetchone()
    return row['id'] if row else None


def reply(runtime, workspace, message, start):
    if not enabled(workspace) or not runtime.send or not runtime.direct.allow_dispatch:
        raise RuntimeError('Instagram automation not authorized')
    job_id = uuid4()
    with db() as conn:
        _lock(conn, workspace)
        row = source(conn, workspace, message)
        if not row:
            return 'skipped'
        if not conn.execute("SELECT 1 FROM socialmei.ig_meta_ingress_events e JOIN socialmei.me_messages m "
                            "ON m.workspace_id=e.workspace_id AND m.id=e.message_id WHERE e.workspace_id=%s "
                            "AND m.id=%s AND e.received_at>=%s AND m.occurred_at>=%s",
                            (workspace, message, start, start)).fetchone():
            return 'skipped'
        if conn.execute('SELECT 1 FROM socialmei.ig_menu_replies WHERE workspace_id=%s AND source_message_id=%s',
                        (workspace, message)).fetchone():
            return 'duplicate'
        if conn.execute("SELECT 1 FROM socialmei.ig_menu_replies WHERE workspace_id=%s AND status IN ('dispatching','uncertain') LIMIT 1",
                        (workspace,)).fetchone():
            raise HTTPException(409, 'Envio automático pendente de conciliação.')
        counts = conn.execute("SELECT COUNT(*) AS total,COUNT(*) FILTER(WHERE conversation_id=%s) AS contact "
                              "FROM socialmei.ig_menu_replies WHERE workspace_id=%s "
                              "AND status IN ('dispatching','confirmed','uncertain') "
                              "AND created_at>NOW()-INTERVAL '15 minutes'", (row['conversation_id'], workspace)).fetchone()
        if counts['total'] >= 60 or counts['contact'] >= 10:
            return 'rate_limited'
        conn.execute("INSERT INTO socialmei.ig_menu_conversations(workspace_id,conversation_id) VALUES(%s,%s) "
                     "ON CONFLICT DO NOTHING", (workspace, row['conversation_id']))
        state = conn.execute('SELECT * FROM socialmei.ig_menu_conversations WHERE workspace_id=%s AND conversation_id=%s FOR UPDATE',
                             (workspace, row['conversation_id'])).fetchone()
        pending = conn.execute("SELECT 1 FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND conversation_id=%s "
                               "AND status IN ('draft','approved','dispatching','retry_ready','uncertain') LIMIT 1",
                               (workspace, row['conversation_id'])).fetchone()
        resume = row['text'].strip().casefold() in {'0','menu','inicio','início'}
        current_state = 'menu' if resume and not pending else state['state']
        stale = state['last_occurred_at'] is not None and row['occurred_at'] < state['last_occurred_at']
        blocked = bool(pending) or current_state == 'human' or stale
        text = ''
        if blocked:
            new_state, result = answer(conn, workspace, current_state, row['text'])
        else:
            booking_plan = instagram_booking_flow.respond(conn, workspace, row)
            if booking_plan is not None:
                new_state, result, selection = booking_plan
                try:
                    text = instagram_booking_flow.render(result, selection)
                except ValueError:
                    # Do not truncate a confirmation reference or send unusable choices.
                    new_state = 'menu'
                    text = ('Não consegui apresentar todas as opções de agendamento. '
                            'Digite 6 para recomeçar ou 5 para falar com nossa equipe.')
            else:
                new_state, result = answer(conn, workspace, current_state, row['text'])
                result = channel_booking_flow.with_entry(conn, workspace, result)
                config = json.loads(os.getenv('SOCIALMEI_INSTAGRAM_AUTO_MENU_CONFIG', '{}')).get(str(workspace), {})
                if result['action'] == 'menu' and config.get('greeting'):
                    text = config['greeting']
                else:
                    text = result['text']
                if result['choices']:
                    text += '\n\n' + '\n'.join(c['id']+' - '+c['title'] for c in result['choices'])
                text = text.encode('utf-8')[:1000].decode('utf-8', errors='ignore')
            if not text.strip() or any(ord(c)<32 and c not in '\n\r\t' for c in text):
                raise ValueError('Invalid automatic greeting')
        # Persist the full choice reference for a verified follow-up, but never
        # disclose that opaque internal state in a customer-facing Direct.
        outbound_text = instagram_booking_flow.public_text(text)
        if not blocked and not outbound_text.strip():
            raise ValueError('Invalid customer-facing reply')
        token = None if blocked else runtime.direct.vault.open(row['encrypted_token'], TokenBinding(
            workspace, row['connection_id'], row['external_account_id']))
        conn.execute("INSERT INTO socialmei.ig_menu_replies(workspace_id,id,conversation_id,source_message_id,connection_id,external_account_id,recipient_id,text,status,finished_at) "
                     "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                     (workspace, job_id, row['conversation_id'], message, row['connection_id'], row['external_account_id'],
                      row['contact_ref'].split(':')[1], text, 'skipped' if blocked else 'dispatching',
                      datetime.now(timezone.utc) if blocked else None))
        conn.execute('UPDATE socialmei.ig_menu_conversations SET state=%s,revision=revision+1,updated_at=NOW(), '
                     'last_message_id=%s,last_occurred_at=%s '
                     'WHERE workspace_id=%s AND conversation_id=%s',
                     (state['state'] if stale else ('human' if pending else new_state),
                      state['last_message_id'] if stale else message,
                      state['last_occurred_at'] if stale else row['occurred_at'], workspace, row['conversation_id']))
    if blocked:
        return 'skipped'
    status, receipt = 'uncertain', None
    try:
        sent = runtime.direct.adapter.send_direct(token, row['external_account_id'], row['contact_ref'].split(':')[1], outbound_text)
        status, receipt = 'confirmed', sent['message_id']
    except ProviderError as error:
        if not error.outcome_unknown:
            status = 'failed'
    except Exception:
        pass
    finally:
        token = None
    with db() as conn:
        conn.execute('UPDATE socialmei.ig_menu_replies SET status=%s,provider_message_id=%s,finished_at=NOW() '
                     "WHERE workspace_id=%s AND id=%s AND status='dispatching'", (status, receipt, workspace, job_id))
    return status


def actor(conversation):
    require_enabled()
    user = current()
    if not enabled(user['workspace_id']):
        raise HTTPException(503, 'Menu automático não habilitado.')
    with db() as conn:
        if not conn.execute("SELECT 1 FROM socialmei.me_conversations WHERE workspace_id=%s AND id=%s AND origin='instagram'",
                            (user['workspace_id'], conversation)).fetchone():
            raise HTTPException(404, 'Conversa não encontrada.')
    return user


@router.get('/conversations/{conversation}/status')
def status(conversation: int):
    user = actor(conversation)
    with db() as conn:
        row = conn.execute('SELECT state FROM socialmei.ig_menu_conversations WHERE workspace_id=%s AND conversation_id=%s',
                           (user['workspace_id'], conversation)).fetchone()
    return {'state': row['state'] if row else 'menu'}


@router.post('/conversations/{conversation}/{action}', status_code=204)
def change(conversation: int, action: str):
    user = actor(conversation)
    if user['role'] not in {'owner','admin','member'}:
        raise HTTPException(403, 'Sem permissão para alterar o atendimento.')
    if action not in {'pause','resume'}:
        raise HTTPException(404, 'Ação indisponível.')
    with db() as conn:
        _lock(conn, user['workspace_id'])
        manual_pause(conn, user['workspace_id'], conversation)
        if action == 'resume':
            if conn.execute("SELECT 1 FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND conversation_id=%s "
                            "AND status IN ('draft','approved','dispatching','retry_ready','uncertain') LIMIT 1",
                            (user['workspace_id'], conversation)).fetchone():
                raise HTTPException(409, 'Conclua ou cancele a resposta manual antes de retomar.')
            conn.execute("UPDATE socialmei.ig_menu_conversations SET state='menu',revision=revision+1,updated_at=NOW() "
                         'WHERE workspace_id=%s AND conversation_id=%s', (user['workspace_id'], conversation))
