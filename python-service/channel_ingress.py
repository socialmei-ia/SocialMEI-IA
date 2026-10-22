"""Controlled WAHA and Instagram fixtures; no provider webhook or sending path."""
import hashlib
import hmac
import json
import time
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import Field, StrictBool, StrictInt, StringConstraints, field_validator, model_validator
from starlette.concurrency import run_in_threadpool
import message_enrichment as enrichment
import settings

router = APIRouter(prefix='/api/v1/channel-lab', tags=['controlled channel fixtures'])
internal_router = APIRouter(prefix='/internal/channel-ingress', tags=['signed fixture ingress'])
FixtureRef = Annotated[str, StringConstraints(strict=True, pattern=r'^fixture-[A-Za-z0-9_.-]{1,60}$')]


class Channel(enrichment.Strict):
    instance: FixtureRef
    session: FixtureRef
    name: enrichment.Label


class Message(enrichment.Strict):
    id: enrichment.Label
    sender: enrichment.Label = Field(alias='from')
    fromMe: StrictBool
    type: Literal['chat']
    body: enrichment.Text
    notifyName: enrichment.Label

    @field_validator("fromMe")
    @classmethod
    def only_incoming(cls, value):
        if value:
            raise ValueError("Somente mensagens recebidas de teste.")
        return value


class Event(enrichment.Input):
    event_id: str = Field(max_length=36)
    timestamp: StrictInt
    instance: FixtureRef
    session: FixtureRef
    event: Literal['message']
    payload: Message
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_id(self):
        if str(UUID(self.event_id)) != self.event_id:
            raise ValueError('Evento inválido.')
        return self


class InstagramEvent(enrichment.Input):
    event_id: str = Field(max_length=36)
    timestamp: StrictInt
    account_id: str = Field(max_length=36)
    kind: Literal['incoming_text']
    sender_ref: FixtureRef
    sender_name: enrichment.Label
    message_id: enrichment.Label
    text: enrichment.Text
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')

    @field_validator('event_id', 'account_id')
    @classmethod
    def canonical_id(cls, value):
        if str(UUID(value)) != value:
            raise ValueError('Identidade de teste inválida.')
        return value


def enabled():
    enrichment.require_enabled()
    if (settings.channel_ingress_mode() != 'fixture' or settings.authentication_mode() != 'enabled'
            or settings.message_enrichment_mode() != 'stub'
            or len(settings.channel_ingress_signing_key()) < 32
            or len(settings.message_enrichment_signing_key()) < 32):
        raise HTTPException(503, 'Recepção de teste não habilitada.', headers={'Cache-Control':'no-store'})


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def sign_fixture(value):
    # Only isolated producers use this helper. The browser never receives this key.
    value={k:v for k,v in value.items() if k!='signature'}
    signature=hmac.new(settings.channel_ingress_signing_key().encode(),canonical(value),hashlib.sha256).hexdigest()
    return {**value,'signature':signature}


def verify_fixture(raw):
    enabled()
    try:
        event=Event.model_validate(raw)
    except (ValueError,TypeError,RecursionError):
        raise HTTPException(422,'Evento de teste inválido.') from None
    value=event.model_dump(by_alias=True,exclude={'signature'})
    expected=sign_fixture(value)['signature']
    if not hmac.compare_digest(expected,event.signature):
        raise HTTPException(403,'Assinatura inválida.')
    if abs(int(time.time())-event.timestamp)>120:
        raise HTTPException(409,'Evento expirado.')
    return event


def instagram_enabled():
    enabled()
    if settings.instagram_mode() != 'simulation':
        raise HTTPException(503, 'Recepção Instagram fictícia não habilitada.')


def verify_instagram_fixture(raw):
    instagram_enabled()
    try:
        event = InstagramEvent.model_validate(raw)
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, 'Evento Instagram de teste inválido.') from None
    value = event.model_dump(exclude={'signature'})
    if not hmac.compare_digest(sign_fixture(value)['signature'], event.signature):
        raise HTTPException(403, 'Assinatura inválida.')
    if abs(int(time.time()) - event.timestamp) > 120:
        raise HTTPException(409, 'Evento expirado.')
    return event


@router.get('/instagram/status')
def instagram_status(request: Request, response: Response):
    user = enrichment.guard(request, response, capability=True)
    try:
        instagram_enabled()
        available = True
    except HTTPException:
        available = False
    return {'workspace_id': user['workspace_id'], 'mode': 'fixture' if available else 'disabled',
            'account_source': 'instagram_simulation', 'fixture_ingress_available': available,
            'readiness_state': 'not_connected', 'connected': False, 'can_receive_real': False,
            'can_send': False, 'can_publish': False, 'transport': 'none',
            'blockers': ['Autorização Meta e permissões ainda não verificadas.',
                         'Workflow e contrato real ainda não homologados.',
                         'Webhook Meta, renovação e revogação de autorização ainda não implementados.']}


def human(request,response,manage=False):
    response.headers['Cache-Control']='no-store'
    enabled()
    return enrichment.guard(request,response,write=manage,manage=manage)


@router.get('/accounts')
def accounts(request:Request,response:Response):
    user=human(request,response)
    with enrichment.db() as conn:
        rows=conn.execute("SELECT id,instancia AS instance,sessao AS session,nome AS name FROM socialmei.crm_canais WHERE workspace_id=%s AND instancia LIKE 'fixture-%%' AND sessao LIKE 'fixture-%%' AND provedor='waha' AND NOT ativo AND NOT envio_habilitado ORDER BY id",(user['workspace_id'],)).fetchall()
    return {'workspace_id':user['workspace_id'],'mode':'fixture','transport':'none','items':rows}


@router.post('/accounts')
def create_account(payload:Channel,request:Request,response:Response):
    user=human(request,response,manage=True)
    with enrichment.db() as conn:
        enrichment.lock_workspace(conn,user['workspace_id'])
        enrichment.rate_limit(conn,user['workspace_id'])
        row=conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,provedor,instancia,sessao,nome) VALUES(%s,'waha',%s,%s,%s) ON CONFLICT(provedor,instancia,sessao) DO NOTHING RETURNING id",(user['workspace_id'],payload.instance,payload.session,payload.name)).fetchone()
        if not row:
            row=conn.execute("SELECT id,nome FROM socialmei.crm_canais WHERE workspace_id=%s AND provedor='waha' AND instancia=%s AND sessao=%s AND NOT ativo AND NOT envio_habilitado",(user['workspace_id'],payload.instance,payload.session)).fetchone()
            if not row or row['nome']!=payload.name:
                raise HTTPException(409,'Referência de teste indisponível.')
    return {'id':row['id'],'instance':payload.instance,'session':payload.session,'mode':'fixture','transport':'none','sending_enabled':False}


def receive(raw):
    event=verify_fixture(raw)
    with enrichment.db() as conn:
        # A signed instance/session resolves the stored owner, never a workspace selector.
        channel=conn.execute("SELECT id,workspace_id FROM socialmei.crm_canais WHERE provedor='waha' AND instancia=%s AND sessao=%s AND NOT ativo AND NOT envio_habilitado",(event.instance,event.session)).fetchone()
        if not channel:
            raise HTTPException(404,'Conta de teste não encontrada.')
        contact=hashlib.sha256(event.payload.sender.encode()).hexdigest()
        payload=enrichment.Incoming(schema_version=1,operation_id=event.event_id,channel='whatsapp',account_ref='synthetic:waha-fixture-'+str(channel['id']),contact_ref='synthetic:'+contact,contact_name=event.payload.notifyName,external_message_id=event.payload.id,text=event.payload.body)
        result=enrichment.persist_incoming(conn,channel['workspace_id'],payload)
        return {**result,'mode':'fixture','transport':'none','sent':False}


def receive_instagram(raw):
    event = verify_instagram_fixture(raw)
    with enrichment.db() as conn:
        # Simulation UUIDs are not Meta identities. Refuse ambiguous ownership.
        rows = conn.execute('SELECT workspace_id FROM socialmei.instagram_sim_accounts WHERE id=%s ORDER BY workspace_id LIMIT 2', (UUID(event.account_id),)).fetchall()
        if not rows:
            raise HTTPException(404, 'Conta fictícia não encontrada.')
        if len(rows) != 1:
            raise HTTPException(409, 'Identidade fictícia ambígua. Confira a conta antes de repetir.')
        contact = hashlib.sha256(event.sender_ref.encode()).hexdigest()
        payload = enrichment.Incoming(schema_version=1, operation_id=event.event_id,
                    channel='instagram', account_ref='synthetic:instagram-fixture:' + event.account_id,
                    contact_ref='synthetic:' + contact, contact_name=event.sender_name,
                    external_message_id=event.message_id, text=event.text)
        result = enrichment.persist_incoming(conn, rows[0]['workspace_id'], payload)
        return {**result, 'mode': 'fixture', 'transport': 'none', 'sent': False}


async def read_fixture(request):
    if request.query_params or request.headers.get('content-type','').split(';',1)[0].lower()!='application/json':
        raise HTTPException(422,'Evento inválido.')
    content=bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk)>16384:
            raise HTTPException(422,'Evento muito grande.')
        content.extend(chunk)
    try:
        raw=json.loads(content,object_pairs_hook=enrichment.unique_json_fields)
    except (ValueError,UnicodeError,RecursionError):
        raise HTTPException(422,'Evento inválido.') from None
    return raw


@internal_router.post('/waha')
async def incoming(request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    enabled()
    raw = await read_fixture(request)
    return await run_in_threadpool(receive,raw)


@internal_router.post('/instagram-fixture')
async def instagram_incoming(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    instagram_enabled()
    raw = await read_fixture(request)
    return await run_in_threadpool(receive_instagram, raw)
