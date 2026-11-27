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
from whatsapp_bot import answer, HUMAN_CHOICES
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
            "JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "JOIN socialmei.ig_meta_connections c ON c.workspace_id=e.workspace_id AND c.id=e.connection_id "
            "AND c.external_account_id=e.external_account_id "
            "WHERE m.workspace_id=%s AND m.origin='instagram' AND e.kind='message' AND e.status='processed' "
            "AND v.origin='instagram' AND v.account_ref='instagram:' || c.external_account_id "
            "AND v.contact_ref ~ '^instagram:[0-9]{1,40}$' "
            "AND c.status='connected' AND c.expires_at>NOW() "
            "AND c.scopes @> ARRAY['instagram_business_basic','instagram_business_manage_messages']::text[] "
            "AND e.received_at>=%s AND m.occurred_at>=%s "
            "AND m.occurred_at>=NOW()-INTERVAL '2 minutes' AND m.occurred_at<=NOW()+INTERVAL '30 seconds' "
            "AND NOT EXISTS(SELECT 1 FROM socialmei.ig_menu_replies r WHERE r.workspace_id=m.workspace_id AND r.source_message_id=m.id) "
            "AND (lower(btrim(m.text))=ANY(%s) OR ((SELECT COUNT(*) FROM socialmei.ig_menu_replies r WHERE r.workspace_id=m.workspace_id "
            "AND r.conversation_id=m.conversation_id AND r.status IN ('dispatching','confirmed','uncertain') "
            "AND r.created_at>NOW()-INTERVAL '15 minutes')<10 "
            "AND (SELECT COUNT(*) FROM socialmei.ig_menu_replies r WHERE r.workspace_id=m.workspace_id "
            "AND r.status IN ('dispatching','confirmed','uncertain') AND r.created_at>NOW()-INTERVAL '15 minutes')<60 "
            ")) ORDER BY m.occurred_at,m.id LIMIT 1", (workspace, start, start, sorted(HUMAN_CHOICES)),
        ).fetchone()
    return row['id'] if row else None


def reply(runtime, workspace, message, start):
    if not enabled(workspace) or not runtime.send or not runtime.direct.allow_dispatch:
        raise RuntimeError('Instagram automation not authorized')
    from instagram_ai_bridge import generate,human_requested,sm_ig_command,sm_ig_greeting,sm_ig_actions
    ai_text = generate(workspace,message,start)
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
        limited = counts['total'] >= 60 or counts['contact'] >= 10
        if limited and row['text'].strip().casefold() not in HUMAN_CHOICES:
            return 'rate_limited'
        conn.execute("INSERT INTO socialmei.ig_menu_conversations(workspace_id,conversation_id) VALUES(%s,%s) "
                     "ON CONFLICT DO NOTHING", (workspace, row['conversation_id']))
        state = conn.execute('SELECT * FROM socialmei.ig_menu_conversations WHERE workspace_id=%s AND conversation_id=%s FOR UPDATE',
                             (workspace, row['conversation_id'])).fetchone()
        pending = conn.execute("SELECT 1 FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND conversation_id=%s "
                               "AND status IN ('draft','approved','dispatching','retry_ready','uncertain') LIMIT 1",
                               (workspace, row['conversation_id'])).fetchone()
        if workspace in (60,61):
            command=sm_ig_command(row['text'])
            if command:
                row['text']=command

        if human_requested(row['text']):
            row['text'] = '5'
        resume = row['text'].strip().casefold() in {'0','menu','inicio','início'}
        current_state = 'menu' if resume and not pending else state['state']
        stale = state['last_occurred_at'] is not None and row['occurred_at'] < state['last_occurred_at']
        # A customer's human handoff survives send limits without sending an acknowledgement.
        if limited and not stale:
            current_state = 'human'
        blocked = bool(pending) or current_state == 'human' or stale
        text = ''
        general_quick=[]
        if blocked:
            new_state, result = answer(conn, workspace, current_state, row['text'])
        else:
            booking_plan = None if workspace in (60,61) and sm_ig_greeting(row['text']) else instagram_booking_flow.respond(conn, workspace, row)
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
                if workspace in (60,61) and result['action']=='menu':
                    from instagram_ai_bridge import booking_available

                    if not booking_available(conn,workspace):
                        result['choices']=[
                            choice for choice in result['choices']
                            if choice['id']!='6'
                        ]

                config = json.loads(os.getenv('SOCIALMEI_INSTAGRAM_AUTO_MENU_CONFIG', '{}')).get(str(workspace), {})
                use_ai = bool(
                    ai_text and result['action'] == 'menu'
                    and current_state == 'menu'
                    and not row['text'].strip().isdecimal()
                    and row['text'].strip().casefold()
                        not in {'0','menu','inicio','início','voltar'}
                )
                if use_ai:
                    text = ai_text
                elif result['action'] == 'menu':
                    business = conn.execute(
                        "SELECT nome FROM socialmei.workspaces WHERE id=%s",
                        (workspace,)
                    ).fetchone()
                    text = (
                        (business['nome'] + '\n\n') if business else ''
                    ) + result['text']
                else:
                    text = result['text']
                if workspace in (60,61) and result['action']=='menu' and not use_ai:
                    greeting=sm_ig_greeting(row['text'])
                    explicit_menu=row['text'].strip().casefold() in {'0','menu','inicio','início','voltar'}

                    business=conn.execute(
                        'SELECT nome FROM socialmei.workspaces WHERE id=%s',
                        (workspace,)
                    ).fetchone()

                    name=business['nome'] if business else ''

                    if greeting:
                        text=('Olá! Seja bem-vindo à '+name+'. ' if name else 'Olá! ') + 'Como podemos ajudar você hoje?'
                    elif explicit_menu:
                        text='Em que podemos ajudar? Escolha uma opção ou escreva o que você precisa.'
                    else:
                        text='Me conta um pouco mais sobre o que você precisa, assim consigo te orientar.'

                    types={
                        item['tipo'] for item in conn.execute(
                            "SELECT DISTINCT tipo FROM socialmei.crm_produtos WHERE workspace_id=%s AND status='Ativo'",
                            (workspace,)
                        ).fetchall()
                    }

                    ready=booking_available(conn,workspace)
                    general_quick=sm_ig_actions(job_id,types,ready)

                    hints=[]

                    if types:
                        hints.append('consultar nosso catálogo')

                    if ready:
                        hints.append('agendar um horário')

                    hints.append('falar com nossa equipe')

                    text+='\n\nVocê pode '+', '.join(hints[:-1])+(' ou ' if len(hints)>1 else '')+hints[-1]+'.'

                elif result['choices'] and not use_ai:
                    text += '\n\n' + '\n'.join(c['id']+' - '+c['title'] for c in result['choices'])
                text = text.encode('utf-8')[:1000].decode('utf-8', errors='ignore')
            if not text.strip() or any(ord(c)<32 and c not in '\n\r\t' for c in text):
                raise ValueError('Invalid automatic greeting')
        # Persist the full choice reference for a verified follow-up, but never
        # disclose that opaque internal state in a customer-facing Direct.
        outbound_text = instagram_booking_flow.public_text(text)

        if not blocked and booking_plan is not None:
            outbound_text=instagram_booking_flow.format_ig_booking(
                outbound_text,result.get('action')
            )
        if not blocked and not outbound_text.strip():
            raise ValueError('Invalid customer-facing reply')
        token = None if blocked else runtime.direct.vault.open(row['encrypted_token'], TokenBinding(
            workspace, row['connection_id'], row['external_account_id']))
        conn.execute("INSERT INTO socialmei.ig_menu_replies(workspace_id,id,conversation_id,source_message_id,connection_id,external_account_id,recipient_id,text,status,finished_at) "
                     "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                     (workspace, job_id, row['conversation_id'], message, row['connection_id'], row['external_account_id'],
                      row['contact_ref'].split(':')[1], text, 'skipped' if blocked else 'dispatching',
                      datetime.now(timezone.utc) if blocked else None))
        conn.execute('UPDATE socialmei.ig_menu_conversations SET state=%s,revision=revision+1,updated_at=CASE WHEN workspace_id IN (60,61) AND state=\'human\' AND %s=\'human\' THEN updated_at ELSE NOW() END, '
                     'last_message_id=%s,last_occurred_at=%s '
                     'WHERE workspace_id=%s AND conversation_id=%s',
                     (state['state'] if stale else ('human' if pending else new_state),
                      state['state'] if stale else ('human' if pending else new_state),
                      state['last_message_id'] if stale else message,
                      state['last_occurred_at'] if stale else row['occurred_at'], workspace, row['conversation_id']))
    if blocked:
        return 'skipped'
    status, receipt = 'uncertain', None
    try:
        quick=[q for _,q in instagram_booking_flow.quick_options(text,job_id)] if workspace in (60,61) and booking_plan is not None else general_quick

        args=(token,row['external_account_id'],row['contact_ref'].split(':')[1],outbound_text)

        if quick:
            try:
                sent=runtime.direct.adapter.send_direct(*args,quick_replies=quick)
            except ProviderError as error:
                if error.status_code!=400 or error.outcome_unknown:
                    raise

                sent=runtime.direct.adapter.send_direct(*args)
        else:
            sent=runtime.direct.adapter.send_direct(*args)
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



import unicodedata

def _sm_menu_norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value or '').casefold()) if not unicodedata.combining(c)).strip(' !?.,')

def _sm_menu_personalize(workspace,state,result):
    if workspace not in (60,61) or state=='human' or result.get('handoff') or result.get('action')!='menu' or not result.get('text'):
        return result

    out=dict(result)

    if workspace==60:
        out['text']='Olá! Você está falando com a Brilho&Limpeza Service. Como podemos ajudar com a limpeza do seu ambiente?'
    else:
        out['text']='Olá! Seja bem-vindo(a) à Bella Store. Podemos ajudar você a encontrar uma peça ou acessório e consultar a disponibilidade com nossa equipe.'

    choices=[]

    for choice in result.get('choices',[]):
        title=_sm_menu_norm(choice.get('title'))

        if workspace==60 and ('produto' in title or 'preco e disponibilidade' in title):
            continue

        if workspace==61 and ('servico' in title or 'orcamento' in title):
            continue

        choices.append(choice)

    if choices:
        out['choices']=choices

    return out

def _sm_ig_input(workspace,state,text):
    if workspace not in (60,61) or state!='menu':
        return text

    t=_sm_menu_norm(text)

    if workspace==60 and t in ('1','2','servicos','conhecer servicos','precos','preco','valores','valor'):
        return '3'

    if workspace==61 and t in ('produtos','catalogo','ver produtos'):
        return '1'

    if workspace==61 and t in ('precos','preco','valores','valor'):
        return '2'

    if t in ('atendente','humano','falar com atendente','falar com a equipe'):
        return '5'

    return text


_sm_original_ig_answer = answer

def answer(conn, workspace, state, text):
    next_state, result = _sm_original_ig_answer(conn,workspace,state,_sm_ig_input(workspace,state,text))
    return next_state,_sm_menu_personalize(workspace,state,result)
