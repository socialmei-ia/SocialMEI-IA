"""Synthetic-only, tenant-scoped deterministic enrichment. No network transport."""
import hashlib
import hmac
import json
import re
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, HTTPException, Query, Request, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StringConstraints, field_validator, model_validator

import settings
from account_auth import current, require_enabled
from database import connect

router = APIRouter(prefix='/api/v1/message-enrichment', tags=['synthetic enrichment'])
internal_router = APIRouter(prefix='/internal/message-enrichment', tags=['internal synthetic enrichment'])
SAFE_MAX = 9007199254740991


def safe_text(value):
    if not value.strip() or any(ord(c) < 32 and c not in '\t\n\r' for c in value):
        raise ValueError('Texto inválido.')
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise ValueError('Texto inválido.') from None
    return value.strip()


def bounded_text(value):
    value = safe_text(value)
    if len(value.encode()) > 8192:
        raise ValueError('Texto muito grande.')
    return value


Text = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=8192), AfterValidator(bounded_text)]
Label = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=120), AfterValidator(safe_text)]
Reference = Annotated[str, StringConstraints(strict=True, pattern=r'^synthetic:[A-Za-z0-9_.:-]{1,100}$')]
Revision = Annotated[StrictInt, Field(ge=1, le=SAFE_MAX-1)]
Id = Annotated[int, Field(ge=1, le=SAFE_MAX)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Input(Strict):
    schema_version: StrictInt

    @model_validator(mode='after')
    def version(self):
        if self.schema_version != 1:
            raise ValueError('Versão inválida.')
        return self


class Operation(Input):
    operation_id: Annotated[str, StringConstraints(strict=True, max_length=36)]

    @model_validator(mode='after')
    def uuid(self):
        try:
            if str(UUID(self.operation_id)) != self.operation_id:
                raise ValueError()
        except ValueError:
            raise ValueError('Operação inválida.') from None
        return self


class Incoming(Operation):
    channel: Literal['whatsapp', 'instagram']
    account_ref: Reference
    contact_ref: Reference
    contact_name: Label
    external_message_id: Label
    text: Text
    occurred_at: datetime | None = None

    @field_validator('occurred_at', mode='before')
    @classmethod
    def source_time(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
                raise ValueError('Informe data e hora com fuso explícito.')
            offset = re.search(r'[+-](\d{2}):(\d{2})$', value)
            if offset and (int(offset[1]) > 23 or int(offset[2]) > 59):
                raise ValueError('Fuso horário inválido.')
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Informe data e hora com fuso explícito.')
        try:
            return value.astimezone(timezone.utc)
        except (ValueError, OverflowError):
            raise ValueError('Data e hora fora do intervalo suportado.') from None

    @model_validator(mode='after')
    def bytes(self):
        if len(self.text.encode()) > 8192:
            raise ValueError('Mensagem muito grande.')
        return self


class Enrich(Operation):
    expected_revision: Revision


class Review(Input):
    expected_revision: Revision
    decision: Literal['approved', 'rejected']
    suggested_reply: Annotated[str, StringConstraints(strict=True, max_length=8192)]

    @model_validator(mode='after')
    def draft(self):
        if self.suggested_reply.strip():
            self.suggested_reply = bounded_text(self.suggested_reply)
        elif self.decision == 'approved':
            raise ValueError('Revise uma resposta antes de aprovar.')
        else:
            self.suggested_reply = ''
        return self


class Document(Operation):
    title: Label
    mime_type: Literal['text/plain']
    content: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=32768), AfterValidator(safe_text)]

    @model_validator(mode='after')
    def bytes(self):
        if len(self.content.encode()) > 32768:
            raise ValueError('Documento muito grande.')
        return self


class Result(Strict):
    sentiment: Literal['positive', 'negative', 'neutral', 'uncertain']
    confidence: Literal['low', 'medium', 'high']
    explanation: Text
    suggested_reply: Text
    citations: list[Annotated[StrictInt, Field(ge=1, le=SAFE_MAX)]] = Field(max_length=3)


class SignedEvent(Input):
    job_id: str = Field(max_length=36)
    event_id: str = Field(max_length=36)
    timestamp: StrictInt
    attempt: Annotated[StrictInt, Field(ge=1, le=3)]
    payload: Result
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def uuids(self):
        if len(json.dumps(self.model_dump(), ensure_ascii=False).encode()) > 32768:
            raise ValueError('Evento muito grande.')
        for value in (self.job_id, self.event_id):
            if str(UUID(value)) != value:
                raise ValueError('Evento inválido.')
        return self


def guard(request, response, *, write=False, manage=False, capability=False, read_inbox=False):
    response.headers['Cache-Control'] = 'no-store'
    try:
        require_enabled()
    except HTTPException as error:
        error.headers = {'Cache-Control': 'no-store'}
        raise
    user = current()
    if request.query_params and request.method != 'DELETE':
        raise HTTPException(422, 'Confira os campos informados.')
    mode = settings.message_enrichment_mode()
    if mode not in {'disabled', 'stub'}:
        raise HTTPException(503, 'Análise não configurada.')
    if capability:
        return user
    provider_read = read_inbox and (settings.instagram_ingress_isolated_enabled() or settings.waha_ingress_isolated_enabled())
    if not provider_read and (mode != 'stub' or len(settings.message_enrichment_signing_key()) < 32):
        raise HTTPException(503, 'Análise sintética não habilitada.')
    if write and user['role'] not in {'owner', 'admin', 'member'}:
        raise HTTPException(403, 'Acesso somente leitura.')
    if manage and user['role'] not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente responsáveis podem gerenciar documentos.')
    return user


@contextmanager
def db():
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            yield conn
    except (psycopg.Error, RuntimeError):
        raise HTTPException(503, 'Análise temporariamente indisponível.', headers={'Cache-Control': 'no-store'}) from None


def lock_workspace(conn, workspace):
    conn.execute('SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE', (workspace,))


def rate_limit(conn, workspace):
    row = conn.execute("INSERT INTO socialmei.me_limits(workspace_id,count) VALUES(%s,1) ON CONFLICT(workspace_id) DO UPDATE SET bucket=CASE WHEN me_limits.bucket < NOW()-INTERVAL '1 minute' THEN NOW() ELSE me_limits.bucket END,count=CASE WHEN me_limits.bucket < NOW()-INTERVAL '1 minute' THEN 1 ELSE me_limits.count+1 END WHERE me_limits.count<60 OR me_limits.bucket<NOW()-INTERVAL '1 minute' RETURNING count", (workspace,)).fetchone()
    if not row:
        raise HTTPException(429, 'Limite sintético atingido. Aguarde um minuto.')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def operation_data(payload):
    # Optional source time must not change fingerprints of already persisted messages.
    return payload.model_dump(mode='json', exclude_none=True)


def operation(conn, workspace, kind, payload):
    value = operation_data(payload)
    row = conn.execute('SELECT fingerprint,response FROM socialmei.me_operations WHERE workspace_id=%s AND kind=%s AND operation_id=%s', (workspace, kind, payload.operation_id)).fetchone()
    if row:
        if row['fingerprint'] != fingerprint(value):
            raise HTTPException(409, 'Operação já usada com outros dados.')
        return row['response']
    return None


def remember(conn, workspace, kind, payload, response):
    conn.execute('INSERT INTO socialmei.me_operations(workspace_id,kind,operation_id,fingerprint,response) VALUES(%s,%s,%s,%s,%s)', (workspace, kind, payload.operation_id, fingerprint(operation_data(payload)), Jsonb(response)))


def invalidate_expired(conn, workspace):
    conn.execute("UPDATE socialmei.me_jobs SET status='expired',revision=revision+1,result=NULL WHERE workspace_id=%s AND status='pending' AND expires_at<=NOW()", (workspace,))
    # Expired document content is purged, including on read, before retrieval.
    conn.execute("UPDATE socialmei.me_documents SET content='',deleted_at=NOW(),revision=revision+1 WHERE workspace_id=%s AND deleted_at IS NULL AND expires_at<=NOW()", (workspace,))
    conn.execute("UPDATE socialmei.me_jobs j SET status=CASE WHEN EXISTS(SELECT 1 FROM socialmei.me_citations c JOIN socialmei.me_documents d ON d.id=c.document_id WHERE c.job_id=j.id AND d.expires_at<=NOW()) THEN 'expired' ELSE 'invalidated' END,revision=revision+1,result=NULL WHERE j.workspace_id=%s AND j.status NOT IN ('invalidated','expired') AND EXISTS(SELECT 1 FROM socialmei.me_citations c JOIN socialmei.me_documents d ON d.id=c.document_id AND d.workspace_id=c.workspace_id WHERE c.job_id=j.id AND (d.deleted_at IS NOT NULL OR d.expires_at<=NOW() OR d.revision<>c.document_revision))", (workspace,))


def envelope(row):
    result = row['result'] or {}
    return {'id': str(row['id']), 'message_id': row['message_id'], 'revision': row['revision'], 'status': row['status'], 'sentiment': result.get('sentiment', 'uncertain'), 'confidence': result.get('confidence', 'low'), 'explanation': result.get('explanation', 'Resultado indisponível; gere uma nova análise.'), 'suggested_reply': result.get('suggested_reply', ''), 'citations': result.get('citations', []), 'transport': 'none'}


def signing_data(event):
    return {'schema_version': event['schema_version'], 'job_id': event['job_id'], 'event_id': event['event_id'], 'timestamp': event['timestamp'], 'attempt': event['attempt'], 'payload_hash': fingerprint(event['payload'])}


def sign_event(job_id, attempt, payload, *, timestamp=None, event_id=None):
    event = {'schema_version': 1, 'job_id': str(job_id), 'event_id': event_id or str(uuid4()), 'timestamp': int(time.time()) if timestamp is None else timestamp, 'attempt': attempt, 'payload': payload}
    key = settings.message_enrichment_signing_key()
    if settings.message_enrichment_mode() != 'stub' or len(key) < 32:
        raise HTTPException(503, 'Adaptador não configurado.')
    event['signature'] = hmac.new(key.encode(), json.dumps(signing_data(event), sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
    return event


def process_event(conn, raw):
    with conn.transaction():
        return _process_event(conn, raw)


def verify_event(raw):
    """Authenticate the bounded envelope before any database access."""
    try:
        event = SignedEvent.model_validate(raw).model_dump()
    except ValueError:
        raise HTTPException(422, 'Evento inválido.') from None
    key = settings.message_enrichment_signing_key()
    if settings.message_enrichment_mode() != 'stub' or len(key) < 32:
        raise HTTPException(503, 'Adaptador não configurado.')
    signature = hmac.new(key.encode(), json.dumps(signing_data(raw), sort_keys=True, separators=(',', ':')).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, event['signature']):
        raise HTTPException(403, 'Assinatura inválida.')
    if abs(int(time.time()) - event['timestamp']) > 120:
        raise HTTPException(409, 'Evento expirado.')
    return event


def _process_event(conn, raw):
    """Internal adapter only. Job identity is the sole source of workspace scope."""
    event = verify_event(raw)
    found = conn.execute('SELECT workspace_id FROM socialmei.me_jobs WHERE id=%s', (event['job_id'],)).fetchone()
    if not found:
        raise HTTPException(404, 'Análise não encontrada.')
    workspace = found['workspace_id']
    lock_workspace(conn, workspace)
    invalidate_expired(conn, workspace)
    job = conn.execute('SELECT * FROM socialmei.me_jobs WHERE id=%s FOR UPDATE', (event['job_id'],)).fetchone()
    previous = conn.execute('SELECT fingerprint FROM socialmei.me_events WHERE event_id=%s', (event['event_id'],)).fetchone()
    if previous:
        if previous['fingerprint'] != fingerprint(event):
            raise HTTPException(409, 'Evento já utilizado.')
        return envelope(job)
    if job['status'] != 'pending' or job['attempt'] != event['attempt'] or job['expires_at'] <= datetime.now(timezone.utc):
        raise HTTPException(409, 'Resultado tardio ou análise já revisada.')
    message = conn.execute('SELECT revision FROM socialmei.me_messages WHERE workspace_id=%s AND id=%s', (workspace, job['message_id'])).fetchone()
    if message['revision'] != job['message_revision']:
        raise HTTPException(409, 'Uma análise mais recente substituiu este resultado.')
    rate_limit(conn, workspace)
    citations = []
    for document_id in dict.fromkeys(event['payload']['citations']):
        document = conn.execute('SELECT id,title,revision FROM socialmei.me_documents WHERE workspace_id=%s AND id=%s AND deleted_at IS NULL AND expires_at>NOW()', (workspace, document_id)).fetchone()
        if not document:
            raise HTTPException(409, 'Fonte indisponível para este negócio.')
        citations.append({'id': document['id'], 'title': document['title'], 'revision': document['revision']})
        conn.execute('INSERT INTO socialmei.me_citations(workspace_id,job_id,document_id,document_revision) VALUES(%s,%s,%s,%s)', (workspace, job['id'], document_id, document['revision']))
    result = {**event['payload'], 'citations': citations}
    row = conn.execute("UPDATE socialmei.me_jobs SET status='pending_review',revision=revision+1,result=%s WHERE id=%s RETURNING *", (Jsonb(result), job['id'])).fetchone()
    conn.execute('INSERT INTO socialmei.me_events(event_id,job_id,attempt,fingerprint) VALUES(%s,%s,%s,%s)', (event['event_id'], job['id'], event['attempt'], fingerprint(event)))
    return envelope(row)


def retry_job(conn, job_id, expected_revision):
    if settings.message_enrichment_mode() != 'stub' or len(settings.message_enrichment_signing_key()) < 32:
        raise HTTPException(503, 'Adaptador não configurado.')
    if type(expected_revision) is not int or not 1 <= expected_revision < SAFE_MAX:
        raise HTTPException(422, 'Revisão inválida.')
    found = conn.execute('SELECT workspace_id FROM socialmei.me_jobs WHERE id=%s', (job_id,)).fetchone()
    if not found:
        raise HTTPException(404, 'Análise não encontrada.')
    lock_workspace(conn, found['workspace_id'])
    rate_limit(conn, found['workspace_id'])
    row = conn.execute("UPDATE socialmei.me_jobs SET status='pending',attempt=attempt+1,revision=revision+1,expires_at=NOW()+INTERVAL '5 minutes' WHERE id=%s AND revision=%s AND (status='pending' OR (status='expired' AND result IS NULL AND NOT EXISTS(SELECT 1 FROM socialmei.me_citations WHERE job_id=me_jobs.id))) AND attempt<3 AND message_revision=(SELECT revision FROM socialmei.me_messages WHERE id=me_jobs.message_id AND workspace_id=me_jobs.workspace_id) RETURNING *", (job_id, expected_revision)).fetchone()
    if not row:
        raise HTTPException(409, 'Repetição não permitida.')
    return row


def classify_sentiment(text):
    normalized = ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))
    positive_words = {'obrigado', 'obrigada', 'otimo', 'excelente', 'adorei', 'gostei', 'bom'}
    negative_words = {'ruim', 'problema', 'reclamacao', 'horrivel', 'atraso'}
    positive = negative = False
    for clause in re.split(r'[.!?;\n]', normalized):
        tokens = re.findall(r'\w+', clause)
        for index, token in enumerate(tokens):
            negated = bool(set(tokens[max(0, index-3):index]) & {'nao', 'nunca', 'sem'})
            if token in positive_words:
                if negated:
                    negative = True
                else:
                    positive = True
            elif token in negative_words and not negated:
                negative = True
    return 'uncertain' if positive and negative else 'negative' if negative else 'positive' if positive else 'neutral'


def stub_result(conn, workspace, text):
    words = set(re.findall(r'\w{3,}', text.lower()))
    documents = conn.execute('SELECT id,title,content FROM socialmei.me_documents WHERE workspace_id=%s AND deleted_at IS NULL AND expires_at>NOW() ORDER BY id LIMIT 50', (workspace,)).fetchall()
    ranked = sorted(((len(words & set(re.findall(r'\w{3,}', d['content'].lower()))), d) for d in documents), key=lambda item: (-item[0], item[1]['id']))
    matches = [d for score, d in ranked if score > 0][:3]
    sentiment = classify_sentiment(text)
    # Document text influences retrieval only. It is never executed or inserted as instructions.
    return {'sentiment': sentiment, 'confidence': 'low', 'explanation': 'Heurística sintética por palavras e negação curta; confiança não estatística. Fontes por correspondência lexical do próprio negócio.', 'suggested_reply': 'Obrigado pela mensagem. Vou conferir as informações e retornar para você.' + (' Confira as fontes selecionadas antes de responder.' if matches else ' Ainda não há fonte correspondente.'), 'citations': [d['id'] for d in matches]}


@router.get('/capabilities')
def capabilities(request: Request, response: Response):
    user = guard(request, response, capability=True)
    result = {'schema_version': 1, 'workspace_id': user['workspace_id'], 'mode': settings.message_enrichment_mode(), 'transport': 'none'}
    if settings.instagram_ingress_isolated_enabled() or settings.instagram_live_ingress_enabled():
        result['instagram_inbox'] = True
    if settings.waha_ingress_isolated_enabled():
        result['waha_inbox'] = True
    return result


@router.post('/synthetic-messages')
def incoming(payload: Incoming, request: Request, response: Response):
    user = guard(request, response, write=True); workspace = user['workspace_id']
    with db() as conn:
        return persist_incoming(conn, workspace, payload)


def persist_incoming(conn, workspace, payload):
    lock_workspace(conn, workspace)
    prior = operation(conn, workspace, 'message', payload)
    if prior:
        return {**prior, 'replayed': True}
    external_fingerprint = fingerprint({k: v for k, v in operation_data(payload).items() if k != 'operation_id'})
    rate_limit(conn, workspace)
    result = _append_inbox_message(conn, workspace, payload, external_fingerprint, origin='synthetic')
    remember(conn, workspace, 'message', payload, result)
    return result


def _append_inbox_message(conn, workspace, payload, external_fingerprint, *, origin):
    # Trusted append only: provider ingress verifies account ownership before calling.
    # Public synthetic routes still validate Incoming and keep their quota/operation ledger.
    lock_workspace(conn, workspace)
    existing = conn.execute('SELECT m.* FROM socialmei.me_external_messages e JOIN socialmei.me_messages m ON m.workspace_id=e.workspace_id AND m.id=e.message_id WHERE e.workspace_id=%s AND e.channel=%s AND e.account_ref=%s AND e.external_message_id=%s AND e.origin=%s', (workspace, payload.channel, payload.account_ref, payload.external_message_id, origin)).fetchone()
    if existing:
        if existing['fingerprint'] != external_fingerprint:
            raise HTTPException(409, 'Mensagem externa já usada com outros dados.')
        return {'conversation_id': existing['conversation_id'], 'message_id': existing['id'], 'revision': existing['conversation_revision'], 'replayed': True}
    conv = conn.execute('INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name,origin) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(workspace_id,channel,account_ref,contact_ref) DO UPDATE SET contact_name=me_conversations.contact_name RETURNING *', (workspace, payload.channel, payload.account_ref, payload.contact_ref, payload.contact_name, origin)).fetchone()
    revision = conn.execute('UPDATE socialmei.me_conversations SET revision=revision+1 WHERE id=%s RETURNING revision', (conv['id'],)).fetchone()['revision']
    message = conn.execute('INSERT INTO socialmei.me_messages(workspace_id,conversation_id,external_message_id,text,fingerprint,conversation_revision,occurred_at,origin) VALUES(%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()),%s) RETURNING id', (workspace, conv['id'], payload.external_message_id, payload.text, external_fingerprint, revision, payload.occurred_at, origin)).fetchone()
    conn.execute('INSERT INTO socialmei.me_external_messages(workspace_id,channel,account_ref,external_message_id,message_id,origin) VALUES(%s,%s,%s,%s,%s,%s)', (workspace, payload.channel, payload.account_ref, payload.external_message_id, message['id'], origin))
    return {'conversation_id': conv['id'], 'message_id': message['id'], 'revision': revision, 'replayed': False}


@router.get('/conversations')
def conversations(request: Request, response: Response):
    workspace = guard(request, response, read_inbox=True)['workspace_id']
    origins = ['synthetic'] if settings.message_enrichment_mode() == 'stub' else []
    if settings.instagram_ingress_isolated_enabled() or settings.instagram_live_ingress_enabled():
        origins.append('instagram')
    if settings.waha_ingress_isolated_enabled():
        origins.append('waha')
    with db() as conn:
        if 'synthetic' in origins:
            invalidate_expired(conn, workspace)
        items = conn.execute('SELECT id,channel,account_ref,contact_ref,contact_name,revision,origin FROM socialmei.me_conversations WHERE workspace_id=%s AND origin=ANY(%s) ORDER BY id DESC LIMIT 100', (workspace, origins)).fetchall()
        for conversation in items:
            messages = conn.execute('SELECT id,external_message_id,text,occurred_at,revision FROM socialmei.me_messages WHERE workspace_id=%s AND conversation_id=%s ORDER BY occurred_at DESC,id DESC LIMIT 100', (workspace, conversation['id'])).fetchall()
            for message in messages:
                job = conn.execute('SELECT * FROM socialmei.me_jobs WHERE workspace_id=%s AND message_id=%s ORDER BY message_revision DESC,id DESC LIMIT 1', (workspace, message['id'])).fetchone() if conversation['origin'] == 'synthetic' else None
                message['enrichment'] = envelope(job) if job else None
            conversation['messages'] = list(reversed(messages))
            if conversation['origin'] == 'synthetic':
                del conversation['origin']
        return {'workspace_id': workspace, 'items': items}


@router.post('/messages/{message_id}/enrich')
def enrich(message_id: Id, payload: Enrich, request: Request, response: Response):
    workspace = guard(request, response, write=True)['workspace_id']
    with db() as conn:
        lock_workspace(conn, workspace)
        prior = operation(conn, workspace, 'enrich', payload)
        if prior:
            # Do not resurrect cached text after source deletion or human review.
            if prior['message_id'] != message_id:
                raise HTTPException(409, 'Operação pertence a outra mensagem.')
            invalidate_expired(conn, workspace)
            job = conn.execute('SELECT * FROM socialmei.me_jobs WHERE workspace_id=%s AND id=%s', (workspace, prior['id'])).fetchone()
            return envelope(job)
        message = conn.execute('SELECT * FROM socialmei.me_messages WHERE workspace_id=%s AND id=%s FOR UPDATE', (workspace, message_id)).fetchone()
        if not message:
            raise HTTPException(404, 'Mensagem não encontrada.')
        if message['origin'] != 'synthetic':
            raise HTTPException(409, 'Análise sintética indisponível para esta origem.')
        if message['revision'] != payload.expected_revision:
            raise HTTPException(409, 'A mensagem mudou. Recarregue antes de analisar.')
        rate_limit(conn, workspace); invalidate_expired(conn, workspace)
        revision = conn.execute('UPDATE socialmei.me_messages SET revision=revision+1 WHERE id=%s RETURNING revision', (message_id,)).fetchone()['revision']
        conn.execute("UPDATE socialmei.me_jobs SET status='superseded',revision=revision+1 WHERE workspace_id=%s AND message_id=%s AND status IN ('pending','pending_review')", (workspace, message_id))
        job = conn.execute('INSERT INTO socialmei.me_jobs(id,workspace_id,message_id,message_revision) VALUES(%s,%s,%s,%s) RETURNING *', (uuid4(), workspace, message_id, revision)).fetchone()
        result = process_event(conn, sign_event(job['id'], job['attempt'], stub_result(conn, workspace, message['text'])))
        remember(conn, workspace, 'enrich', payload, result)
        return result


@router.get('/conversations/{conversation_id}/enrichments')
def history(conversation_id: Id, request: Request, response: Response):
    workspace = guard(request, response)['workspace_id']
    with db() as conn:
        if not conn.execute('SELECT id FROM socialmei.me_conversations WHERE workspace_id=%s AND id=%s', (workspace, conversation_id)).fetchone():
            raise HTTPException(404, 'Conversa não encontrada.')
        invalidate_expired(conn, workspace)
        jobs = conn.execute('SELECT j.* FROM socialmei.me_jobs j JOIN socialmei.me_messages m ON m.workspace_id=j.workspace_id AND m.id=j.message_id WHERE j.workspace_id=%s AND m.conversation_id=%s ORDER BY j.created_at DESC,j.id DESC LIMIT 100', (workspace, conversation_id)).fetchall()
        return {'items': [envelope(job) for job in jobs]}


@router.patch('/jobs/{job_id}/review')
def review(job_id: UUID, payload: Review, request: Request, response: Response):
    workspace = guard(request, response, write=True)['workspace_id']
    with db() as conn:
        lock_workspace(conn, workspace); invalidate_expired(conn, workspace)
        job = conn.execute('SELECT * FROM socialmei.me_jobs WHERE workspace_id=%s AND id=%s FOR UPDATE', (workspace, job_id)).fetchone()
        if not job:
            raise HTTPException(404, 'Análise não encontrada.')
        message = conn.execute('SELECT revision FROM socialmei.me_messages WHERE workspace_id=%s AND id=%s', (workspace, job['message_id'])).fetchone()
        if job['revision'] != payload.expected_revision or job['status'] != 'pending_review' or message['revision'] != job['message_revision']:
            raise HTTPException(409, 'A análise mudou ou já foi revisada.')
        result = {**job['result'], 'suggested_reply': payload.suggested_reply}
        row = conn.execute('UPDATE socialmei.me_jobs SET status=%s,result=%s,revision=revision+1 WHERE id=%s RETURNING *', (payload.decision, Jsonb(result), job_id)).fetchone()
        return envelope(row)


@router.get('/documents')
def documents(request: Request, response: Response):
    workspace = guard(request, response)['workspace_id']
    with db() as conn:
        invalidate_expired(conn, workspace)
        return {'workspace_id': workspace, 'items': conn.execute('SELECT id,title,revision,expires_at FROM socialmei.me_documents WHERE workspace_id=%s AND deleted_at IS NULL AND expires_at>NOW() ORDER BY id DESC LIMIT 50', (workspace,)).fetchall()}


@router.post('/documents')
def create_document(payload: Document, request: Request, response: Response):
    workspace = guard(request, response, write=True, manage=True)['workspace_id']
    with db() as conn:
        lock_workspace(conn, workspace); invalidate_expired(conn, workspace)
        prior = operation(conn, workspace, 'document', payload)
        if prior:
            doc = conn.execute('SELECT id,title,revision,expires_at,deleted_at FROM socialmei.me_documents WHERE workspace_id=%s AND id=%s', (workspace, prior['id'])).fetchone()
            if doc['deleted_at'] is not None:
                raise HTTPException(409, 'Documento removido ou expirado.')
            return {k: v for k, v in doc.items() if k != 'deleted_at'}
        count = conn.execute('SELECT COUNT(*) AS count FROM socialmei.me_documents WHERE workspace_id=%s AND deleted_at IS NULL', (workspace,)).fetchone()['count']
        if count >= 50:
            raise HTTPException(429, 'Limite de 50 documentos ativos atingido.')
        rate_limit(conn, workspace)
        row = conn.execute('INSERT INTO socialmei.me_documents(workspace_id,title,content) VALUES(%s,%s,%s) RETURNING id,title,revision,expires_at', (workspace, payload.title, payload.content)).fetchone()
        remember(conn, workspace, 'document', payload, {**row, 'expires_at': row['expires_at'].isoformat()})
        return row


@router.delete('/documents/{document_id}')
def delete_document(document_id: Id, request: Request, response: Response, expected_revision: Annotated[str, Query()]):
    workspace = guard(request, response, write=True, manage=True)['workspace_id']
    if set(request.query_params) != {'expected_revision'} or len(request.query_params.getlist('expected_revision')) != 1 or not re.fullmatch(r'[1-9][0-9]{0,15}', expected_revision) or int(expected_revision) > SAFE_MAX-1:
        raise HTTPException(422, 'Revisão inválida.')
    with db() as conn:
        lock_workspace(conn, workspace)
        row = conn.execute('SELECT revision,deleted_at FROM socialmei.me_documents WHERE workspace_id=%s AND id=%s', (workspace, document_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Documento não encontrado.')
        if row['revision'] != int(expected_revision) or row['deleted_at'] is not None:
            raise HTTPException(409, 'O documento mudou ou já foi removido.')
        conn.execute("UPDATE socialmei.me_documents SET content='',deleted_at=NOW(),revision=revision+1 WHERE workspace_id=%s AND id=%s", (workspace, document_id))
        invalidate_expired(conn, workspace)
        return {'id': document_id, 'revision': row['revision']+1, 'deleted': True}


def unique_json_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


@internal_router.post('/results')
async def internal_result(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    if settings.message_enrichment_mode() != 'stub' or len(settings.message_enrichment_signing_key()) < 32:
        raise HTTPException(503, 'Adaptador não configurado.')
    if request.query_params or request.headers.get('content-type', '').split(';', 1)[0].lower() != 'application/json':
        raise HTTPException(422, 'Evento inválido.')
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > 32768:
            raise HTTPException(422, 'Evento muito grande.')
        content.extend(chunk)
    try:
        raw = json.loads(content, object_pairs_hook=unique_json_fields)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(422, 'Evento inválido.') from None
    verify_event(raw)
    # Signature, schema, size and time have all passed before opening PostgreSQL.
    return await run_in_threadpool(receive_internal_event, raw)


def receive_internal_event(raw):
    verify_event(raw)
    with db() as conn:
        return process_event(conn, raw)
