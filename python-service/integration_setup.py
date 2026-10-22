"""Public test-account preparation metadata. Never credentials or live transport."""
import re
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from account_auth import current, require_enabled
from database import connect, shared_data_enabled


def boundary(request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    require_enabled()
    if not shared_data_enabled():
        raise HTTPException(503, 'Preparação compartilhada indisponível.')
    current()
    if request.query_params:
        raise HTTPException(422, 'Parâmetros de consulta não suportados.')
    try:
        yield
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível consultar ou salvar o preparo. Nenhuma conexão foi ativada.') from None


router = APIRouter(prefix='/api/v1/integrations/setup', tags=['integration preparation'], dependencies=[Depends(boundary)])


def username(value):
    if not isinstance(value, str):
        raise ValueError('Informe um nome de usuário, sem senha ou endereço.')
    result = value.strip().removeprefix('@').lower()
    if result and not re.fullmatch(r'[a-z0-9._]{1,30}', result):
        raise ValueError('Nome de usuário inválido.')
    return result


class InstagramSetup(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    username: str = Field(default='', max_length=31)
    account_type: Literal['unknown', 'business', 'creator'] = 'unknown'
    meta_app_status: Literal['unknown', 'exists', 'not_created'] = 'unknown'
    test_participants: list[str] = Field(default_factory=list, max_length=10)
    reply_mode: Literal['review'] = 'review'

    @field_validator('username')
    @classmethod
    def valid_username(cls, value):
        return username(value)

    @field_validator('test_participants')
    @classmethod
    def valid_participants(cls, values):
        items = [username(value) for value in values]
        if any(not item for item in items):
            raise ValueError('Participante sem nome de usuário.')
        return list(dict.fromkeys(items))

    def normalized(self):
        return self.model_dump()


class SetupWrite(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: Annotated[StrictInt, Field(ge=0, le=9007199254740990)]
    instagram: InstagramSetup


def envelope(workspace, revision, instagram):
    blockers = []
    if not instagram['username']:
        blockers.append('Informar a conta profissional de teste.')
    if instagram['account_type'] == 'unknown':
        blockers.append('Confirmar se a conta é Empresa ou Criador.')
    if instagram['meta_app_status'] != 'exists':
        blockers.append('Confirmar o aplicativo no Meta for Developers.')
    if not instagram['test_participants']:
        blockers.append('Definir participantes autorizados para o teste.')
    blockers.extend([
        'Autorizar a conta e conferir permissões no fluxo oficial da Meta.',
        'Homologar recebimento HTTPS, assinatura e resposta pelo conector real.',
        'Conferir contratos dos workflows e a base de produtos antes de responder.',
    ])
    return {'workspace_id': workspace, 'revision': revision, 'instagram': instagram,
            'connected': False, 'transport': 'none',
            'readiness': {'can_receive': False, 'can_send': False, 'can_publish': False,
                          'source': 'user_reported_preparation', 'blockers': blockers},
            'whatsapp': {'connected': False, 'status': 'awaiting_dedicated_number'},
            'providers': {'captions': 'local_template_without_ai', 'images': 'unavailable',
                          'sentiment': 'synthetic_heuristic', 'publishing': 'simulation_only'}}


@router.get('')
def read_setup():
    user = current()
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT revision,instagram FROM socialmei.integration_setup WHERE workspace_id=%s', (user['workspace_id'],))
        row = cur.fetchone()
    return envelope(user['workspace_id'], row['revision'] if row else 0,
                    row['instagram'] if row else InstagramSetup().normalized())


@router.put('')
def save_setup(payload: SetupWrite):
    user = current()
    if user['role'] not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente o responsável pode preparar conexões.')
    with connect() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', ('integration-setup:' + str(user['workspace_id']),))
        cur.execute('SELECT revision FROM socialmei.integration_setup WHERE workspace_id=%s FOR UPDATE', (user['workspace_id'],))
        old = cur.fetchone()
        if (old['revision'] if old else 0) != payload.expected_revision:
            raise HTTPException(409, 'O preparo foi alterado em outra sessão. Atualize para conferir antes de salvar.')
        value = payload.instagram.normalized()
        cur.execute('INSERT INTO socialmei.integration_setup(workspace_id,instagram,updated_by) VALUES(%s,%s,%s) ON CONFLICT(workspace_id) DO UPDATE SET instagram=EXCLUDED.instagram,revision=integration_setup.revision+1,updated_by=EXCLUDED.updated_by,updated_at=now() RETURNING revision', (user['workspace_id'], Jsonb(value), user['id']))
        revision = cur.fetchone()['revision']
    return envelope(user['workspace_id'], revision, value)
