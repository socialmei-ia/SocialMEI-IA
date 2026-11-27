"""Durable replies for verified WAHA inputs. This module never sends a message."""
import os
import whatsapp_catalog_navigation as navigation
import re
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from account_auth import require_enabled
from database import connect
from whatsapp_catalog import ChannelAccess, _TOKEN, issue_secret, product_view, require_owner, token_digest
import settings
from whatsapp_menu_ux import WELCOME_TEXT, ASK_PRODUCT_TEXT, canonical_choice, text_menu
from omnichannel_menu_policy import explicit_menu_action

router = APIRouter(tags=['WhatsApp conversation planning'])
INTERNAL = '/internal/whatsapp/bot'
OPTIONS = [
    {'id': '1', 'title': 'Ver produtos'},
    {'id': '2', 'title': 'Preço e disponibilidade'},
    {'id': '3', 'title': 'Conhecer serviços'},
    {'id': '4', 'title': 'Solicitar orçamento'},
    {'id': '5', 'title': 'Falar com atendente'},
]
HUMAN_CHOICES = {'4', '5', 'atendente', 'humano', 'falar com atendente'}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Source(Strict):
    instance: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
    external_message_id: str = Field(pattern=r'^[!-~]{1,1024}$')


class Receipt(Strict):
    status: Literal['confirmed', 'uncertain']
    provider_message_id: str | None = Field(default=None, pattern=r'^[!-~]{1,1024}$')

    @model_validator(mode='after')
    def confirmed_identity(self):
        if (self.status == 'confirmed') != (self.provider_message_id is not None):
            raise ValueError('Confirmação exige identificação do provedor.')
        return self


def enabled():
    return (
        not settings.waha_workspace_inbox_requested()
        and os.getenv('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'false').strip().lower() == 'true'
    )


def require_bot():
    if not enabled():
        raise HTTPException(503, 'Atendimento WhatsApp ainda não habilitado.')
    require_enabled()


def authorize(conn, request):
    require_bot()
    values = request.headers.getlist('authorization')
    scheme, _, token = (values[0] if len(values) == 1 else '').partition(' ')
    if scheme.lower() != 'bearer' or not _TOKEN.fullmatch(token):
        raise HTTPException(401, 'Credencial de atendimento inválida.')
    row = conn.execute(
        "SELECT a.workspace_id,a.channel_id,a.binding_hash,c.instancia,c.sessao,c.identificador_conta,c.versao "
        "FROM socialmei.wa_bot_access a JOIN socialmei.crm_canais c "
        "ON c.workspace_id=a.workspace_id AND c.id=a.channel_id "
        "WHERE a.token_hash=%s AND c.ativo AND c.ingress_provisioned AND c.provedor='waha' "
        "AND NOT c.envio_habilitado FOR SHARE OF a,c", (token_digest(token),),
    ).fetchone()
    if not row or row['binding_hash'] != binding_hash(row):
        raise HTTPException(401, 'Credencial de atendimento inválida.')
    if (
        os.getenv("SOCIALMEI_WAHA_PILOT_BINDING_SHA256")
        and not _reviewed_channel(row)
    ):
        raise HTTPException(
            401,"Credencial fora do vinculo autorizado."
        )
    return row


def binding_hash(channel):
    fields = [channel[key] for key in ('workspace_id', 'channel_id', 'instancia', 'sessao', 'identificador_conta', 'versao')]
    return hashlib.sha256(json.dumps(fields, separators=(',', ':')).encode()).hexdigest()


def configure(conn):
    conn.row_factory = dict_row
    conn.execute("SET LOCAL lock_timeout='3s'")
    conn.execute("SET LOCAL statement_timeout='5s'")


@contextmanager
def operation_database():
    try:
        with connect() as conn:
            configure(conn)
            yield conn
    except psycopg.Error:
        raise HTTPException(503, 'Atendimento temporariamente indisponível. Não repita envios incertos.') from None


def view(row):
    return {**row['result'], 'operation_id': str(row['id']), 'status': row['status'],
            'source_message_id': row['source_message_id'], 'conversation_id': row['conversation_id']}


def _catalog_answer(conn, workspace, state, text, target, enabled):
    if not enabled or state == 'human':
        return answer(conn, workspace, state, text)
    if target is not None:
        return navigation.respond(conn, workspace, target)
    command = globals().get('canonical_choice', lambda value: value.strip().casefold())(text)
    routes = {'0': {'route':'main'}, '1': {'route':'browse','kind':'Produto'},
              '2': {'route':'browse','kind':'Produto'}, '3': {'route':'browse','kind':'Serviço'},
              '4': {'route':'quote'}, '5': {'route':'human'}}
    if state == 'ask_product' and command not in routes:
        return navigation.browse(conn, workspace, {'route':'browse','kind':'Produto','query':text})
    return navigation.respond(conn, workspace, routes.get(command, {'route':'main'}))



def _reviewed_channel(channel):
    if os.getenv("SOCIALMEI_WAHA_PILOT_BINDING_SHA256"):
        return settings.waha_pilot_binding_allowed(
            channel["workspace_id"],
            channel["channel_id"],
            channel["instancia"],
            channel["sessao"],
            channel["identificador_conta"],
            channel["versao"],
            os.getenv("SOCIALMEI_MENU_WAHA_ENGINE","WEBJS")
        )
    return (
        channel["workspace_id"],
        channel["channel_id"],
        channel["instancia"],
        channel["sessao"]
    ) == (1,1,"socialmei-equipe-piloto","01")


def native_list_canary(channel,contact):
    if not _public_direct(contact):
        return False

    if os.getenv("SOCIALMEI_MENU_WAHA_ENGINE")!="GOWS":
        return False

    if not _reviewed_channel(channel):
        return False

    public=(
        os.getenv("SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE")=="YES"
        and os.getenv("SOCIALMEI_PUBLIC_MENU_EXPLICIT_ENABLE")=="YES"
        and _public_contacts(channel) is None
    )

    canary=(
        os.getenv("SOCIALMEI_MENU_GOWS_LIST_CANARY_ACTIVE")=="YES"
        and contact in navigation.configured_contacts(os.environ)
    )

    return public or canary


def render_waha(session, chat, text, choices, *, engine='WEBJS', list_verified=False, action=None, business_name=None):
    """Construct a payload, not an HTTP call. Text is the verified default."""
    labels = {'booking_review': ('Agendamento', 'Confirmar ou alterar', 'O que deseja fazer?'),
              'booking_slots': ('Horários disponíveis', 'Escolher horário', 'Horários'),
              'booking_services': ('Nossos serviços', 'Escolher serviço', 'Serviços'),
              'booking_days': ('Datas disponíveis', 'Escolher data', 'Datas'),
              'booking_resources': ('Atendimento', 'Escolher equipe', 'Equipes')}
    title, button, section = labels.get(action, ('Atendimento', 'Ver opções', 'Como podemos ajudar?'))
    footer = ' '.join(str(business_name or 'SocialMEI').split())[:60]
    if choices and list_verified and engine in {'GOWS', 'NOWEB'}:
        return {'path': '/api/sendList', 'body': {'session': session, 'chatId': chat, 'message': {
            'title': title, 'description': text, 'footer': footer, 'button': button,
            'sections': [{'title': section, 'rows': [
                {'rowId': c['id'], 'title': c['title'], 'description': c.get('description')} for c in choices
            ]}],
        }}}
    return {'path': '/api/sendText', 'body': {'session': session, 'chatId': chat,
                                             'text': text_menu(text, choices)}}


def answer(conn, workspace, state, text):
    text = text if isinstance(text, str) else ''
    choice = canonical_choice(text)
    result = {'action': 'menu', 'text': WELCOME_TEXT,
              'choices': OPTIONS, 'items': [], 'handoff': False}
    if state == 'human':
        return 'human', {**result, 'action': 'human_wait', 'text': '', 'choices': [], 'handoff': True}
    if choice in HUMAN_CHOICES:
        return 'human', {**result, 'action': 'quote_handoff' if choice == '4' else 'human_handoff',
                         'text': 'Seu pedido ficou registrado nesta conversa para um atendente. Aguarde o atendimento.',
                         'choices': [], 'handoff': True}
    if choice in {'0', 'menu', 'início', 'inicio'}:
        return 'menu', result
    if choice == '2':
        return 'ask_product', {**result, 'action': 'ask_product', 'text': ASK_PRODUCT_TEXT,
                               'choices': []}
    if choice not in {'1', '3'} and state != 'ask_product':
        return 'menu', result
    if state == 'ask_product' and not text.strip():
        return 'ask_product', {**result, 'action': 'ask_product', 'text': ASK_PRODUCT_TEXT, 'choices': []}
    query = text.strip() if choice not in {'1', '3'} else ''
    if query and (len(query) < 2 or len(query) > 160):
        return 'ask_product', {**result, 'action': 'ask_product', 'text': 'Informe o nome do produto (2 a 160 caracteres).',
                               'choices': []}
    kind = 'Serviço' if choice == '3' else 'Produto'
    rows = conn.execute(
        "SELECT nome,tipo,preco,estoque FROM socialmei.crm_produtos "
        "WHERE workspace_id=%s AND status='Ativo' AND tipo=%s "
        "AND (%s='' OR strpos(lower(nome),lower(%s))>0) ORDER BY nome,id LIMIT 10",
        (workspace, kind, query, query),
    ).fetchall()
    items = [product_view(row) for row in rows]
    lines = []
    for item in items:
        price = format(Decimal(item['preco']), '.2f').replace('.', ',')
        line = item['nome'] + '\nPreço: R$ ' + price
        if item['tipo'] == 'Produto':
            if item['disponibilidade'] == 'em_estoque':
                quantity = item['estoque']
                unit = 'unidade' if quantity == 1 else 'unidades'
                line += f'\nDisponibilidade: {quantity} {unit}'
            else:
                line += '\nDisponibilidade: a confirmar'
        lines.append(line)
    return 'menu', {**result, 'action': 'services' if choice == '3' else 'availability' if query else 'products',
                    'items': items, 'choices': [], 'text': ('\n\n'.join(lines) +
                    '\n\nPara solicitar um orçamento, digite 4. Para falar com um atendente, digite 5. Para voltar ao menu, digite 0.')
                    if items else (
                        'Não encontrei um produto com esse nome no catálogo ativo. '
                        'Digite 5 para falar com atendente ou 0 para o menu.'
                        if query else
                        ('Ainda não há serviços ativos disponíveis para consulta por aqui. '
                         if choice == '3' else
                         'Ainda não há produtos ativos disponíveis para consulta por aqui. ')
                        + 'Digite 5 para falar com atendente ou 0 para o menu.'
                    )}


@router.get('/api/v1/whatsapp/bot/preview')
def preview(response: Response, opcao: Literal['0', '1', '2', '3', '4', '5'] = Query('0'),
            produto: str = Query('', max_length=160)):
    """Preview the existing bot logic with this owner's real catalog; never send or persist."""
    user = require_owner()
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    query = produto.strip()
    if '\x00' in query or (query and opcao != '2'):
        raise HTTPException(422, 'Consulta inválida.')
    with connect() as conn:
        conn.row_factory = dict_row
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='3000ms'")
        _, result = answer(
            conn, user['workspace_id'],
            'ask_product' if opcao == '2' and query else 'menu',
            query if opcao == '2' and query else opcao,
        )
    rendered = render_waha('preview', 'preview@c.us', result['text'], result['choices'])
    return {
        'preview_only': True, 'send_enabled': False,
        'action': result['action'], 'text': rendered['body']['text'],
        'choices': result['choices'], 'items': result['items'],
        'handoff': result['handoff'],
    }


@router.post('/api/v1/whatsapp/bot/access')
def provision(data: ChannelAccess):
    user = require_owner()
    token = issue_secret()
    with connect() as conn:
        conn.row_factory = dict_row
        row = conn.execute("SELECT workspace_id,id AS channel_id,instancia,sessao,identificador_conta,versao "
                           "FROM socialmei.crm_canais WHERE workspace_id=%s AND id=%s "
                           "AND provedor='waha' AND ativo FOR UPDATE", (user['workspace_id'], data.channel_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Canal ativo não encontrado neste negócio.')
        conn.execute("INSERT INTO socialmei.wa_bot_access(workspace_id,channel_id,token_hash,binding_hash,issued_by) VALUES(%s,%s,%s,%s,%s) "
                     "ON CONFLICT(workspace_id,channel_id) DO UPDATE SET token_hash=EXCLUDED.token_hash,"
                     "binding_hash=EXCLUDED.binding_hash,issued_by=EXCLUDED.issued_by,issued_at=NOW()",
                     (user['workspace_id'], data.channel_id, token_digest(token), binding_hash(row), user['id']))
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_bot_rotated')", (user['id'],))
    return {'channel_id': data.channel_id, 'token_once': token}


@router.get('/api/v1/whatsapp/bot/access')
def status():
    user = require_owner()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute("SELECT c.id AS channel_id,c.instancia AS instance,c.ativo AS active,"
                            "c.ingress_provisioned,(a.channel_id IS NOT NULL) AS credential_configured "
                            "FROM socialmei.crm_canais c LEFT JOIN socialmei.wa_bot_access a "
                            "ON a.workspace_id=c.workspace_id AND a.channel_id=c.id "
                            "WHERE c.workspace_id=%s ORDER BY c.id LIMIT 100", (user['workspace_id'],)).fetchall()
    return {'enabled': enabled(), 'transport': 'none', 'channels': rows}


@router.delete('/api/v1/whatsapp/bot/access/{channel_id}', status_code=204)
def revoke(channel_id: int):
    user = require_owner()
    with connect() as conn:
        row = conn.execute("DELETE FROM socialmei.wa_bot_access WHERE workspace_id=%s AND channel_id=%s RETURNING channel_id",
                           (user['workspace_id'], channel_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Credencial não encontrada.')
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_bot_revoked')", (user['id'],))


@router.post('/api/v1/whatsapp/bot/conversations/{conversation_id}/resume', status_code=204)
def resume(conversation_id: int, payload: ChannelAccess):
    user = require_owner()
    with operation_database() as conn:
        if conversation_channel(conn, user['workspace_id'], conversation_id) != payload.channel_id:
            raise HTTPException(404, 'Canal não encontrado nesta conversa.')
        # Serialize against the human claim before allowing automation again.
        conn.execute("SELECT conversation_id FROM socialmei.wa_bot_conversations "
                     "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s FOR UPDATE",
                     (user['workspace_id'], payload.channel_id, conversation_id)).fetchone()
        if pending_human_reply(conn, user['workspace_id'], payload.channel_id, conversation_id):
            raise HTTPException(409, 'Existe resposta humana iniciada ou incerta. Concilie antes de retomar o bot.')
        row = conn.execute("UPDATE socialmei.wa_bot_conversations SET state='menu',revision=revision+1,updated_at=NOW() "
                           "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s RETURNING conversation_id",
                           (user['workspace_id'], payload.channel_id, conversation_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Conversa não encontrada.')
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_bot_resumed')", (user['id'],))


def pending_human_reply(conn, workspace, channel, conversation, source_id=None):
    if conn.execute("SELECT to_regclass('socialmei.wa_human_replies') AS relation").fetchone()['relation'] is None:
        return False

    return conn.execute("""
        SELECT EXISTS(
            SELECT 1 FROM socialmei.wa_human_replies h
            WHERE h.workspace_id=%s
            AND h.channel_id=%s
            AND h.conversation_id=%s
            AND (
                h.status='dispatching'
                OR (
                    h.status='uncertain'
                    AND (
                        h.workspace_id<>60
                        OR h.finished_at IS NULL
                        OR h.finished_at>NOW()-INTERVAL '2 minutes'
                        OR (
                            %s::bigint IS NOT NULL
                            AND NOT EXISTS (
                                SELECT 1 FROM socialmei.me_messages m
                                JOIN socialmei.crm_eventos_canal e
                                  ON e.workspace_id=m.workspace_id
                                  AND e.inbox_message_id=m.id
                                WHERE m.workspace_id=h.workspace_id
                                AND m.conversation_id=h.conversation_id
                                AND m.id=%s
                                AND m.origin='waha'
                                AND e.canal_id=h.channel_id
                                AND e.tipo='message'
                                AND e.status='processado'
                                AND m.id<>h.source_message_id
                                AND m.occurred_at>h.finished_at
                            )
                        )
                    )
                )
            )
        ) AS pending
    """,(workspace,channel,conversation,source_id,source_id)
    ).fetchone()['pending']


def conversation_channel(conn, workspace, conversation_id):
    rows = conn.execute(
        "SELECT c.id AS channel_id FROM socialmei.crm_canais c "
        "JOIN socialmei.me_conversations v ON v.workspace_id=c.workspace_id "
        "AND v.account_ref='waha:' || c.identificador_conta "
        "WHERE c.workspace_id=%s AND v.id=%s AND v.origin='waha' "
        "AND c.provedor='waha' AND c.ativo AND c.ingress_provisioned "
        "FOR SHARE OF c,v", (workspace, conversation_id),
    ).fetchall()
    if len(rows) != 1:
        raise HTTPException(404, 'Conversa WhatsApp ativa não encontrada neste negócio.')
    return rows[0]['channel_id']


@router.get('/api/v1/whatsapp/bot/conversations/{conversation_id}/status')
def conversation_status(conversation_id: int):
    user = require_owner()
    with operation_database() as conn:
        workspace = user['workspace_id']
        cid = conversation_channel(conn, workspace, conversation_id)
        state = conn.execute("SELECT state FROM socialmei.wa_bot_conversations "
                             "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s",
                             (workspace, cid, conversation_id)).fetchone()
        claimed = conn.execute("SELECT EXISTS(SELECT 1 FROM socialmei.wa_bot_decisions "
                               "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s "
                               "AND status='claimed') AS pending",
                               (workspace, cid, conversation_id)).fetchone()['pending']
    return {'channel_id': cid, 'state': state['state'] if state else 'menu',
            'enabled': enabled(), 'claimed_in_flight': claimed}


@router.post('/api/v1/whatsapp/bot/conversations/{conversation_id}/pause', status_code=204)
def pause(conversation_id: int, payload: ChannelAccess):
    user = require_owner()
    with operation_database() as conn:
        workspace = user['workspace_id']
        cid = conversation_channel(conn, workspace, conversation_id)
        if cid != payload.channel_id:
            raise HTTPException(404, 'Canal não encontrado nesta conversa.')
        # Same unique row/lock as prepare(), including pause before the first decision.
        conn.execute("INSERT INTO socialmei.wa_bot_conversations(workspace_id,channel_id,conversation_id,state,revision) "
                     "VALUES(%s,%s,%s,'human',1) ON CONFLICT(workspace_id,channel_id,conversation_id) "
                     "DO UPDATE SET state='human',revision=wa_bot_conversations.revision+1,updated_at=NOW()",
                     (workspace, cid, conversation_id))
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_bot_paused')", (user['id'],))


@router.get('/api/v1/whatsapp/bot/conversations')
def conversations():
    user = require_owner()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute("SELECT channel_id,conversation_id,state,revision,updated_at "
                            "FROM socialmei.wa_bot_conversations WHERE workspace_id=%s "
                            "ORDER BY updated_at DESC,conversation_id DESC LIMIT 100", (user['workspace_id'],)).fetchall()
    return {'items': rows}


@router.get('/api/v1/whatsapp/bot/decisions')
def history():
    user = require_owner()
    with connect() as conn:
        conn.row_factory = dict_row
        rows = conn.execute("SELECT * FROM socialmei.wa_bot_decisions WHERE workspace_id=%s "
                            "ORDER BY created_at DESC,id DESC LIMIT 100", (user['workspace_id'],)).fetchall()
    return {'items': [{**view(row), 'provider_message_id': row['provider_message_id']} for row in rows]}


@router.get(INTERNAL + '/sources')
def sources(request: Request):
    require_bot()
    with operation_database() as conn:
        channel = authorize(conn, request)
        contacts = _public_contacts(channel)
        rows = conn.execute(
            "SELECT e.mensagem_externa_id AS external_message_id FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id "
            "AND m.origin='waha' JOIN socialmei.me_conversations v "
            "ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_decisions d ON d.workspace_id=e.workspace_id "
            "AND d.channel_id=e.canal_id AND d.source_message_id=m.id "
            "LEFT JOIN socialmei.wa_bot_conversations s ON s.workspace_id=e.workspace_id "
            "AND s.channel_id=e.canal_id AND s.conversation_id=m.conversation_id "
            "WHERE e.workspace_id=%s AND e.canal_id=%s AND e.tipo='message' AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s "
            "AND v.contact_ref ~ '^waha:([0-9]{1,40}@c[.]us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)$' AND (%s OR v.contact_ref=ANY(%s)) "
            "AND m.occurred_at>=NOW()-INTERVAL '15 minutes' AND m.occurred_at<=NOW()+INTERVAL '1 minute' "
            "AND (d.id IS NULL OR (d.status='planned' AND d.created_at>NOW()-INTERVAL '2 minutes' "
            "AND d.binding_hash=%s AND d.state_revision=s.revision)) "
            "ORDER BY m.occurred_at,m.id LIMIT 50",
            (channel['workspace_id'], channel['channel_id'], channel['identificador_conta'],
             'waha:' + channel['identificador_conta'], contacts is None, list(contacts or []),
             channel['binding_hash']),
        ).fetchall()
    return {'sources': [{'instance': channel['instancia'], **row} for row in rows]}



def _everson_original_prepare(payload: Source, request: Request):
    require_bot()
    with operation_database() as conn:
        channel = authorize(conn, request)
        if payload.instance != channel['instancia']:
            raise HTTPException(401, 'Credencial de atendimento inválida.')
        workspace, cid = channel['workspace_id'], channel['channel_id']
        message = conn.execute(
            "SELECT m.*,v.contact_ref,e.recebido_em AS batch_received_at,e.dados_normalizados AS ingress_data FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id AND m.origin='waha' "
            "JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "WHERE e.workspace_id=%s AND e.canal_id=%s AND e.mensagem_externa_id=%s AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s AND e.tipo='message'",
            (workspace, cid, payload.external_message_id, channel['identificador_conta'], 'waha:' + channel['identificador_conta']),
        ).fetchone()
        if not message:
            raise HTTPException(404, 'Mensagem recebida não encontrada neste canal.')
        if not _public_direct(message["contact_ref"]):
            raise HTTPException(403,"Contato individual exigido.")
        contacts = _public_contacts(channel)
        if contacts is not None and message['contact_ref'] not in contacts:
            raise HTTPException(403, 'Contato não autorizado para este piloto.')
        conv = message['conversation_id']
        conn.execute("INSERT INTO socialmei.wa_bot_conversations(workspace_id,channel_id,conversation_id) VALUES(%s,%s,%s) "
                     "ON CONFLICT DO NOTHING", (workspace, cid, conv))
        state = conn.execute("SELECT * FROM socialmei.wa_bot_conversations WHERE workspace_id=%s AND channel_id=%s "
                             "AND conversation_id=%s FOR UPDATE", (workspace, cid, conv)).fetchone()
        existing = conn.execute("SELECT * FROM socialmei.wa_bot_decisions WHERE workspace_id=%s AND channel_id=%s AND source_message_id=%s",
                                (workspace, cid, message['id'])).fetchone()
        if existing:
            return view(existing)
        nav_enabled = native_list_canary(channel, message['contact_ref'])
        metadata = message.get('ingress_data') or {}
        token = metadata.get('wa_selection')
        if nav_enabled and navigation.valid_token(token):
            message['catalog_target'] = navigation.resolve(conn, channel, conv, token)
            if message['catalog_target'].get('route') == 'resume' and not pending_human_reply(conn, workspace, cid, conv, message['id']):
                message['text'] = '0'
                state['state'] = 'menu'
        now = datetime.now(timezone.utc)
        old = message['occurred_at'] < now - timedelta(minutes=15) or message['occurred_at'] > now + timedelta(minutes=1)
        outdated = state['last_occurred_at'] is not None and (message['occurred_at'], message['id']) < (state['last_occurred_at'], state['last_message_id'])
        if old or outdated:
            next_state = state['state']
            result = {'action': 'stale_message', 'text': '', 'choices': [], 'items': [], 'handoff': state['state'] == 'human'}
        else:
            recent = conn.execute("SELECT count(*) AS n FROM (SELECT 1 FROM socialmei.wa_bot_decisions "
                                  "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s "
                                  "AND created_at>NOW()-INTERVAL '1 minute' AND status<>'skipped' LIMIT 20) limited",
                                  (workspace, cid, conv)).fetchone()['n']
            if recent >= 20 and state['state'] != 'human' and str(message['text'] or '').strip().casefold() not in HUMAN_CHOICES:
                next_state = state['state']
                result = {'action': 'rate_limited', 'text': '', 'choices': [], 'items': [], 'handoff': False}
            else:
                # Nao repetir boas-vindas para varias mensagens livres seguidas.
                # Escolhas explicitas e pedidos de humano continuam imediatos.
                booking_result = _sm_booking_route(
                    conn, channel, message, state, native=nav_enabled)
                if booking_result is not None:
                    next_state, result = booking_result
                else:
                    latest_menu = conn.execute(
                        "SELECT 1 FROM socialmei.wa_bot_decisions "
                        "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s "
                        "AND status IN ('planned','claimed','confirmed','uncertain') "
                        "AND result->>'action'='menu' "
                        "AND created_at>NOW()-INTERVAL '60 seconds' "
                        "ORDER BY created_at DESC LIMIT 1",
                        (workspace, cid, conv),
                    ).fetchone()
                    if (((state['state'] == 'menu' and latest_menu and (not (explicit_menu_action(message['text']) or message.get('catalog_target') is not None)) and not _everson_continue_after_menu(conn,channel,message,conv)) and (workspace != 60 or cid != 3 or _socialmei_repeat_greeting(message['text']) or pending_human_reply(conn, workspace, cid, conv)))):
                        next_state = state['state']
                        result = {'action': 'quiet_repeat', 'text': '', 'choices': [],
                                  'items': [], 'handoff': False}
                    else:
                        # Na API ISOLADA do beta, somente uma solicitacao EXPLICITA
                        # do proprio cliente pode retomar uma conversa humana.
                    # Nunca reativar o bot com 'Oi' e nunca interromper uma
                    # resposta humana que ja esteja em despacho/incerta.
                        text_for_resume = str(message['text'] or '').strip().casefold()
                        allowed_resume = (
                            state['state'] == 'human'
                            and text_for_resume in {'menu', 'menu principal', '0'}
                            and (message.get('catalog_target') is None or message['catalog_target'].get('route') == 'resume')
                            and not pending_human_reply(conn, workspace, cid, conv)
                        )
                        next_state, result = _catalog_answer(
                            conn, workspace, 'menu' if allowed_resume else state['state'],
                            message['text']
                        , message.get('catalog_target'), nav_enabled)
                    result = _sm_booking_menu(conn, channel, message, state, result)
        grouped=[]
        last_message=message

        if not old and not outdated and next_state=='menu':
            try:
                with conn.transaction():
                    group=_sm_batch_try_group(
                        conn,channel,message,state,
                        nav_enabled,result
                    )
            except Exception:
                print('BATCH_GROUP_FALLBACK',flush=True)
                group=None

            if group:
                answer,grouped=group
                last_message=grouped[-1]

                result=dict(result)
                result['text']=answer
                result['choices']=[]
                result['items']=[]
                result.pop('catalog_navigation',None)
                result['grouped_source_ids']=[
                    message['id'],
                    *[item['id'] for item in grouped]
                ]
                result['grouped_catalog_answer']=True

        revision = state['revision'] + (0 if old or outdated else 1)
        if not old and not outdated:
            conn.execute("UPDATE socialmei.wa_bot_conversations SET state=%s,revision=%s,"
                     "last_message_id=%s,last_occurred_at=%s,updated_at=CASE WHEN workspace_id=60 AND state='human' AND %s='human' THEN updated_at ELSE NOW() END "
                     "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s",
                     (next_state, revision, last_message['id'], last_message['occurred_at'], next_state, workspace, cid, conv))
        row = conn.execute("INSERT INTO socialmei.wa_bot_decisions(id,workspace_id,channel_id,conversation_id,source_message_id,binding_hash,state_revision,result,status) "
                           "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                           (uuid4(), workspace, cid, conv, message['id'], channel['binding_hash'], max(1, revision), Jsonb(result), 'planned' if result['text'] else 'skipped')).fetchone()
        for item in grouped:
            conn.execute(
                "INSERT INTO socialmei.wa_bot_decisions("
                "id,workspace_id,channel_id,conversation_id,"
                "source_message_id,binding_hash,state_revision,"
                "result,status) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),workspace,cid,conv,
                    item['id'],channel['binding_hash'],
                    max(1,revision),
                    Jsonb({
                        'action':'grouped_message',
                        'text':'',
                        'choices':[],
                        'items':[],
                        'handoff':False,
                        'parent_operation':str(row['id'])
                    }),
                    'skipped'
                )
            )

        if grouped:
            print(
                'CATALOG_GROUP_PREPARED',
                len(grouped)+1,flush=True
            )

        return view(row)




def _public_direct(contact):
    return (
        isinstance(contact,str)
        and re.fullmatch(
            r"waha:(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)",
            contact
        ) is not None
    )


def _public_contacts(channel):
    if (
        _reviewed_channel(channel)
        and enabled()
        and os.getenv("SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE")=="YES"
        and os.getenv("SOCIALMEI_PUBLIC_MENU_EXPLICIT_ENABLE")=="YES"
    ):
        return None

    return settings.whatsapp_bot_allowed_contacts()


def _everson_text(value):
    if not isinstance(value,str):
        return None

    text=value.strip()

    if not 2<=len(text)<=500:
        return None

    choice=text.casefold()

    if choice in {
        "menu","inicio","início","voltar","sair",
        "cancelar","atendente","humano",
        "falar com atendente","agendar","agendamento"
    }:
        return None

    if choice.startswith("sm:") or choice.isdigit():
        return None

    greetings={
        "oi","ola","olá","bom dia",
        "boa tarde","boa noite","opa"
    }

    if choice not in greetings and canonical_choice(text) in {
        "0","1","2","3","4","5","6","7","8","9"
    }:
        return None

    if re.search(
        r"\b(cpf|cnpj|senha|pix|cartao|cartão|rg)\b",
        text,re.I
    ):
        return None

    if re.search(
        r"(?:\d[\s()./+:-]*){5,}|"
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        text
    ):
        return None

    return text


def _everson_context(conn,channel,row,cfg):
    if not _reviewed_channel(channel):
        return None

    if row["status"]!="planned":
        return None

    if row["result"].get("action")!="menu":
        return None

    if not row["result"].get("catalog_navigation"):
        return None

    if not row["result"].get("choices"):
        return None

    state=conn.execute(
        "SELECT s.state,s.revision,v.contact_ref,"
        "m.text,m.occurred_at "
        "FROM socialmei.wa_bot_conversations s "
        "JOIN socialmei.me_conversations v "
        "ON v.workspace_id=s.workspace_id "
        "AND v.id=s.conversation_id "
        "JOIN socialmei.me_messages m "
        "ON m.workspace_id=s.workspace_id "
        "AND m.conversation_id=s.conversation_id "
        "AND m.id=%s AND m.origin='waha' "
        "WHERE s.workspace_id=%s AND s.channel_id=%s "
        "AND s.conversation_id=%s "
        "AND NOT EXISTS ("
        "SELECT 1 FROM socialmei.crm_eventos_canal e "
        "WHERE e.workspace_id=m.workspace_id "
        "AND e.inbox_message_id=m.id "
        "AND COALESCE(e.dados_normalizados->>'wa_selection','')<>''"
        ") FOR SHARE OF s",
        (
            row["source_message_id"],
            channel["workspace_id"],
            channel["channel_id"],
            row["conversation_id"]
        )
    ).fetchone()

    if not state:
        return None

    now=datetime.now(timezone.utc)

    if not (
        state["state"]=="menu"
        and state["revision"]==row["state_revision"]
        and native_list_canary(channel,state["contact_ref"])
        and state["occurred_at"]>=datetime.fromisoformat(
            cfg["enabled_at"]
        )
        and row["created_at"]>now-timedelta(minutes=2)
        and not row["result"].get("handoff")
        and not pending_human_reply(
            conn,channel["workspace_id"],
            channel["channel_id"],row["conversation_id"]
        )
    ):
        return None

    return _everson_text(state["text"])


def _everson_generate(planned,request):
    import http.client
    from pathlib import Path

    if planned.get("status")!="planned" or \
       planned.get("action")!="menu":
        return planned

    path = Path("/app/.everson-pilot.private.json")

    if not path.is_file():
        return planned

    cfg = json.loads(path.read_text())


    opid = UUID(str(planned["operation_id"]))
    marker = str(uuid4())

    with operation_database() as conn:
        channel = authorize(conn,request)
        row = locked_decision(conn,channel,opid)

        if row["result"].get("everson_pilot_attempted"):
            return planned

        text=_everson_context(conn,channel,row,cfg)
        if not text:
            return planned

        if channel["workspace_id"] == 60:
            greeting=text.casefold().strip(" !?.,")
            if greeting in {
                "oi","ola","olá","opa","bom dia",
                "boa tarde","boa noite"
            }:
                result=dict(row["result"])
                result["text"]=(
                    "Olá! Seja bem-vindo(a) à "
                    "Brilho&Limpeza Service!\n\n"
                    "Estamos aqui para ajudar você com "
                    "nossas soluções de limpeza. "
                    "Conheça nossos serviços, solicite um "
                    "orçamento ou converse com nossa equipe."
                )
                result["brilho_welcome"]=True

                saved=conn.execute(
                    "UPDATE socialmei.wa_bot_decisions "
                    "SET result=%s WHERE id=%s RETURNING *",
                    (Jsonb(result),opid)
                ).fetchone()

                return view(saved)

            if not (
                cfg.get("workspace_id")==60
                and cfg.get("business_scope_verified") is True
            ):
                return planned



        try:
            with conn.transaction():
                context=_everson_business_context(
                    conn,channel,row,text,marker
                )
        except Exception:
            return planned

        if context is None:
            return planned

        if (
            channel["workspace_id"],
            channel["channel_id"]
        ) == (60,3):
            direct = _socialmei_catalog_answer(context,text)

            if not direct:
                try:
                    with conn.transaction():
                        direct = _socialmei_price_followup(
                            conn,channel,row,context,text
                        )
                except Exception:
                    print(
                        "CATALOG_FOLLOWUP_UNAVAILABLE",
                        flush=True
                    )

            if direct:
                result = _socialmei_direct_result(
                    row["result"], direct
                )
                result["everson_catalog_answered"] = True

                saved = conn.execute(
                    "UPDATE socialmei.wa_bot_decisions "
                    "SET result=%s WHERE id=%s RETURNING *",
                    (Jsonb(result),opid)
                ).fetchone()

                print("CATALOG_DIRECT_ANSWER",flush=True)
                return view(saved)

        lock = conn.execute(
            "SELECT pg_try_advisory_xact_lock(76102401) AS ok"
        ).fetchone()

        if not lock["ok"]:
            return planned

        n = conn.execute(
            "SELECT count(*) AS n FROM socialmei.wa_bot_decisions "
            "WHERE workspace_id=%s AND channel_id=%s "
            "AND created_at>NOW()-INTERVAL '1 minute' "
            "AND result->>'everson_pilot_attempted' IS NOT NULL",
            (channel["workspace_id"],channel["channel_id"])
        ).fetchone()["n"]

        if n>=6:
            return planned

        result = dict(row["result"])
        result["everson_pilot_attempted"] = marker

        conn.execute(
            "UPDATE socialmei.wa_bot_decisions SET result=%s WHERE id=%s",
            (Jsonb(result),opid)
        )

    def fallback(reason):
        print("EVERSON_FALLBACK",reason,flush=True)

        with operation_database() as conn:
            channel = authorize(conn,request)

            if (
                channel["workspace_id"],
                channel["channel_id"]
            ) != (60,3):
                return planned

            row = locked_decision(conn,channel,opid)

            if (
                row["result"].get("everson_pilot_attempted") != marker
                or _everson_context(conn,channel,row,cfg) != text
            ):
                return planned

            answer = _socialmei_catalog_answer(
                context,text,summary=True
            )

            if not answer:
                answer = (
                    "Nao consegui confirmar essa informacao agora. "
                    "Posso ajudar com nossos servicos ou, "
                    "se preferir, voce pode pedir um atendente."
                ).replace("Nao","N\u00e3o").replace(
                    "informacao","informa\u00e7\u00e3o"
                ).replace("servicos","servi\u00e7os").replace(
                    "voce","voc\u00ea"
                )

            result = _socialmei_direct_result(
                row["result"],answer
            )

            result["everson_fallback_reason"] = reason

            saved = conn.execute(
                "UPDATE socialmei.wa_bot_decisions "
                "SET result=%s WHERE id=%s RETURNING *",
                (Jsonb(result),opid)
            ).fetchone()

            return view(saved)

    with __import__('contextlib').nullcontext():
        payload = {
            "event":"message",
            "session":"socialmei-publico",
            "socialmei":context,
            "payload":{
                "id":marker,
                "from":"000000000000@c.us",
                "fromMe":False,
                "body":context["mensagem"],
                "_data":{"Info":{"PushName":"Cliente"}}
            }
        }

        h = http.client.HTTPConnection(
            "socialmei-n8n",5678,timeout=35
        )

        try:
            h.request(
                "POST",cfg["route"],
                body=json.dumps(payload).encode(),
                headers={
                    "Content-Type":"application/json",
                    "X-SocialMEI-Backend":cfg["secret"]
                }
            )

            r = h.getresponse()

            if r.status!=200:
                return fallback("http_error")

            raw = r.read(65537)

            if len(raw)>65536:
                return fallback("response_too_large")

            data = json.loads(raw)
            if isinstance(data,list) and not data:
                return fallback("empty_response")

            item = data[0] if isinstance(data,list) else data

            if not isinstance(item,dict):
                return fallback("invalid_response")

            reply = item.get("reply")

            if not isinstance(reply,str) or \
               not reply.strip() or len(reply)>1024:
                return fallback("invalid_reply")

            if any(
                ord(c)<32 and c not in "\n\r\t"
                or 127<=ord(c)<=159
                for c in reply
            ):
                return fallback("invalid_characters")

        except (OSError,ValueError,TypeError,AttributeError,http.client.HTTPException):
            return fallback("transport_or_parse_error")
        finally:
            h.close()

        with operation_database() as conn:
            channel = authorize(conn,request)
            row = locked_decision(conn,channel,opid)

            if row["result"].get("everson_pilot_attempted")!=marker:
                return planned

            if _everson_context(conn,channel,row,cfg)!=text:
                print("EVERSON_DISCARDED_CONTEXT_CHANGED",flush=True)
                return planned

            result = dict(row["result"])
            result["text"] = reply.strip()
            result["everson_answered"] = True
            try:
                with conn.transaction():
                    result=_everson_apply_interaction(
                        conn,channel,row,text,result
                    )
            except Exception:
                print("EVERSON_INTERACTION_FAILED",flush=True)

                if (channel["workspace_id"],channel["channel_id"]) != (60,3):
                    return planned

                result = _socialmei_direct_result(
                    row["result"],reply
                )
                result["everson_answered"] = True

            if (
                (channel["workspace_id"],channel["channel_id"]) == (60,3)
                and not result.get("everson_list_kind")
            ):
                result = _socialmei_direct_result(
                    result,result["text"]
                )

            result["everson_pilot_attempted"] = marker

            row = conn.execute(
                "UPDATE socialmei.wa_bot_decisions "
                "SET result=%s WHERE id=%s RETURNING *",
                (Jsonb(result),opid)
            ).fetchone()

            return view(row)


@router.post(INTERNAL + "/decisions")
def prepare(payload: Source,request: Request):
    planned = _everson_original_prepare(payload,request)

    try:
        return _everson_generate(planned,request)
    except Exception:
        return planned




def locked_decision(conn, channel, decision_id):
    row = conn.execute("SELECT * FROM socialmei.wa_bot_decisions WHERE workspace_id=%s AND channel_id=%s AND id=%s FOR UPDATE",
                       (channel['workspace_id'], channel['channel_id'], decision_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Operação não encontrada.')
    if row['binding_hash'] != channel['binding_hash']:
        raise HTTPException(409, 'O vínculo do canal mudou. Não repita esta operação.')
    return row


@router.post(INTERNAL + '/decisions/{decision_id}/claim')
def claim(decision_id: UUID, payload: Strict, request: Request):
    require_bot()
    with operation_database() as conn:
        channel = authorize(conn, request)
        row = locked_decision(conn, channel, decision_id)
        state = conn.execute("SELECT s.revision,v.contact_ref FROM socialmei.wa_bot_conversations s "
                             "JOIN socialmei.me_conversations v ON v.workspace_id=s.workspace_id AND v.id=s.conversation_id "
                             "WHERE s.workspace_id=%s AND s.channel_id=%s AND s.conversation_id=%s FOR SHARE OF s",
                             (channel['workspace_id'], channel['channel_id'], row['conversation_id'])).fetchone()
        permitted = row['status'] == 'planned' and row['created_at'] > datetime.now(timezone.utc) - timedelta(minutes=2) and row['state_revision'] == state['revision']
        permitted = permitted and _public_direct(state["contact_ref"])
        contacts = _public_contacts(channel)
        permitted = permitted and (contacts is None or state['contact_ref'] in contacts)
        permitted = permitted and not pending_human_reply(
            conn, channel['workspace_id'], channel['channel_id'], row['conversation_id'], row['source_message_id'])
        permitted = permitted and not conn.execute("SELECT 1 FROM socialmei.wa_bot_decisions q WHERE q.workspace_id=%s AND q.channel_id=%s AND q.conversation_id=%s AND q.status IN ('claimed','uncertain') AND q.id NOT IN ('d095f540-7071-4045-a6d1-6b283e5a15cd'::uuid,'a3da1993-97c3-4856-bfb0-061452a70d57'::uuid) LIMIT 1", (channel['workspace_id'],channel['channel_id'],row['conversation_id'])).fetchone()
        if not permitted:
            return {'operation_id': str(row['id']), 'dispatch_allowed': False, 'status': row['status']}
        conn.execute("UPDATE socialmei.wa_bot_decisions SET status='claimed',claimed_at=NOW() WHERE id=%s", (decision_id,))
        delivery = render_waha(channel['sessao'], state['contact_ref'].removeprefix('waha:'), row['result']['text'], (navigation.offered_choices(row) if row['result'].get('catalog_navigation') else row['result']['choices']), engine='GOWS', list_verified=native_list_canary(channel, state['contact_ref']), action=row['result'].get('action'), business_name='Brilho&Limpeza Service' if channel['workspace_id']==60 else None)
        if (
            channel["workspace_id"],
            channel["channel_id"]
        )==(60,3):
            delivery=_everson_label_delivery(delivery,row)
        return {'operation_id': str(row['id']), 'dispatch_allowed': True, 'status': 'claimed', 'delivery': delivery}



@router.post(INTERNAL + '/decisions/{decision_id}/receipt')
def receipt(decision_id: UUID, payload: Receipt, request: Request):
    require_bot()
    with operation_database() as conn:
        channel = authorize(conn, request)
        row = locked_decision(conn, channel, decision_id)
        if row['status'] in {'confirmed', 'uncertain'}:
            if (row['status'], row['provider_message_id']) != (payload.status, payload.provider_message_id):
                raise HTTPException(409, 'Recibo divergente. Não repita o envio.')
            return view(row)
        if row['status'] != 'claimed':
            raise HTTPException(409, 'Operação ainda não reservada para envio.')
        try:
            row = conn.execute("UPDATE socialmei.wa_bot_decisions SET status=%s,provider_message_id=%s,finished_at=NOW() WHERE id=%s RETURNING *",
                               (payload.status, payload.provider_message_id, decision_id)).fetchone()
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, 'Recibo já utilizado em outra operação.') from None
        return view(row)


def _everson_business_context(conn,channel,row,text,marker):
    import re

    w=channel["workspace_id"]
    cid=channel["channel_id"]

    if (w,cid)!=(60,3):
        return None

    business=conn.execute("""
        SELECT w.nome
        FROM socialmei.workspaces w
        JOIN socialmei.crm_canais c
          ON c.workspace_id=w.id
        WHERE w.id=%s AND c.id=%s
        AND c.provedor='waha'
        AND c.ativo AND c.ingress_provisioned
        AND c.identificador_conta=%s
    """,(w,cid,channel["identificador_conta"])).fetchone()

    if not business:
        return None

    name=business["nome"]

    if "brilho" not in name.casefold() or "limpeza" not in name.casefold():
        return None

    anchor=conn.execute("""
        SELECT m.id,m.conversation_id,m.occurred_at
        FROM socialmei.me_messages m
        JOIN socialmei.me_conversations v
          ON v.workspace_id=m.workspace_id
          AND v.id=m.conversation_id
        WHERE m.workspace_id=%s
        AND m.id=%s AND m.conversation_id=%s
        AND m.origin='waha' AND v.origin='waha'
        AND v.account_ref=%s
        AND EXISTS(
            SELECT 1 FROM socialmei.crm_eventos_canal e
            WHERE e.workspace_id=m.workspace_id
            AND e.inbox_message_id=m.id
            AND e.canal_id=%s
            AND e.tipo='message'
            AND e.status='processado'
            AND e.waha_account_snapshot=%s
        )
    """,(
        w,row["source_message_id"],row["conversation_id"],
        "waha:"+channel["identificador_conta"],
        cid,channel["identificador_conta"]
    )).fetchone()

    if not anchor:
        return None

    conv=anchor["conversation_id"]
    moment=anchor["occurred_at"]
    source=anchor["id"]
    binding=row["binding_hash"]

    rows=conn.execute("""
        WITH history AS (
            SELECT m.occurred_at AS moment,
                   'cliente' AS role,m.text
            FROM socialmei.me_messages m
            WHERE m.workspace_id=%s
            AND m.conversation_id=%s
            AND m.origin='waha'
            AND (m.occurred_at,m.id)<(%s,%s)
            AND EXISTS(
                SELECT 1 FROM socialmei.crm_eventos_canal e
                WHERE e.workspace_id=m.workspace_id
                AND e.inbox_message_id=m.id
                AND e.canal_id=%s
                AND e.tipo='message'
                AND e.status='processado'
                AND e.waha_account_snapshot=%s
            )

            UNION ALL

            SELECT d.finished_at,'assistente',
                   d.result->>'text'
            FROM socialmei.wa_bot_decisions d
            WHERE d.workspace_id=%s
            AND d.channel_id=%s
            AND d.conversation_id=%s
            AND d.binding_hash=%s
            AND d.status='confirmed'

            UNION ALL

            SELECT h.finished_at,'atendente',h.text
            FROM socialmei.wa_human_replies h
            WHERE h.workspace_id=%s
            AND h.channel_id=%s
            AND h.conversation_id=%s
            AND h.binding_hash=%s
            AND h.status='confirmed'
        )
        SELECT role,text
        FROM history
        WHERE moment<=%s
        AND moment>=%s-INTERVAL '48 hours'
        AND text IS NOT NULL
        AND btrim(text)<>''
        ORDER BY moment DESC LIMIT 10
    """,(
        w,conv,moment,source,cid,channel["identificador_conta"],
        w,cid,conv,binding,
        w,cid,conv,binding,
        moment,moment
    )).fetchall()

    def clean(value,limit):
        value=" ".join(str(value).split())

        value=re.sub(
            r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
            "[documento omitido]",value
        )

        value=re.sub(
            r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
            "[documento omitido]",value
        )

        return value[:limit]

    history=[
        {
            "autor":r["role"],
            "mensagem":_sm_context_clean(r["text"],280)
        }
        for r in reversed(rows)
    ]

    products=conn.execute("""
        SELECT nome,tipo,preco
        FROM socialmei.crm_produtos
        WHERE workspace_id=%s
        AND status='Ativo'
        ORDER BY nome,id LIMIT 25
    """,(w,)).fetchall()

    catalog=[
        {
            "nome":clean(p["nome"],100),
            "tipo":clean(p["tipo"],40),
            "preco":str(p["preco"]) if p["preco"] is not None else None
        }
        for p in products
    ]

    return {
        "workspace_id":w,
        "request_id":marker,
        "empresa":name,
        "mensagem":_sm_context_clean(text,1500),
        "historico_recente":history,
        "catalogo":catalog,
        "agendamento_disponivel":_sm_booking_ready(conn,channel)
    }



def _everson_continue_after_menu(conn,channel,message,conv):
    from pathlib import Path

    if (
        channel["workspace_id"],
        channel["channel_id"]
    )!=(60,3):
        return False

    try:
        cfg=json.loads(Path(
            "/app/.everson-pilot.private.json"
        ).read_text())
    except (OSError,ValueError):
        return False

    if not (
        cfg.get("workspace_id")==60
        and cfg.get("channel_id")==3
        and cfg.get("business_scope_verified") is True
    ):
        return False

    text=_everson_text(message["text"])

    if not text:
        return False

    if text.casefold().strip(" !?.,") in {
        "oi","ola","olá","opa",
        "bom dia","boa tarde","boa noite"
    }:
        return False

    scope=(60,3,conv,channel["binding_hash"])

    if conn.execute("""
        SELECT 1
        FROM socialmei.wa_bot_decisions
        WHERE workspace_id=%s AND channel_id=%s
        AND conversation_id=%s AND binding_hash=%s
        AND status IN ('planned','claimed','uncertain')
        LIMIT 1
    """,scope).fetchone():
        return False

    previous=conn.execute("""
        SELECT status,result->>'action' AS action
        FROM socialmei.wa_bot_decisions
        WHERE workspace_id=%s AND channel_id=%s
        AND conversation_id=%s AND binding_hash=%s
        AND status<>'skipped'
        ORDER BY created_at DESC LIMIT 1
    """,scope).fetchone()

    return bool(
        previous
        and previous["status"]=="confirmed"
        and previous["action"]=="menu"
        and not pending_human_reply(
            conn,60,3,conv,message["id"]
        )
    )



def _everson_apply_interaction(conn,channel,row,text,result):
    import re
    import unicodedata

    if (
        channel["workspace_id"],
        channel["channel_id"]
    )!=(60,3):
        return result

    result=dict(result)

    normalized=unicodedata.normalize(
        "NFKD",text.casefold()
    )

    normalized="".join(
        c for c in normalized
        if not unicodedata.combining(c)
    )

    normalized=" ".join(normalized.split())

    kind=None

    for label,value in (
        ("servicos","Servi\u00e7o"),
        ("produtos","Produto")
    ):
        pattern=(
            r"\b(?:quais|que|listar|ver|conhecer|"
            r"mostrar|mostre|consultar)\s+"
            r"(?:sao\s+)?(?:os\s+)?"+label+r"\b"
        )

        other=(
            r"\b(?:lista|catalogo)\s+"
            r"(?:de\s+)?"+label+r"\b"
        )

        if re.search(pattern,normalized) or \
           re.search(other,normalized):
            kind=value
            break

    if kind:
        _,catalog=navigation.browse(
            conn,60,{
                "route":"browse",
                "kind":kind
            }
        )

        choices=catalog.get("choices") or []

        if choices:
            result["choices"]=choices
            result["catalog_navigation"]=True
            result["everson_list_kind"]=kind

            if catalog.get("action")=="catalog_empty":
                result["text"]=catalog["text"]
            elif catalog.get("action")=="categories":
                result["text"]=(
                    "Claro! Escolha uma categoria "
                    "para conhecer nossas op\u00e7\u00f5es."
                )
            elif kind=="Servi\u00e7o":
                result["text"]=(
                    "Claro! Confira nossos *servi\u00e7os*.\n\n"
                    "Selecione uma op\u00e7\u00e3o para consultar "
                    "o pre\u00e7o e os detalhes."
                )
            else:
                result["text"]=(
                    "Claro! Confira nossos *produtos*.\n\n"
                    "Selecione uma op\u00e7\u00e3o para conhecer "
                    "os detalhes."
                )

            return result

    previous=conn.execute("""
        SELECT 1
        FROM socialmei.wa_bot_decisions
        WHERE workspace_id=%s
        AND channel_id=%s
        AND conversation_id=%s
        AND binding_hash=%s
        AND status='confirmed'
        AND result->>'catalog_navigation'='true'
        AND jsonb_typeof(result->'choices')='array'
        AND result->'choices'<>'[]'::jsonb
        AND finished_at>NOW()-INTERVAL '24 hours'
        LIMIT 1
    """,(
        60,3,row["conversation_id"],
        channel["binding_hash"]
    )).fetchone()

    if previous:
        result["choices"]=[]
        result["catalog_navigation"]=False
        result["everson_menu_suppressed"]=True

    return result


def _everson_label_delivery(delivery,row):
    if delivery.get("path")!="/api/sendList":
        return delivery

    result=row["result"]
    action=result.get("action")
    kind=result.get("everson_list_kind")

    title="Atendimento"
    button="Selecionar assunto"
    section="Como podemos ajudar?"

    if kind=="Servi\u00e7o" or action=="services":
        title="Servi\u00e7os"
        button="Escolher servi\u00e7o"
        section="Nossos servi\u00e7os"

    elif kind=="Produto" or action=="products":
        title="Cat\u00e1logo"
        button="Escolher produto"
        section="Nossos produtos"

    elif action=="categories":
        title="Categorias"
        button="Ver categorias"
        section="Escolha uma categoria"

    elif action in {"product_detail","availability"}:
        title="Detalhes"
        button="Como continuar"
        section="O que deseja fazer?"

    elif action in {"quote_handoff","human_handoff"}:
        title="Atendimento"
        button="Op\u00e7\u00f5es de atendimento"
        section="Pr\u00f3ximos passos"

    elif action=="catalog_empty":
        title="Cat\u00e1logo"
        button="Ver alternativas"
        section="Como continuar?"

    message=delivery["body"]["message"]
    message["title"]=title
    message["button"]=button
    message["sections"][0]["title"]=section

    return delivery



def _socialmei_repeat_greeting(text):
    import re
    import unicodedata

    value = unicodedata.normalize(
        "NFKD", str(text or "").casefold()
    )

    value = "".join(
        c for c in value
        if not unicodedata.combining(c)
    )

    value = " ".join(re.findall(r"[a-z0-9]+", value))

    return value in {
        "", "oi", "ola", "opa", "e ai",
        "bom dia", "boa tarde", "boa noite",
        "oi bom dia", "oi boa tarde", "oi boa noite",
        "ola bom dia", "ola boa tarde", "ola boa noite",
        "tudo bem", "oi tudo bem", "ola tudo bem",
        "oi oi", "ola ola"
    }


def _socialmei_catalog_answer(context, text, summary=False):
    import re
    import unicodedata
    from decimal import Decimal, InvalidOperation

    def norm(value):
        value = unicodedata.normalize(
            "NFKD", str(value or "").casefold()
        )
        value = "".join(
            c for c in value
            if not unicodedata.combining(c)
        )
        return " ".join(re.findall(r"[a-z0-9]+", value))

    def money(value):
        try:
            value = str(value).strip().replace("R$", "").strip()
            if "," in value:
                value = value.replace(".", "").replace(",", ".")
            amount = Decimal(value)
            if not amount.is_finite() or amount < 0:
                return None
            if amount != amount.quantize(Decimal("0.01")):
                return None
            formatted = format(amount, ",.2f")
            return "R$ " + formatted.translate(
                str.maketrans(",.", ".,")
            )
        except (InvalidOperation, ValueError, TypeError):
            return None

    if context.get("workspace_id") != 60:
        return None

    catalog = context.get("catalogo")

    if not isinstance(catalog, list):
        return None

    items = []

    for item in catalog:
        if not isinstance(item, dict):
            continue

        name = item.get("nome")
        price = money(item.get("preco"))

        if (
            isinstance(name, str)
            and name.strip()
            and len(name) <= 160
            and price is not None
        ):
            items.append((name.strip(), price))

    q = norm(text)

    price_question = re.search(
        r"\b(?:quanto|preco|valor|custa|custam)\b", q
    )

    if price_question:
        matches = [
            (name, price)
            for name, price in items
            if norm(name) and
            (" " + norm(name) + " ") in (" " + q + " ")
        ]

        if len(matches) == 1:
            name, price = matches[0]
            return (
                f"No nosso catalogo, {name} custa {price}. "
                "Gostaria de saber mais sobre esse servico?"
            ).replace("catalogo", "cat\u00e1logo").replace(
                "servico", "servi\u00e7o"
            )

    if summary and re.search(
        r"\b(?:oferecem|servicos|catalogo|produtos)\b", q
    ) and items:
        lines = [
            f"- {name}: {price}"
            for name, price in items[:10]
        ]
        return (
            "Estas sao algumas das nossas opcoes:\n\n"
            + "\n".join(lines)
            + "\n\nSobre qual voce gostaria de saber mais?"
        ).replace("sao", "s\u00e3o").replace(
            "opcoes", "op\u00e7\u00f5es"
        ).replace("voce", "voc\u00ea")

    return None


def _socialmei_clean_reply(text):
    import re

    text = text.replace("**", "")

    text = re.sub(
        r"\s+(?:na|pela|por meio da)\s+op[c\u00e7][a\u00e3]o\s+5\b",
        "",
        text,
        flags=re.I
    )

    return text.strip()


def _socialmei_direct_result(result, text):
    result = dict(result)
    result["text"] = _socialmei_clean_reply(text)
    result["choices"] = []
    result["items"] = []
    result["catalog_navigation"] = False
    result["everson_menu_suppressed"] = True
    return result


def _socialmei_price_followup(conn,channel,row,context,text):
    import re
    import unicodedata

    if (channel["workspace_id"],channel["channel_id"]) != (60,3):
        return None

    def norm(value):
        value=unicodedata.normalize(
            "NFKD",str(value or "").casefold()
        )
        value="".join(
            c for c in value
            if not unicodedata.combining(c)
        )
        return " ".join(re.findall(r"[a-z0-9]+",value))

    q=norm(text)

    if not q.startswith("e "):
        return None

    q=q[2:]
    q=re.sub(r"^(?:o|a|os|as) ","",q)

    catalog=context.get("catalogo")

    if not isinstance(catalog,list):
        return None

    matches=[
        item["nome"]
        for item in catalog
        if isinstance(item,dict)
        and isinstance(item.get("nome"),str)
        and norm(item["nome"]) == q
    ]

    if len(matches)!=1:
        return None

    previous=conn.execute(
        "SELECT status,result->>'everson_catalog_answered' "
        "AS catalog_answered "
        "FROM socialmei.wa_bot_decisions "
        "WHERE workspace_id=%s AND channel_id=%s "
        "AND conversation_id=%s AND binding_hash=%s "
        "AND id<>%s AND created_at<=%s "
        "AND created_at>=NOW()-INTERVAL '5 minutes' "
        "ORDER BY created_at DESC,id DESC LIMIT 1",
        (
            channel["workspace_id"],
            channel["channel_id"],
            row["conversation_id"],
            channel["binding_hash"],
            row["id"],
            row["created_at"]
        )
    ).fetchone()

    if not previous or previous["status"]!="confirmed":
        return None

    if previous["catalog_answered"]!="true":
        return None

    return _socialmei_catalog_answer(
        context,"Quanto custa "+matches[0]+"?"
    )


def _sm_batch_price_group(first,rows,catalog):
    import re
    import unicodedata
    from decimal import Decimal, InvalidOperation

    def normalize(text):
        text=unicodedata.normalize("NFKD",text.casefold())
        text="".join(
            c for c in text
            if not unicodedata.combining(c)
        )
        return " ".join(
            text.strip(" !?.,").split()
        )

    messages=[first]
    seen={first["id"]}

    if first.get("decided") or first.get("selection"):
        return None

    for item in rows:
        if len(messages)>=3:
            break

        if (
            item["id"] in seen
            or item.get("decided")
            or item.get("selection")
        ):
            break

        messages.append(item)
        seen.add(item["id"])

    if len(messages)<2:
        return None

    texts=[]

    for item in messages:
        value=item.get("text")

        if not isinstance(value,str):
            return None

        if not 2<=len(value.strip())<=500:
            return None

        texts.append(normalize(value))

    if texts[-1] not in {
        "quanto custa",
        "qual o preco",
        "qual o valor",
        "quanto fica",
        "qual e o preco",
        "qual e o valor"
    }:
        return None

    parts=texts[:-1]

    if len(parts)==2 and parts[0] in {
        "oi","ola","opa","bom dia",
        "boa tarde","boa noite"
    }:
        parts=parts[1:]

    if len(parts)!=1:
        return None

    match=re.fullmatch(
        r"(?:quero|queria|gostaria|preciso|tenho interesse)"
        r"\s+(?:(?:de|em)\s+)?"
        r"(?:(?:um|uma|o|a)\s+)?(.+)",
        parts[0]
    )

    if not match:
        return None

    requested=match.group(1).strip()

    if re.search(
        r"\b(?:cpf|cnpj|senha|pix|cartao|"
        r"atendente|humano|cancelar|agendar|"
        r"reagendar|menu|voltar|sair)\b",
        requested
    ):
        return None

    matches=[
        product for product in catalog
        if isinstance(product.get("nome"),str)
        and normalize(product["nome"])==requested
    ]

    # Nao responder quando existir ambiguidade.
    if len(matches)!=1:
        return None

    product=matches[0]

    if product.get("preco") is None:
        return None

    try:
        price=Decimal(str(product["preco"]))

        if not price.is_finite() or price<0:
            return None

        formatted=format(
            price.quantize(Decimal("0.01")),",.2f"
        )

    except (InvalidOperation,ValueError,TypeError):
        return None

    formatted=formatted.translate(
        str.maketrans({",":".",".":","})
    )

    name=" ".join(product["nome"].split())

    if not name or len(name)>150:
        return None

    answer=f"O valor de {name} e R$ {formatted}."

    return answer,messages[1:]



def _sm_batch_group_sql():
    return """
        SELECT DISTINCT
            m.id,m.text,m.occurred_at,
            COALESCE(
                e.dados_normalizados->>'wa_selection',''
            ) AS selection,
            EXISTS(
                SELECT 1
                FROM socialmei.wa_bot_decisions d
                WHERE d.workspace_id=m.workspace_id
                AND d.channel_id=e.canal_id
                AND d.source_message_id=m.id
            ) AS decided
        FROM socialmei.me_messages m
        JOIN socialmei.crm_eventos_canal e
          ON e.workspace_id=m.workspace_id
          AND e.inbox_message_id=m.id
        WHERE m.workspace_id=%s
        AND m.conversation_id=%s
        AND m.origin='waha'
        AND e.canal_id=%s
        AND e.tipo='message'
        AND e.status='processado'
        AND e.waha_account_snapshot=%s
        AND e.recebido_em>=%s
        AND (m.occurred_at,m.id)>(%s,%s)
        AND m.occurred_at<=%s+INTERVAL '10 seconds'
        AND m.occurred_at<=NOW()
        ORDER BY m.occurred_at,m.id
        LIMIT 2
    """


def _sm_batch_try_group(
    conn,channel,message,state,nav_enabled,result
):
    from pathlib import Path

    if (
        channel["workspace_id"],
        channel["channel_id"]
    )!=(60,3):
        return None

    if (
        state["state"]!="menu"
        or result.get("action")!="menu"
        or result.get("handoff")
        or not nav_enabled
        or not _reviewed_channel(channel)
        or not result.get("catalog_navigation")
        or message.get("catalog_target") is not None
        or (message.get("ingress_data") or {}).get("wa_selection")
        or pending_human_reply(
            conn,60,3,message["conversation_id"]
        )
    ):
        return None

    cfg=json.loads(Path(
        "/app/.everson-pilot.private.json"
    ).read_text())

    if (
        cfg.get("workspace_id")!=60
        or cfg.get("channel_id")!=3
        or cfg.get("business_scope_verified") is not True
        or message["occurred_at"]<
           datetime.fromisoformat(cfg["enabled_at"])
    ):
        return None

    rows=conn.execute(
        _sm_batch_group_sql(),
        (
            60,message["conversation_id"],3,
            channel["identificador_conta"],
            message["batch_received_at"],
            message["occurred_at"],message["id"],
            message["occurred_at"]
        )
    ).fetchall()

    if not rows:
        return None

    catalog=conn.execute("""
        SELECT nome,tipo,preco
        FROM socialmei.crm_produtos
        WHERE workspace_id=60
        AND status='Ativo'
        ORDER BY nome,id LIMIT 25
    """).fetchall()

    catalog=[
        {
            "nome":row["nome"],
            "tipo":row["tipo"],
            "preco":str(row["preco"])
            if row["preco"] is not None else None
        }
        for row in catalog
    ]

    group=_sm_batch_price_group(
        message,rows,catalog
    )

    if not group:
        return None

    answer,items=group

    if pending_human_reply(
        conn,60,3,message["conversation_id"],
        items[-1]["id"]
    ):
        return None

    return answer,items


_SM_BOOKING_READY_SQL = (
    "SELECT EXISTS (SELECT 1 FROM socialmei.crm_produtos "
    "WHERE workspace_id=%s AND tipo='Serviço' AND status='Ativo' "
    "AND duracao_minutos>0) AND EXISTS (SELECT 1 "
    "FROM socialmei.agenda_resources WHERE workspace_id=%s "
    "AND ativo) AS ready"
)

def _sm_booking_ready(conn,channel):
    if (channel["workspace_id"],channel["channel_id"])!=(60,3):
        return False

    import channel_booking as booking
    from fastapi import HTTPException

    try:
        policy=booking.read_policy(conn,60)["policy"]
    except HTTPException:
        return False

    if policy.get("enabled") is not True:
        return False

    row=conn.execute(
        _SM_BOOKING_READY_SQL,(60,60)
    ).fetchone()

    return bool(row and row["ready"])


def _sm_booking_route(conn,channel,message,state,*,native):
    if state["state"]=="human":
        return None

    if not _sm_booking_ready(conn,channel):
        return None

    if pending_human_reply(
        conn,60,3,message["conversation_id"],message["id"]
    ):
        return None

    import channel_booking_flow as flow

    return flow.respond(
        conn,channel,message,state,native=native
    )


def _sm_booking_menu(conn,channel,message,state,result):
    if result.get("action")!="menu" or result.get("handoff"):
        return result

    if state["state"]=="human" or not _sm_booking_ready(conn,channel):
        return result

    if pending_human_reply(
        conn,60,3,message["conversation_id"],message["id"]
    ):
        return result

    import channel_booking_flow as flow

    updated=flow.with_entry(conn,60,result)
    choices=updated.get("choices",[])
    ids=[str(c["id"]) for c in choices]

    if len(ids)>10 or len(ids)!=len(set(ids)):
        return result

    return updated


def _sm_context_clean(value,limit):
    import re
    value=" ".join(str(value).split())

    if re.search(r"\b(?:senha|password|token|codigo de verificacao|código de verificação)\s*[:=]",value,re.I):
        return "[dado confidencial omitido]"

    value=re.sub(
        r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}",
        "[email omitido]",value
    )

    value=re.sub(
        r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)",
        "[documento omitido]",value
    )

    value=re.sub(
        r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)",
        "[documento ou telefone omitido]",value
    )

    value=re.sub(
        r"(?<!\d)(?:\+55\s*)?\(?[1-9]\d\)?[ .-]*(?:9\d{4}|\d{4})[ .-]*\d{4}(?!\d)",
        "[telefone omitido]",value
    )

    return value[:limit]



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


_sm_original_catalog_answer = _catalog_answer

def _catalog_answer(conn, workspace, state, text, target, enabled):
    next_state, result = _sm_original_catalog_answer(conn,workspace,state,text,target,enabled)
    return next_state,_sm_menu_personalize(workspace,state,result)



from contextlib import contextmanager as _sm_contextmanager

@_sm_contextmanager
def _sm_typing_presence(channel,row):
    import threading,re,httpx
    from types import SimpleNamespace
    worker=None
    stop=threading.Event()

    try:
        if (channel['workspace_id'],channel['channel_id'])!=(60,3):
            raise ValueError('scope')

        wa=SimpleNamespace(**__import__('json').loads(__import__('pathlib').Path('/tmp/.socialmei-typing.private.json').read_text()))

        if not (
            wa and wa.workspace_id==60
            and wa.engine=='GOWS'
            and wa.base_url=='http://socialmei-waha-gows-piloto:3000'
            and wa.account_id==channel['identificador_conta']
            and wa.session==channel['sessao']
        ):
            raise ValueError('provider')

        with operation_database() as conn:
            hit=conn.execute("""
                SELECT v.contact_ref FROM socialmei.me_conversations v
                JOIN socialmei.wa_bot_decisions d
                  ON d.workspace_id=v.workspace_id
                  AND d.conversation_id=v.id
                JOIN socialmei.wa_bot_conversations s
                  ON s.workspace_id=d.workspace_id
                  AND s.channel_id=d.channel_id
                  AND s.conversation_id=d.conversation_id
                WHERE d.workspace_id=60 AND d.channel_id=3
                  AND d.id=%s AND d.status='planned'
                  AND s.state='menu'
                  AND s.revision=d.state_revision
                  AND v.origin='waha' AND v.account_ref=%s
            """,(row['id'],'waha:'+wa.account_id)).fetchone()

            if not hit or pending_human_reply(
                conn,60,3,row['conversation_id']
            ):
                raise ValueError('conversation')

            ref=hit['contact_ref']

        if not re.fullmatch(
            r'waha:(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)',ref
        ):
            raise ValueError('contact')

        chat=ref[5:]

        def presence():
            try:
                with httpx.Client(
                    timeout=2,trust_env=False,
                    follow_redirects=False,
                    headers={'X-Api-Key':wa.api_key}
                ) as client:
                    url=wa.base_url+'/api/'+wa.session+'/presence'
                    attempted=False

                    try:
                        session=client.get(
                            wa.base_url+'/api/sessions/'+wa.session
                        )
                        session.raise_for_status()
                        data=session.json()

                        if (
                            data.get('name')!=wa.session
                            or data.get('status')!='WORKING'
                            or data.get('me',{}).get('id')!=wa.account_id
                        ):
                            return

                        for _ in range(8):
                            if stop.is_set():
                                break

                            attempted=True

                            r=client.post(wa.base_url+'/api/startTyping',json={
                                'chatId':chat,'session':wa.session
                            })

                            if not 200<=r.status_code<300:
                                break

                            if stop.wait(7):
                                break
                    finally:
                        if attempted:
                            client.post(wa.base_url+'/api/stopTyping',json={
                                'chatId':chat,'session':wa.session
                            })
            except Exception:
                pass

        worker=threading.Thread(
            target=presence,daemon=True
        )
        worker.start()

    except Exception:
        pass

    try:
        yield
    finally:
        stop.set()
        if worker is not None and worker.ident is not None:
            worker.join(timeout=5)



import re as _sm_re
from contextlib import contextmanager as _sm_cm

def _sm_dialog_kind(text):
    t=_sm_menu_norm(text)
    t=' '.join(t.split())
    if t in ('oi','ola','opa','bom dia','boa tarde','boa noite','oi tudo bem','ola tudo bem'):
        return 'greeting'
    if t in ('0','menu','menu principal','inicio','ajuda','opcoes','ver menu','quero ver o menu','mostrar menu','mostre o menu','quero o menu'):
        return 'menu'
    if explicit_menu_action(text) or _sm_re.search(r'\b(?:quais|listar|ver|conhecer|mostrar|mostre|consultar|lista|catalogo)\b.*\b(?:servicos|produtos|opcoes)\b',t):
        return 'requested'
    return 'text'

def _sm_dialog_result(result,text):
    if result.get('action')!='menu' or result.get('handoff') or result.get('channel_booking'):
        return result
    kind=_sm_dialog_kind(text)
    if kind in ('menu','requested'):
        return result
    out=dict(result,choices=[],catalog_navigation=False,everson_menu_suppressed=True)
    if kind=='greeting':
        from zoneinfo import ZoneInfo
        from datetime import datetime
        h=datetime.now(ZoneInfo('America/Recife')).hour
        saudacao='Bom dia' if 5<=h<12 else 'Boa tarde' if 12<=h<18 else 'Boa noite'
        out['text']=saudacao+'! Seja bem-vindo(a) à Brilho&Limpeza Service. Tudo bem? Como podemos ajudar você hoje?'
    return out

def _sm_dialog_scope(conn,request,opid):
    channel=authorize(conn,request)
    if (channel['workspace_id'],channel['channel_id'])!=(60,3):return None
    row=locked_decision(conn,channel,opid)
    if row['status']!='planned' or row['result'].get('handoff') or row['result'].get('action')!='menu':return None
    hit=conn.execute("""
        SELECT m.text,v.contact_ref FROM socialmei.me_messages m
        JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id
        JOIN socialmei.wa_bot_conversations s ON s.workspace_id=v.workspace_id AND s.conversation_id=v.id AND s.channel_id=3
        WHERE m.workspace_id=60 AND m.id=%s AND m.conversation_id=%s
        AND m.origin='waha' AND v.origin='waha' AND v.account_ref=%s
        AND s.state='menu' AND s.revision=%s
        AND EXISTS (SELECT 1 FROM socialmei.crm_eventos_canal e
          WHERE e.workspace_id=60 AND e.canal_id=3 AND e.inbox_message_id=m.id
          AND e.tipo='message' AND e.status='processado' AND e.waha_account_snapshot=%s)
    """,(row['source_message_id'],row['conversation_id'],'waha:'+channel['identificador_conta'],row['state_revision'],channel['identificador_conta'])).fetchone()
    if not hit or pending_human_reply(conn,60,3,row['conversation_id'],row['source_message_id']):return None
    return channel,row,hit

@_sm_cm
def _sm_presence_v2(channel,hit):
    import httpx,threading,time,logging,json
    from pathlib import Path
    log=logging.getLogger('socialmei.presence')
    client=None; attempted=False; started=None; worker=None; stop=threading.Event()
    try:
        cfg=json.loads(Path('/tmp/.socialmei-typing.private.json').read_text())
        ref=hit['contact_ref']
        if not (cfg['workspace_id']==60 and cfg['engine']=='GOWS' and cfg['base_url']=='http://socialmei-waha-gows-piloto:3000' and cfg['account_id']==channel['identificador_conta'] and cfg['session']==channel['sessao'] and _sm_re.fullmatch(r'waha:(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)',ref)):
            raise ValueError('scope')
        client=httpx.Client(timeout=2,trust_env=False,follow_redirects=False,headers={'X-Api-Key':cfg['api_key']})
        base=cfg['base_url']; data={'session':cfg['session'],'chatId':ref[5:]}
        r=client.get(base+'/api/sessions/'+cfg['session']); r.raise_for_status(); info=r.json()
        if info.get('name')!=cfg['session'] or info.get('status')!='WORKING' or info.get('me',{}).get('id')!=cfg['account_id']:raise ValueError('session')
        attempted=True
        r=client.post(base+'/api/startTyping',json=data); r.raise_for_status()
        started=time.monotonic(); log.warning('SM_TYPING_START_OK')
        def refresh():
            for _ in range(8):
                if stop.wait(6):return
                try:client.post(base+'/api/startTyping',json=data).raise_for_status()
                except Exception:return
        worker=threading.Thread(target=refresh,daemon=True); worker.start()
    except Exception as e:
        log.warning('SM_TYPING_START_FAIL_%s',type(e).__name__)
    try:
        yield
    finally:
        if started is not None:time.sleep(max(0,1.2-(time.monotonic()-started)))
        stop.set()
        if worker is not None:worker.join(timeout=4)
        if attempted:
            try:client.post(base+'/api/stopTyping',json=data).raise_for_status();log.warning('SM_TYPING_STOP_OK')
            except Exception as e:log.warning('SM_TYPING_STOP_FAIL_%s',type(e).__name__)
        if client is not None:client.close()

_sm_dialog_original_generate=_everson_generate

def _everson_generate(planned,request):
    if planned.get('status')=='planned' and str(planned.get('action','')).startswith('booking_'):
        try:
            scope=_sm_booking_presence_scope(planned,request)
            if scope is not None:
                channel,hit=scope
                with _sm_presence_v2(channel,hit):
                    pass
        except Exception:
            pass
        return planned
    if planned.get('status')!='planned' or planned.get('action')!='menu':
        return _sm_dialog_original_generate(planned,request)
    opid=UUID(str(planned['operation_id']))
    with operation_database() as conn:
        scope=_sm_dialog_scope(conn,request,opid)
    if scope is None:return _sm_dialog_original_generate(planned,request)
    channel,row,hit=scope
    kind=_sm_dialog_kind(hit['text'])
    with _sm_presence_v2(channel,hit):
        generated=planned if kind in ('greeting','menu') else _sm_dialog_original_generate(planned,request)
        with operation_database() as conn:
            scope=_sm_dialog_scope(conn,request,opid)
            if scope is None:return generated
            _,current,source=scope
            result=_sm_dialog_result(current['result'],source['text'])
            if result==current['result']:return view(current)
            saved=conn.execute("UPDATE socialmei.wa_bot_decisions SET result=%s WHERE id=%s AND workspace_id=60 AND channel_id=3 AND status='planned' RETURNING *",(Jsonb(result),opid)).fetchone()
            return view(saved) if saved else generated



# SM_BOOKING_PRESENCE_V1

def _sm_booking_presence_scope(planned,request):
    with operation_database() as conn:
        channel=authorize(conn,request)

        if channel['workspace_id']!=60 or channel['channel_id']!=3:
            return None

        row=locked_decision(conn,channel,UUID(str(planned['operation_id'])))

        if row['status']!='planned':
            return None

        result=row['result']

        if not result.get('channel_booking') or result.get('handoff'):
            return None

        if result.get('action')!=planned.get('action'):
            return None

        hit=conn.execute(
            """
            SELECT v.contact_ref
            FROM socialmei.me_conversations v
            JOIN socialmei.wa_bot_conversations s
              ON s.workspace_id=v.workspace_id
              AND s.conversation_id=v.id
            JOIN socialmei.me_messages m
              ON m.workspace_id=v.workspace_id
              AND m.conversation_id=v.id
            WHERE v.workspace_id=60
              AND v.id=%s
              AND s.channel_id=3
              AND s.state='menu'
              AND s.revision=%s
              AND m.id=%s
              AND m.origin='waha'
              AND m.occurred_at>=NOW()-INTERVAL '2 minutes'
              AND EXISTS (
                SELECT 1 FROM socialmei.crm_eventos_canal e
                WHERE e.workspace_id=60
                  AND e.canal_id=3
                  AND e.inbox_message_id=m.id
                  AND e.inbox_origin='waha'
                  AND e.status='processado'
                  AND e.waha_account_snapshot=%s
              )
            """,
            (row['conversation_id'],row['state_revision'],
             row['source_message_id'],channel['identificador_conta'])
        ).fetchone()

        if not hit or pending_human_reply(
            conn,60,3,row['conversation_id'],row['source_message_id']
        ):
            return None

        return channel,hit
