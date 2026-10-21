"""Controlled WAHA-shaped fixture reception; no live connector or sending path."""
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


@internal_router.post('/waha')
async def incoming(request:Request,response:Response):
    response.headers['Cache-Control']='no-store'
    enabled()
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
    verify_fixture(raw)
    return await run_in_threadpool(receive,raw)
