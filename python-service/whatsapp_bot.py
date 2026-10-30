"""Durable replies for verified WAHA inputs. This module never sends a message."""
import os
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from account_auth import require_enabled
from database import connect
from whatsapp_catalog import ChannelAccess, _TOKEN, issue_secret, product_view, require_owner, token_digest
import settings

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
    return os.getenv('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'false').strip().lower() == 'true'


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


def render_waha(session, chat, text, choices, *, engine='WEBJS', list_verified=False):
    """Construct a payload, not an HTTP call. Text is the verified default."""
    if choices and list_verified and engine in {'GOWS', 'NOWEB'}:
        return {'path': '/api/sendList', 'body': {'session': session, 'chatId': chat, 'message': {
            'title': 'Atendimento', 'description': text, 'footer': 'SocialMEI', 'button': 'Ver opções',
            'sections': [{'title': 'Como podemos ajudar?', 'rows': [
                {'rowId': c['id'], 'title': c['title'], 'description': None} for c in choices
            ]}],
        }}}
    menu = '\n'.join(c['id'] + ' - ' + c['title'] for c in choices)
    return {'path': '/api/sendText', 'body': {'session': session, 'chatId': chat,
                                             'text': text + ('\n\n' + menu if menu else '')}}


def answer(conn, workspace, state, text):
    choice = text.strip().casefold()
    result = {'action': 'menu', 'text': 'Olá! Como podemos ajudar? Escolha uma opção.',
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
        return 'ask_product', {**result, 'action': 'ask_product', 'text': 'Qual produto deseja consultar? Informe o nome.',
                               'choices': []}
    if choice not in {'1', '3'} and state != 'ask_product':
        return 'menu', result
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
        line = item['nome'] + ' — R$ ' + price
        if item['tipo'] == 'Produto':
            line += (' — estoque: ' + str(item['estoque']) + ' registrado(s)'
                     if item['disponibilidade'] == 'em_estoque' else ' — disponibilidade a confirmar')
        lines.append(line)
    return 'menu', {**result, 'action': 'services' if choice == '3' else 'availability' if query else 'products',
                    'items': items, 'choices': [], 'text': ('\n'.join(lines) +
                    '\n\nConfirme os detalhes antes de fechar o pedido. Digite 0 para o menu ou 5 para atendente.')
                    if items else 'Não encontrei esse item no catálogo ativo. Digite 5 para atendente ou 0 para o menu.'}


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
        row = conn.execute("UPDATE socialmei.wa_bot_conversations SET state='menu',revision=revision+1,updated_at=NOW() "
                           "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s RETURNING conversation_id",
                           (user['workspace_id'], payload.channel_id, conversation_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Conversa não encontrada.')
        conn.execute("INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,'whatsapp_bot_resumed')", (user['id'],))


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
        contacts = settings.whatsapp_bot_allowed_contacts()
        rows = conn.execute(
            "SELECT e.mensagem_externa_id AS external_message_id FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id "
            "AND m.origin='waha' JOIN socialmei.me_conversations v "
            "ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "LEFT JOIN socialmei.wa_bot_decisions d ON d.workspace_id=e.workspace_id "
            "AND d.channel_id=e.canal_id AND d.source_message_id=m.id "
            "WHERE e.workspace_id=%s AND e.canal_id=%s AND e.tipo='message' AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s "
            "AND (%s OR v.contact_ref=ANY(%s)) "
            "AND m.occurred_at>=NOW()-INTERVAL '15 minutes' AND m.occurred_at<=NOW()+INTERVAL '1 minute' "
            "AND (d.id IS NULL OR (d.status='planned' AND d.created_at>NOW()-INTERVAL '2 minutes')) "
            "ORDER BY m.occurred_at,m.id LIMIT 50",
            (channel['workspace_id'], channel['channel_id'], channel['identificador_conta'],
             'waha:' + channel['identificador_conta'], contacts is None, list(contacts or [])),
        ).fetchall()
    return {'sources': [{'instance': channel['instancia'], **row} for row in rows]}


@router.post(INTERNAL + '/decisions')
def prepare(payload: Source, request: Request):
    require_bot()
    with operation_database() as conn:
        channel = authorize(conn, request)
        if payload.instance != channel['instancia']:
            raise HTTPException(401, 'Credencial de atendimento inválida.')
        workspace, cid = channel['workspace_id'], channel['channel_id']
        message = conn.execute(
            "SELECT m.*,v.contact_ref FROM socialmei.crm_eventos_canal e "
            "JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.inbox_message_id AND m.origin='waha' "
            "JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id "
            "WHERE e.workspace_id=%s AND e.canal_id=%s AND e.mensagem_externa_id=%s AND e.status='processado' "
            "AND e.waha_account_snapshot=%s AND v.account_ref=%s AND e.tipo='message'",
            (workspace, cid, payload.external_message_id, channel['identificador_conta'], 'waha:' + channel['identificador_conta']),
        ).fetchone()
        if not message:
            raise HTTPException(404, 'Mensagem recebida não encontrada neste canal.')
        contacts = settings.whatsapp_bot_allowed_contacts()
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
            if recent >= 20 and state['state'] != 'human' and message['text'].strip().casefold() not in HUMAN_CHOICES:
                next_state = state['state']
                result = {'action': 'rate_limited', 'text': '', 'choices': [], 'items': [], 'handoff': False}
            else:
                next_state, result = answer(conn, workspace, state['state'], message['text'])
        revision = state['revision'] + (0 if old or outdated else 1)
        if not old and not outdated:
            conn.execute("UPDATE socialmei.wa_bot_conversations SET state=%s,revision=%s,"
                     "last_message_id=%s,last_occurred_at=%s,updated_at=NOW() "
                     "WHERE workspace_id=%s AND channel_id=%s AND conversation_id=%s",
                     (next_state, revision, message['id'], message['occurred_at'], workspace, cid, conv))
        row = conn.execute("INSERT INTO socialmei.wa_bot_decisions(id,workspace_id,channel_id,conversation_id,source_message_id,binding_hash,state_revision,result,status) "
                           "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                           (uuid4(), workspace, cid, conv, message['id'], channel['binding_hash'], max(1, revision), Jsonb(result), 'planned' if result['text'] else 'skipped')).fetchone()
        return view(row)


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
        contacts = settings.whatsapp_bot_allowed_contacts()
        permitted = permitted and (contacts is None or state['contact_ref'] in contacts)
        if not permitted:
            return {'operation_id': str(row['id']), 'dispatch_allowed': False, 'status': row['status']}
        conn.execute("UPDATE socialmei.wa_bot_decisions SET status='claimed',claimed_at=NOW() WHERE id=%s", (decision_id,))
        delivery = render_waha(channel['sessao'], state['contact_ref'].removeprefix('waha:'), row['result']['text'], row['result']['choices'])
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
