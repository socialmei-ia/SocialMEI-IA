"""Authenticated commercial lifecycle, independent from sales and payments."""
import hashlib
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi import APIRouter, HTTPException, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from account_auth import current, require_enabled
from database import connect
from shared_data import require_shared_data

router = APIRouter(prefix='/api/v1/opportunities', tags=['opportunities'])
Interest = Literal['unknown', 'cold', 'warm', 'hot']
MAX_ID = 9007199254740991
COLUMNS = 'o.workspace_id,o.id,o.client_id,c.nome AS client_name,o.title,o.interest_level,o.outcome,o.outcome_reason,o.outcome_note,o.sale_id,s.status AS sale_status,(o.sale_id IS NOT NULL AND (s.id IS NULL OR s.excluida OR s.status=\'Cancelado\')) AS sale_unavailable,o.revision,o.closed_at,o.updated_at,o.created_at'
SOURCE = 'socialmei.crm_opportunities o JOIN socialmei.crm_clientes c ON c.workspace_id=o.workspace_id AND c.id=o.client_id LEFT JOIN socialmei.crm_vendas s ON s.workspace_id=o.workspace_id AND s.id=o.sale_id'


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Operation(Strict):
    operation_id: UUID


class Create(Operation):
    client_id: StrictInt = Field(ge=1, le=MAX_ID)
    title: str = Field(min_length=1, max_length=160)
    interest_level: Interest = 'unknown'


class Revision(Operation):
    expected_revision: StrictInt = Field(ge=1, le=MAX_ID)


class Edit(Revision):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    interest_level: Interest | None = None

    @model_validator(mode='after')
    def changes(self):
        if not self.model_fields_set.intersection({'title', 'interest_level'}) or any(getattr(self, key) is None for key in self.model_fields_set.intersection({'title', 'interest_level'})):
            raise ValueError('Informe uma alteração válida.')
        return self


class Close(Revision):
    outcome: Literal['won', 'lost']
    reason: Literal['sale_completed', 'gave_up', 'other_supplier', 'price', 'timing', 'other']
    note: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def compatible_reason(self):
        if (self.outcome == 'won') != (self.reason == 'sale_completed'):
            raise ValueError('Motivo incompatível com o resultado.')
        return self


class Reopen(Revision):
    reason: str = Field(min_length=1, max_length=300)


class SaleLink(Revision):
    sale_id: StrictInt = Field(ge=1, le=MAX_ID)


def guard(write=False):
    require_enabled()
    require_shared_data()
    user = current()
    if write and user['role'] not in {'owner', 'admin', 'member'}:
        raise HTTPException(403, 'Este acesso permite somente leitura.')
    return user


def transition(outcome, action):
    if (action in {'edit', 'close'} and outcome != 'open') or (action == 'reopen' and outcome == 'open'):
        raise HTTPException(409, 'O resultado mudou. Atualize a oportunidade antes de continuar.')


@contextmanager
def transaction():
    try:
        with connect() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                yield cursor
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, 'Esta venda já está vinculada a outra oportunidade.') from None
    except psycopg.Error:
        raise HTTPException(503, 'Oportunidades temporariamente indisponíveis. Atualize antes de tentar novamente.') from None


def record(cur, workspace, oid):
    cur.execute(f'SELECT {COLUMNS} FROM {SOURCE} WHERE o.workspace_id=%s AND o.id=%s', (workspace, oid))
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, 'Oportunidade não encontrada.')
    return jsonable_encoder(row)


def mutate(action, payload, oid=None):
    user = guard(True)
    workspace = user['workspace_id']
    fingerprint = hashlib.sha256(json.dumps({'action': action, 'id': str(oid), 'payload': payload.model_dump(mode='json')}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with transaction() as cur:
        # One workspace lock serializes operation replay and sale linking together.
        cur.execute('SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE', (workspace,))
        if not cur.fetchone():
            raise HTTPException(403, 'Negócio indisponível.')
        cur.execute('SELECT fingerprint,response FROM socialmei.crm_opportunity_operations WHERE workspace_id=%s AND operation_id=%s', (workspace, payload.operation_id))
        previous_operation = cur.fetchone()
        if previous_operation:
            if previous_operation['fingerprint'] != fingerprint:
                raise HTTPException(409, 'Identidade de operação já usada com outros dados.')
            return record(cur, workspace, previous_operation['response']['id'])
        before = None
        if action == 'create':
            cur.execute('SELECT id FROM socialmei.crm_clientes WHERE workspace_id=%s AND id=%s FOR KEY SHARE', (workspace, payload.client_id))
            if not cur.fetchone():
                raise HTTPException(404, 'Cliente não encontrado neste negócio.')
            oid = uuid4()
            cur.execute('INSERT INTO socialmei.crm_opportunities(workspace_id,id,client_id,title,interest_level,created_by) VALUES (%s,%s,%s,%s,%s,%s)', (workspace, oid, payload.client_id, payload.title, payload.interest_level, user['id']))
        else:
            before = record(cur, workspace, oid)
            if before['revision'] != payload.expected_revision:
                raise HTTPException(409, 'A oportunidade mudou. Atualize antes de salvar.')
            transition(before['outcome'], action)
            fields = {}
            if action == 'edit':
                fields = payload.model_dump(include={'title', 'interest_level'}, exclude_unset=True)
            elif action == 'close':
                fields = {'outcome': payload.outcome, 'outcome_reason': payload.reason, 'outcome_note': payload.note, 'closed_at': datetime.now(timezone.utc)}
            elif action == 'reopen':
                fields = {'outcome': 'open', 'outcome_reason': '', 'outcome_note': '', 'closed_at': None}
            elif action == 'sale':
                cur.execute('SELECT cliente_id,status,excluida FROM socialmei.crm_vendas WHERE workspace_id=%s AND id=%s FOR SHARE', (workspace, payload.sale_id))
                sale = cur.fetchone()
                if not sale or sale['cliente_id'] != before['client_id'] or sale['excluida'] or sale['status'] not in {'Pendente', 'Pago'}:
                    raise HTTPException(409, 'Escolha uma venda ativa do mesmo cliente e negócio.')
                fields = {'sale_id': payload.sale_id}
            # Keys come exclusively from the fixed mappings above, never from the request.
            assignments = ','.join(key + '=%s' for key in fields)
            cur.execute(f'UPDATE socialmei.crm_opportunities SET {assignments},revision=revision+1,updated_at=now() WHERE workspace_id=%s AND id=%s', (*fields.values(), workspace, oid))
        result = record(cur, workspace, oid)
        cur.execute('INSERT INTO socialmei.crm_opportunity_events(workspace_id,opportunity_id,actor_id,action,reason,previous,current) VALUES (%s,%s,%s,%s,%s,%s,%s)', (workspace, oid, user['id'], action, getattr(payload, 'reason', ''), Jsonb(before), Jsonb(result)))
        cur.execute('INSERT INTO socialmei.crm_opportunity_operations(workspace_id,operation_id,fingerprint,response) VALUES (%s,%s,%s,%s)', (workspace, payload.operation_id, fingerprint, Jsonb(result)))
        return result


@router.get('')
def list_opportunities(response: Response):
    user = guard()
    response.headers['Cache-Control'] = 'no-store'
    with transaction() as cur:
        cur.execute(f'SELECT {COLUMNS} FROM {SOURCE} WHERE o.workspace_id=%s ORDER BY o.updated_at DESC,o.id LIMIT 100', (user['workspace_id'],))
        return {'workspace_id': user['workspace_id'], 'items': cur.fetchall()}


@router.post('', status_code=201)
def create_opportunity(payload: Create):
    return mutate('create', payload)


@router.patch('/{oid}')
def edit_opportunity(oid: UUID, payload: Edit):
    return mutate('edit', payload, oid)


@router.post('/{oid}/close')
def close_opportunity(oid: UUID, payload: Close):
    return mutate('close', payload, oid)


@router.post('/{oid}/reopen')
def reopen_opportunity(oid: UUID, payload: Reopen):
    return mutate('reopen', payload, oid)


@router.post('/{oid}/sale')
def link_sale(oid: UUID, payload: SaleLink):
    return mutate('sale', payload, oid)


@router.get('/{oid}/history')
def opportunity_history(oid: UUID, response: Response):
    user = guard()
    response.headers['Cache-Control'] = 'no-store'
    with transaction() as cur:
        record(cur, user['workspace_id'], oid)
        cur.execute('SELECT id,actor_id,action,reason,previous,current,created_at FROM socialmei.crm_opportunity_events WHERE workspace_id=%s AND opportunity_id=%s ORDER BY id DESC LIMIT 500', (user['workspace_id'], oid))
        return {'workspace_id': user['workspace_id'], 'items': cur.fetchall()}
