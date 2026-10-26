"""Durable preparation and simulated dispatch. No network, secrets or uploaded bytes."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field, StrictBool, StrictInt, model_validator

import settings
from account_auth import current, require_enabled
from database import connect
from instagram_simulation import Strict, MediaManifest, FORMATS, AccountInput

def boundary(request: Request, response: Response):
    response.headers['Cache-Control']='no-store'
    if request.query_params:
        raise HTTPException(422,'Parâmetros de consulta não suportados.')
    try:
        yield
    except (psycopg.Error, RuntimeError):
        raise HTTPException(503,'Preparação temporariamente indisponível. Nenhum envio foi feito.') from None


router = APIRouter(prefix='/api/v1/content/preparation', tags=['content preparation simulation'], dependencies=[Depends(boundary)])
WRITERS = {'owner', 'admin', 'member'}


def mode_guard(write=False):
    require_enabled()
    if settings.content_preparation_mode() != 'simulation':
        raise HTTPException(503, 'Preparação compartilhada não habilitada. Nenhuma publicação disponível.')
    user = current()
    if write and user['role'] not in WRITERS:
        raise HTTPException(403, 'Acesso somente leitura.')
    if write:
        rate_limit(user)
    return user


def rate_limit(user):
    key = hashlib.sha256(f"preparation:{user['workspace_id']}:{user['id']}".encode()).hexdigest()
    with connect() as conn:
        count = conn.execute("INSERT INTO socialmei.auth_limites(chave) VALUES (%s) ON CONFLICT(chave) DO UPDATE SET tentativas=CASE WHEN auth_limites.inicio<now()-interval '1 minute' THEN 1 ELSE auth_limites.tentativas+1 END,inicio=CASE WHEN auth_limites.inicio<now()-interval '1 minute' THEN now() ELSE auth_limites.inicio END RETURNING tentativas", (key,)).fetchone()[0]
        if count > 60:
            conn.commit()
            raise HTTPException(429, 'Muitas operações. Aguarde um minuto.', headers={'Retry-After':'60'})


class CaptionInput(Strict):
    topic: str = Field(min_length=1, max_length=160)
    business: str = Field(default='', max_length=120)
    offering: str = Field(default='', max_length=160)
    objective: Literal['informar', 'apresentar', 'convidar'] = 'informar'
    tone: Literal['simples', 'acolhedor', 'profissional'] = 'simples'

    @model_validator(mode='after')
    def clean(self):
        if not self.topic.strip():
            raise ValueError('Informe um tema.')
        return self


def caption_suggestions(payload):
    subject = payload.topic.strip()
    offering = (' Sobre: ' + payload.offering.strip() + '.') if payload.offering.strip() else ''
    business = (' — ' + payload.business.strip()) if payload.business.strip() else ''
    endings = {
        'informar': 'Converse com a gente para conferir os detalhes.',
        'apresentar': 'Quer conhecer melhor? Tire suas dúvidas com a gente.',
        'convidar': 'Se fizer sentido para você, fale com a gente.',
    }
    greeting = {'simples': '', 'acolhedor': 'Vamos conversar? ', 'profissional': 'Saiba mais: '}[payload.tone]
    return {
        'source': 'template_fixture', 'generated_by_ai': False,
        'notice': 'Modelo de texto local demonstrativo. Nenhum agente de IA ou workflow foi executado; revise antes de usar.',
        'alternatives': [greeting + subject + '.' + offering + ' ' + endings[payload.objective] + business,
                         subject + offering + '\nQuer mais informações? Envie sua dúvida.' + business,
                         'Vamos falar sobre ' + subject + '?' + offering + '\nConfira os detalhes com a gente.' + business],
        'hashtags': ['#MeuNegocio', '#Empreendedorismo'],
    }


class ImageInput(Strict):
    brief: str = Field(min_length=1, max_length=1000)


class JobInput(Strict):
    idempotency_key: UUID
    account_id: UUID | None = None
    title: str = Field(default='', max_length=120)
    format: Literal['feed', 'story', 'reel']
    caption: str = Field(default='', max_length=2200)
    media: list[MediaManifest] = Field(default_factory=list, max_length=10)
    status: Literal['draft', 'pending_review', 'scheduled'] = 'draft'
    reviewed: StrictBool = False
    scheduled_for: datetime | None = None
    timezone: str = Field(default='America/Fortaleza', max_length=80)

    @model_validator(mode='after')
    def validate_job(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Fuso horário inválido.') from None
        if self.format != 'feed' and len(self.media) > 1:
            raise ValueError('Story/Reel aceita uma mídia neste contrato.')
        for item in self.media:
            if item.mime not in FORMATS[self.format]:
                raise ValueError('Mídia incompatível com o formato.')
            if item.mime.startswith('image/') and item.size > 10 * 1024 * 1024:
                raise ValueError('Imagem excede o limite.')
        if self.scheduled_for:
            when = self.scheduled_for
            if when.tzinfo is None or when.utcoffset() is None:
                raise ValueError('Data exige offset e fuso horário.')
        if self.status == 'scheduled' and not (self.reviewed and self.account_id and self.media and self.scheduled_for):
            raise ValueError('Revise legenda e mídia, selecione conta fictícia e horário antes de agendar.')
        return self


class UpdateInput(JobInput):
    revision: StrictInt = Field(ge=1, le=9007199254740990)


class Revision(Strict):
    revision: StrictInt = Field(ge=1, le=9007199254740990)


def validate_schedule(payload):
    if payload.status == 'scheduled' and not datetime.now(timezone.utc)+timedelta(seconds=30)<payload.scheduled_for<datetime.now(timezone.utc)+timedelta(days=365):
        raise HTTPException(422, 'Escolha um horário futuro, em até um ano.')


def view(row):
    return {
        'workspace_id':row['workspace_id'],'id': str(row['id']), 'idempotency_key': str(row['idempotency_key']), 'account_id': str(row['account_id']) if row['account_id'] else None,
        'revision': row['revision'], 'title': row['title'], 'format': row['format'],
        'caption': row['caption'], 'media': row['media_manifest'],
        'scheduled_for': row['scheduled_for'], 'timezone': row['timezone'],
        'status': row['status'], 'attempts': row['attempts'], 'last_error_code': row['last_error_code'],
        'created_at': row['created_at'], 'updated_at': row['updated_at'],
        'published': False, 'transport': 'none', 'media_stored': False,
    }


def event(cur, workspace, job, status, code=None):
    cur.execute('INSERT INTO socialmei.content_preparation_events(workspace_id,job_id,status,code) VALUES (%s,%s,%s,%s)', (workspace, job, status, code))


def check_account(cur, workspace, account):
    if account is not None:
        cur.execute('SELECT 1 FROM socialmei.instagram_sim_accounts WHERE workspace_id=%s AND id=%s', (workspace, account))
        if not cur.fetchone():
            raise HTTPException(404, 'Conta fictícia não encontrada neste negócio.')


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload.model_dump(mode='json'), ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@router.get('/status')
def status():
    user=mode_guard()
    return {'workspace_id':user['workspace_id'],'mode': 'simulation', 'transport': 'none', 'published': False, 'caption_adapter': 'template_fixture', 'image_adapter': 'unavailable', 'scheduling': 'persisted_simulation', 'media_storage': 'metadata_only'}


@router.get('/accounts')
def accounts():
    user = mode_guard()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT id,label FROM socialmei.instagram_sim_accounts WHERE workspace_id=%s ORDER BY created_at,id LIMIT 50', (user['workspace_id'],))
        return {'workspace_id':user['workspace_id'],'items': [{'id': str(r['id']), 'label': r['label'], 'simulated': True} for r in cur.fetchall()]}


@router.post('/accounts', status_code=201)
def add_account(payload: AccountInput):
    user = mode_guard(write=True)
    if user['role'] not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente o responsável pode criar uma conta fictícia.')
    account = uuid4()
    with connect() as conn:
        conn.execute('INSERT INTO socialmei.instagram_sim_accounts(workspace_id,id,label,created_by) VALUES (%s,%s,%s,%s)', (user['workspace_id'], account, payload.label, user['id']))
    return {'workspace_id':user['workspace_id'],'id': str(account), 'label': payload.label, 'simulated': True}


@router.post('/captions')
def captions(payload: CaptionInput):
    user=mode_guard(write=True)
    return {**caption_suggestions(payload),'workspace_id':user['workspace_id']}


@router.post('/images')
def images(payload: ImageInput):
    mode_guard(write=True)
    raise HTTPException(503, 'Geração de imagem não conectada. Envie sua própria mídia; nenhum arquivo foi gerado.')


@router.get('/jobs')
def jobs():
    user = mode_guard()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM socialmei.content_preparation_jobs WHERE workspace_id=%s ORDER BY created_at DESC,id DESC LIMIT 100', (user['workspace_id'],))
        return {'workspace_id':user['workspace_id'],'items': [view(r) for r in cur.fetchall()]}


@router.get('/jobs/{job_id}')
def get_job(job_id: UUID):
    user = mode_guard()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM socialmei.content_preparation_jobs WHERE workspace_id=%s AND id=%s', (user['workspace_id'], job_id))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, 'Preparação não encontrada neste negócio.')
        cur.execute('SELECT status,code,created_at FROM socialmei.content_preparation_events WHERE workspace_id=%s AND job_id=%s ORDER BY id DESC LIMIT 30', (user['workspace_id'], job_id))
        return {**view(row), 'events': cur.fetchall()}


@router.post('/jobs', status_code=201)
def create(payload: JobInput, response: Response):
    user = mode_guard(write=True)
    workspace = user['workspace_id']
    key = fingerprint(payload)
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('content-preparation:'+str(workspace),))
        check_account(cur, workspace, payload.account_id)
        cur.execute('SELECT * FROM socialmei.content_preparation_jobs WHERE workspace_id=%s AND idempotency_key=%s', (workspace, payload.idempotency_key))
        old = cur.fetchone()
        if old:
            if old['fingerprint'] != key:
                raise HTTPException(409, 'Operação já usada com outro conteúdo.')
            response.status_code = 200
            return view(old)
        cur.execute("SELECT count(*) AS count FROM socialmei.content_preparation_jobs WHERE workspace_id=%s AND created_at>now()-interval '1 minute'", (workspace,))
        if cur.fetchone()['count'] >= 20:
            raise HTTPException(429, 'Muitas preparações. Aguarde um minuto antes de tentar novamente.')
        validate_schedule(payload)
        jid = uuid4()
        cur.execute('INSERT INTO socialmei.content_preparation_jobs(workspace_id,id,account_id,requested_by,idempotency_key,fingerprint,title,format,caption,media_manifest,scheduled_for,timezone,status,run_after) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                    (workspace,jid,payload.account_id,user['id'],payload.idempotency_key,key,payload.title,payload.format,payload.caption,Jsonb([m.model_dump() for m in payload.media]),payload.scheduled_for,payload.timezone,payload.status,payload.scheduled_for))
        row = cur.fetchone()
        event(cur, workspace, jid, payload.status)
        return view(row)


@router.put('/jobs/{job_id}')
def update(job_id: UUID, payload: UpdateInput):
    user = mode_guard(write=True)
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM socialmei.content_preparation_jobs WHERE workspace_id=%s AND id=%s FOR UPDATE', (user['workspace_id'],job_id))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(404, 'Preparação não encontrada neste negócio.')
        if row['revision'] != payload.revision or row['status'] in {'processing','simulated','cancelled','uncertain'}:
            raise HTTPException(409, 'Preparação mudou ou está encerrada. Atualize o histórico antes de editar.')
        if row['idempotency_key'] != payload.idempotency_key:
            raise HTTPException(409, 'Identificador da preparação mudou.')
        validate_schedule(payload)
        check_account(cur,user['workspace_id'],payload.account_id)
        cur.execute('UPDATE socialmei.content_preparation_jobs SET account_id=%s,title=%s,format=%s,caption=%s,media_manifest=%s,scheduled_for=%s,timezone=%s,status=%s,run_after=%s,revision=revision+1,updated_at=now(),attempts=0,last_error_code=NULL WHERE workspace_id=%s AND id=%s RETURNING *',
                    (payload.account_id,payload.title,payload.format,payload.caption,Jsonb([m.model_dump() for m in payload.media]),payload.scheduled_for,payload.timezone,payload.status,payload.scheduled_for,user['workspace_id'],job_id))
        result = view(cur.fetchone());event(cur,user['workspace_id'],job_id,payload.status);return result


@router.post('/jobs/{job_id}/cancel')
def cancel(job_id: UUID, payload: Revision):
    user = mode_guard(write=True)
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT * FROM socialmei.content_preparation_jobs WHERE workspace_id=%s AND id=%s FOR UPDATE', (user['workspace_id'],job_id))
        row=cur.fetchone()
        if row is None:raise HTTPException(404,'Preparação não encontrada neste negócio.')
        if row['revision']!=payload.revision or row['status'] in {'processing','simulated','cancelled','uncertain'}:raise HTTPException(409,'Preparação mudou ou não pode mais ser cancelada.')
        cur.execute("UPDATE socialmei.content_preparation_jobs SET status='cancelled',revision=revision+1,updated_at=now() WHERE workspace_id=%s AND id=%s RETURNING *",(user['workspace_id'],job_id))
        result=view(cur.fetchone());event(cur,user['workspace_id'],job_id,'cancelled');return result


class TransientFailure(Exception):
    pass


class UncertainOutcome(Exception):
    pass


def simulate_dispatch(job):
    return {'published': False, 'transport': 'none'}


def run_due(workspace, *, limit=10, processor=simulate_dispatch):
    """Restart-safe lease recovery is ONLY valid for this side-effect-free adapter."""
    if settings.content_preparation_mode()!='simulation':raise RuntimeError('Simulation worker disabled')
    if not isinstance(workspace,int) or workspace<1 or not 1<=limit<=20:raise ValueError('Invalid worker scope')
    now=datetime.now(timezone.utc)
    claims=[]
    with connect() as conn,conn.cursor(row_factory=dict_row) as cur:
        cur.execute("UPDATE socialmei.content_preparation_jobs SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'scheduled' END,run_after=%s,claim_token=NULL,lease_until=NULL,last_error_code='simulation_lease_expired',revision=revision+1,updated_at=now() WHERE workspace_id=%s AND status='processing' AND lease_until<%s",(now,workspace,now))
        cur.execute("SELECT * FROM socialmei.content_preparation_jobs WHERE workspace_id=%s AND status='scheduled' AND run_after<=%s AND attempts<3 ORDER BY run_after,id FOR UPDATE SKIP LOCKED LIMIT %s",(workspace,now,limit))
        for row in cur.fetchall():
            token=uuid4()
            cur.execute("UPDATE socialmei.content_preparation_jobs SET status='processing',attempts=attempts+1,claim_token=%s,lease_until=%s,revision=revision+1,updated_at=now() WHERE workspace_id=%s AND id=%s RETURNING *",(token,now+timedelta(seconds=60),workspace,row['id']))
            claims.append(cur.fetchone());event(cur,workspace,row['id'],'processing')
    results=[]
    for row in claims:
        state='simulated';code=None
        try:
            result=processor(view(row))
            if result!={'published':False,'transport':'none'}:raise UncertainOutcome()
        except TransientFailure:
            state='scheduled' if row['attempts']<3 else 'failed';code='adapter_temporary_failure'
        except Exception:
            state='uncertain';code='adapter_outcome_unknown'
        with connect() as conn,conn.cursor(row_factory=dict_row) as cur:
            cur.execute('UPDATE socialmei.content_preparation_jobs SET status=%s,last_error_code=%s,run_after=%s,claim_token=NULL,lease_until=NULL,revision=revision+1,updated_at=now() WHERE workspace_id=%s AND id=%s AND status=\'processing\' AND claim_token=%s RETURNING *',(state,code,datetime.now(timezone.utc)+timedelta(seconds=30*row['attempts']),workspace,row['id'],row['claim_token']))
            updated=cur.fetchone()
            if updated:
                event(cur,workspace,row['id'],state,code);results.append(view(updated))
    return {'workspace_id':workspace,'items':results,'published':False,'transport':'none'}


class Empty(Strict):
    pass


@router.post('/run-due')
def process_due(payload: Empty):
    user=mode_guard(write=True)
    return run_due(user['workspace_id'])


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Process only persisted simulated jobs; no provider transport.')
    parser.add_argument('--workspace',type=int,required=True)
    parser.add_argument('--once',action='store_true',required=True)
    args=parser.parse_args()
    result=run_due(args.workspace)
    print(json.dumps({'processed':len(result['items']),'published':False,'transport':'none'}))
