"""Durable human WhatsApp drafts. Production dispatch remains unconfigured."""
import hashlib
import json
import re
from contextlib import contextmanager
from uuid import UUID

import psycopg
import settings
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg.rows import dict_row
from pydantic import Field, StrictInt, StrictStr, field_validator

from account_auth import COOKIE, Strict, current, digest, require_enabled
from database import connect
from waha_ingress import DIRECT
from whatsapp_bot import binding_hash, configure, render_waha
from whatsapp_human_transport import WahaHumanTransport, WahaPolicyError

router = APIRouter(prefix='/api/v1/whatsapp/replies', tags=['WhatsApp human replies'])


class DraftInput(Strict):
    operation_id: UUID
    source_message_id: StrictInt = Field(ge=1, le=9007199254740991)
    text: StrictStr

    @field_validator('text')
    @classmethod
    def valid_text(cls, text):
        try:
            size = len(text.encode('utf-8'))
        except UnicodeEncodeError:
            raise ValueError('Texto inválido.') from None
        if not text.strip() or size > 4096 or any(
            (ord(c) < 32 and c not in '\n\r\t') or 0x7f <= ord(c) <= 0x9f for c in text
        ):
            raise ValueError('Resposta deve conter até 4096 bytes UTF-8.')
        return text


@contextmanager
def database():
    try:
        with connect() as conn:
            configure(conn)
            yield conn
    except psycopg.Error:
        raise HTTPException(503, 'Respostas indisponíveis. Consulte o histórico antes de tentar novamente.') from None


def identity(request):
    require_enabled()
    return current(), digest(request.cookies.get(COOKIE, ''))


def authorize(conn, user, session, *, write=False):
    row = conn.execute(
        'SELECT m.role FROM socialmei.auth_sessoes s '
        'JOIN socialmei.auth_credenciais a ON a.user_id=s.user_id '
        'JOIN socialmei.workspace_members m ON m.workspace_id=s.workspace_id AND m.user_id=s.user_id '
        'WHERE s.token_hash=%s AND s.workspace_id=%s AND s.user_id=%s '
        'AND s.revogada_em IS NULL AND s.expira_em>NOW() AND a.ativo FOR SHARE OF s,a,m',
        (session, user['workspace_id'], user['id']),
    ).fetchone()
    if not row:
        raise HTTPException(401, 'Sessão ausente ou expirada.')
    allowed = {'owner', 'admin', 'member'} if write else {'owner', 'admin', 'member', 'viewer'}
    if row['role'] not in allowed:
        raise HTTPException(403, 'Permissão insuficiente para respostas.')
    return row['role']


def source(conn, workspace, source_id):
    rows = conn.execute(
        'SELECT m.id AS source_message_id,m.conversation_id,v.contact_ref,c.id AS channel_id,'
        'c.workspace_id,c.instancia,c.sessao,c.identificador_conta,c.versao '
        'FROM socialmei.me_messages m '
        'JOIN socialmei.me_conversations v ON v.workspace_id=m.workspace_id AND v.id=m.conversation_id '
        'JOIN socialmei.crm_eventos_canal e ON e.workspace_id=m.workspace_id AND e.inbox_message_id=m.id '
        'JOIN socialmei.crm_canais c ON c.workspace_id=e.workspace_id AND c.id=e.canal_id '
        "WHERE m.workspace_id=%s AND m.id=%s AND m.origin='waha' AND v.origin='waha' "
        "AND e.tipo='message' AND e.status='processado' AND c.provedor='waha' "
        "AND c.ativo AND c.ingress_provisioned AND NOT c.envio_habilitado "
        "AND e.waha_account_snapshot=c.identificador_conta AND v.account_ref='waha:' || c.identificador_conta "
        'FOR SHARE OF c,v', (workspace, source_id),
    ).fetchall()
    if len(rows) != 1 or not rows[0]['contact_ref'].startswith('waha:') or not DIRECT.fullmatch(
        rows[0]['contact_ref'].removeprefix('waha:')
    ):
        raise HTTPException(404, 'Mensagem WhatsApp validada não encontrada neste negócio.')
    return rows[0]


def pause(conn, item):
    scope = (item['workspace_id'], item['channel_id'], item['conversation_id'])
    conn.execute(
        'INSERT INTO socialmei.wa_bot_conversations(workspace_id,channel_id,conversation_id,state,revision) '
        "VALUES(%s,%s,%s,'human',1) ON CONFLICT(workspace_id,channel_id,conversation_id) "
        "DO UPDATE SET state='human',revision=wa_bot_conversations.revision+1,updated_at=NOW()", scope,
    )
    pending = conn.execute(
        'SELECT 1 FROM socialmei.wa_bot_decisions WHERE workspace_id=%s AND channel_id=%s '
        "AND conversation_id=%s AND status IN ('claimed','uncertain') LIMIT 1", scope,
    ).fetchone()
    if pending:
        raise HTTPException(409, 'Existe envio do bot em andamento ou incerto. Concilie antes de responder.')
    pending_human = conn.execute(
        'SELECT 1 FROM socialmei.wa_human_replies WHERE workspace_id=%s AND channel_id=%s '
        "AND conversation_id=%s AND status IN ('dispatching','uncertain') LIMIT 1", scope,
    ).fetchone()
    if pending_human:
        raise HTTPException(409, 'Existe resposta humana em andamento ou incerta. Concilie antes de responder.')


def view(row):
    result = {key: row[key] for key in (
        'conversation_id', 'source_message_id', 'text', 'status', 'provider_message_id',
    )}
    result['id'] = str(row['id'])
    for key in ('created_at', 'claimed_at', 'finished_at'):
        result[key] = row[key].isoformat() if row[key] else None
    result['provider_confirmation'] = 'accepted' if row['status'] == 'confirmed' else None
    return result


class WhatsAppReplyService:
    def __init__(self, *, transport=None, allow_dispatch=False, workspace_id=None, policy=None):
        if (type(allow_dispatch) is not bool or (transport is not None and not callable(transport))
                or (policy is not None and not callable(policy))
                or (workspace_id is not None and (type(workspace_id) is not int or workspace_id < 1))):
            raise ValueError('Transporte inválido.')
        self.transport = transport
        self.send_enabled = allow_dispatch and transport is not None
        self.workspace_id = workspace_id
        self.policy = policy

    def can_send(self, workspace):
        return self.send_enabled and (self.workspace_id is None or self.workspace_id == workspace)

    def create(self, user, session, payload):
        expected = hashlib.sha256(json.dumps(
            [payload.source_message_id, payload.text], ensure_ascii=False, separators=(',', ':'),
        ).encode()).hexdigest()
        workspace = user['workspace_id']
        with database() as conn:
            authorize(conn, user, session, write=True)
            # Serialize the same operation even when it has not inserted a row yet.
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                         (str(workspace) + ':wa-human:' + str(payload.operation_id),))
            old = conn.execute('SELECT * FROM socialmei.wa_human_replies WHERE workspace_id=%s AND id=%s',
                               (workspace, payload.operation_id)).fetchone()
            if old:
                if old['fingerprint'] != expected:
                    raise HTTPException(409, 'Operação já utilizada com outro conteúdo.')
                return view(old)
            item = source(conn, workspace, payload.source_message_id)
            pause(conn, item)
            row = conn.execute(
                'INSERT INTO socialmei.wa_human_replies(workspace_id,id,channel_id,conversation_id,'
                'source_message_id,binding_hash,fingerprint,text,created_by) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                (workspace, payload.operation_id, item['channel_id'], item['conversation_id'],
                 payload.source_message_id, binding_hash(item), expected, payload.text, user['id']),
            ).fetchone()
            return view(row)

    def read(self, user, session, *, reply_id=None, conversation_id=None):
        with database() as conn:
            role = authorize(conn, user, session)
            capability = self.can_send(user['workspace_id']) and role in {'owner', 'admin', 'member'}
            rows = conn.execute(
                'SELECT * FROM socialmei.wa_human_replies WHERE workspace_id=%s '
                'AND (%s::uuid IS NULL OR id=%s) AND (%s::bigint IS NULL OR conversation_id=%s) '
                'ORDER BY created_at DESC,id DESC LIMIT 100',
                (user['workspace_id'], reply_id, reply_id, conversation_id, conversation_id),
            ).fetchall()
            if reply_id:
                if not rows:
                    raise HTTPException(404, 'Resposta não encontrada neste negócio.')
                return {**view(rows[0]), 'send_enabled': capability}
            return {'items': [view(row) for row in rows], 'send_enabled': capability}

    def send(self, user, session, reply_id):
        workspace = user['workspace_id']
        with database() as conn:
            authorize(conn, user, session, write=True)
            row = conn.execute(
                'SELECT * FROM socialmei.wa_human_replies WHERE workspace_id=%s AND id=%s FOR UPDATE',
                (workspace, reply_id),
            ).fetchone()
            if not row:
                raise HTTPException(404, 'Resposta não encontrada neste negócio.')
            if row['status'] != 'draft':
                return view(row)
            if not self.can_send(workspace):
                raise HTTPException(503, 'Envio WhatsApp não habilitado. Rascunho preservado; nenhuma mensagem enviada.')
            item = source(conn, workspace, row['source_message_id'])
            if row['binding_hash'] != binding_hash(item):
                raise HTTPException(409, 'O vínculo do canal mudou. Não repita esta resposta.')
            if self.policy is not None:
                try:
                    self.policy(item)
                except WahaPolicyError:
                    raise HTTPException(403, 'Canal ou contato fora do piloto de envio autorizado.') from None
            pause(conn, item)
            delivery = render_waha(item['sessao'], item['contact_ref'].removeprefix('waha:'), row['text'], [])
            conn.execute(
                "UPDATE socialmei.wa_human_replies SET status='dispatching',claimed_at=NOW() "
                'WHERE workspace_id=%s AND id=%s', (workspace, reply_id),
            )
        # The claim commits before I/O. A timeout/crash cannot cause automatic resend.
        try:
            provider_id = self.transport(delivery)
            if not isinstance(provider_id, str) or not re.fullmatch(r'[!-~]{1,1024}', provider_id):
                raise ValueError('Invalid provider receipt')
        except Exception:
            provider_id = None
        try:
            return self.finish(workspace, reply_id, provider_id)
        except psycopg.errors.UniqueViolation:
            return self.finish(workspace, reply_id, None)

    def finish(self, workspace, reply_id, provider_id):
        # No session dependency after I/O: a receipt must survive session revocation.
        try:
            with connect() as conn:
                configure(conn)
                row = conn.execute(
                    'UPDATE socialmei.wa_human_replies SET status=%s,provider_message_id=%s,finished_at=NOW() '
                    "WHERE workspace_id=%s AND id=%s AND status='dispatching' RETURNING *",
                    ('confirmed' if provider_id else 'uncertain', provider_id, workspace, reply_id),
                ).fetchone()
                if not row:
                    raise HTTPException(409, 'Estado do envio mudou. Consulte o histórico.')
                return view(row)
        except psycopg.errors.UniqueViolation:
            raise
        except psycopg.Error:
            raise HTTPException(503, 'Confirmação indisponível. Envio pode ter ocorrido; não repita.') from None


def reply_service():
    # Configuration is server-owned; constructing the service never contacts WAHA.
    try:
        configuration = settings.whatsapp_human_configuration()
        if configuration is not None:
            transport = WahaHumanTransport(configuration)
            return WhatsAppReplyService(transport=transport, allow_dispatch=True,
                                        workspace_id=configuration.workspace_id, policy=transport.validate_scope)
    except ValueError:
        pass
    return WhatsAppReplyService()


@router.post('', status_code=201)
def create(payload: DraftInput, request: Request, service=Depends(reply_service)):
    return service.create(*identity(request), payload)


@router.get('')
def listing(request: Request, conversation_id: int | None = Query(default=None, ge=1, le=9007199254740991),
            service=Depends(reply_service)):
    return service.read(*identity(request), conversation_id=conversation_id)


@router.get('/{reply_id}')
def detail(reply_id: UUID, request: Request, service=Depends(reply_service)):
    return service.read(*identity(request), reply_id=reply_id)


@router.post('/{reply_id}/send')
def send(reply_id: UUID, payload: Strict, request: Request, service=Depends(reply_service)):
    return service.send(*identity(request), reply_id)
