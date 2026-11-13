"""Setup progress and explicit initial catalog, persisted in one workspace transaction."""
import hashlib
import json
from typing import Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row
from pydantic import Field, field_validator, model_validator

from account_auth import Strict, current, require_enabled
from catalog_data import ProdutoCreate, insert_product
from channel_booking import BookingPolicy
from database import connect
from workspace_profile import BusinessProfile, database_text

router = APIRouter(prefix='/api/v1/onboarding', tags=['business setup'])


def owner():
    require_enabled()
    user = current()
    if user.get('role') not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente responsáveis podem configurar o negócio.')
    return user


class DraftOffer(Strict):
    nome: str = Field(min_length=1, max_length=160)
    tipo: Literal['Produto', 'Serviço']
    preco: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duracao_minutos: int | None = Field(default=None, ge=1, le=1440, strict=True)

    @field_validator('nome')
    @classmethod
    def clean_name(cls, value):
        value = ' '.join(database_text(value).split())
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError('Informe o nome da oferta.')
        return value


class CatalogDraft(Strict):
    expected_revision: int = Field(ge=0, strict=True)
    items: list[DraftOffer] = Field(max_length=30)


class CatalogConfirm(Strict):
    expected_revision: int = Field(ge=0, strict=True)
    operation_id: UUID
    confirmed: bool = Field(strict=True)
    items: list[ProdutoCreate] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def explicit_offers(self):
        if not self.confirmed:
            raise ValueError('Confira as ofertas antes de cadastrar.')
        names = set()
        for item in self.items:
            item.nome = DraftOffer.clean_name(item.nome)
            key = (item.tipo, item.nome.casefold())
            if key in names or item.status != 'Ativo':
                raise ValueError('Confirme cada oferta ativa uma única vez.')
            names.add(key)
            if item.tipo == 'Serviço' and item.duracao_minutos is None:
                raise ValueError('Informe a duração de cada serviço.')
        return self


def catalog_state(row):
    value = row['configuracao'].get('onboarding_catalog', {'revision': 0, 'items': [], 'receipt': None})
    if (not isinstance(value, dict) or type(value.get('revision')) is not int
            or value['revision'] < 0 or not isinstance(value.get('items'), list)
            or len(value['items']) > 30):
        raise HTTPException(503, 'A configuração inicial precisa de revisão.')
    try:
        for item in value['items']:
            DraftOffer.model_validate(item)
        receipt = value.get('receipt')
        if receipt is not None:
            UUID(receipt['operation_id'])
            if (not isinstance(receipt['fingerprint'], str) or len(receipt['fingerprint']) != 64
                    or not isinstance(receipt['items'], list) or not 1 <= len(receipt['items']) <= 30):
                raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(503, 'A configuração inicial precisa de revisão.') from None
    return value


def configure(conn):
    conn.row_factory = dict_row
    conn.execute("SET LOCAL statement_timeout='5s'")
    conn.execute("SET LOCAL lock_timeout='3s'")


def workspace(conn, user, lock=False):
    row = conn.execute('SELECT id,configuracao FROM socialmei.workspaces WHERE id=%s' +
                       (' FOR UPDATE' if lock else ''), (user['workspace_id'],)).fetchone()
    if not row:
        raise HTTPException(403, 'Negócio indisponível.')
    return row


def save_catalog(conn, user, value):
    conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{onboarding_catalog}',%s::jsonb),atualizado_em=NOW() WHERE id=%s",
                 (json.dumps(value), user['workspace_id']))


@router.get('/catalog')
def initial_catalog():
    user = owner()
    try:
        with connect() as conn:
            configure(conn)
            row = workspace(conn, user)
            state = catalog_state(row)
            profile = conn.execute('SELECT profile FROM socialmei.workspace_profiles WHERE workspace_id=%s', (user['workspace_id'],)).fetchone()
            suggestions = []
            if profile:
                try:
                    suggestions = BusinessProfile.model_validate(profile['profile']).services
                except ValueError:
                    pass
            return {'workspace_id': user['workspace_id'], **state, 'suggestions': suggestions}
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível consultar a configuração inicial.') from None


@router.put('/catalog')
def draft_catalog(payload: CatalogDraft):
    user = owner()
    try:
        with connect() as conn:
            configure(conn)
            previous = catalog_state(workspace(conn, user, True))
            if previous.get('receipt') or previous['revision'] != payload.expected_revision:
                raise HTTPException(409, 'A configuração mudou. Recarregue antes de continuar.')
            result = {'revision': previous['revision'] + 1, 'items': payload.model_dump(mode='json')['items'], 'receipt': None}
            save_catalog(conn, user, result)
        return {'workspace_id': user['workspace_id'], **result}
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível salvar a configuração inicial.') from None


@router.post('/catalog')
def confirm_catalog(payload: CatalogConfirm):
    user = owner()
    value = payload.model_dump(mode='json', exclude={'operation_id', 'expected_revision'})
    signature = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
    try:
        with connect() as conn:
            configure(conn)
            previous = catalog_state(workspace(conn, user, True))
            receipt = previous.get('receipt')
            if receipt:
                if receipt['operation_id'] != str(payload.operation_id) or receipt['fingerprint'] != signature:
                    raise HTTPException(409, 'As ofertas iniciais já foram cadastradas. Use o catálogo para editar ou adicionar itens.')
                return {'workspace_id': user['workspace_id'], 'revision': previous['revision'], 'items': receipt['items'], 'registered': True}
            if previous['revision'] != payload.expected_revision:
                raise HTTPException(409, 'A configuração mudou. Recarregue antes de continuar.')
            saved = []
            with conn.cursor(row_factory=dict_row) as cur:
                for item in payload.items:
                    if cur.execute('SELECT id FROM socialmei.crm_produtos WHERE workspace_id=%s AND tipo=%s AND LOWER(BTRIM(nome))=LOWER(BTRIM(%s)) LIMIT 1',
                                   (user['workspace_id'], item.tipo, item.nome)).fetchone():
                        raise HTTPException(409, 'Uma oferta já existe no catálogo. Confira os itens antes de cadastrar novamente.')
                    row = insert_product(cur, user['workspace_id'], item)
                    saved.append({'id': row['id'], 'nome': row['nome'], 'tipo': row['tipo'],
                                  'preco': str(row['preco']), 'duracao_minutos': row['duracao_minutos']})
            result = {'revision': previous['revision'] + 1, 'items': [],
                      'receipt': {'operation_id': str(payload.operation_id), 'fingerprint': signature, 'items': saved}}
            save_catalog(conn, user, result)
            conn.execute('INSERT INTO socialmei.auth_auditoria(user_id,acao) VALUES(%s,%s)', (user['id'], f"setup:{user['workspace_id']}:catalogo"))
        return {'workspace_id': user['workspace_id'], 'revision': result['revision'], 'items': saved, 'registered': True}
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível cadastrar as ofertas. Confira a configuração e tente novamente.') from None


@router.get('/status')
def status():
    require_enabled()
    user = current()
    if user.get('role') not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente responsáveis podem consultar a configuração inicial.')
    workspace = user['workspace_id']
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute("SET LOCAL statement_timeout='3s'")
            counts = conn.execute(
                'SELECT '
                '(SELECT count(*) FROM socialmei.crm_clientes WHERE workspace_id=%s) AS customers,'
                "(SELECT count(*) FROM socialmei.crm_produtos WHERE workspace_id=%s AND tipo='Produto' AND status='Ativo') AS products,"
                "(SELECT count(*) FROM socialmei.crm_produtos WHERE workspace_id=%s AND tipo='Serviço' AND status='Ativo' AND duracao_minutos IS NOT NULL) AS services,"
                '(SELECT count(*) FROM socialmei.agenda_resources WHERE workspace_id=%s AND ativo) AS resources,'
                '(SELECT count(*) FROM socialmei.agenda_appointments WHERE workspace_id=%s) AS appointments_created,'
                "(SELECT count(*) FROM socialmei.crm_vendas WHERE workspace_id=%s AND NOT excluida AND status IN ('Pago','Pendente')) AS valid_sales",
                (workspace,) * 6,
            ).fetchone()
            row = conn.execute('SELECT profile FROM socialmei.workspace_profiles WHERE workspace_id=%s', (workspace,)).fetchone()
            settings = conn.execute('SELECT configuracao FROM socialmei.workspaces WHERE id=%s', (workspace,)).fetchone()
            config = catalog_state(settings)
            try:
                stored = settings['configuracao'].get('channel_booking')
                if stored is not None and (type(stored['revision']) is not int or stored['revision'] < 1):
                    raise ValueError()
                policy = BookingPolicy.model_validate(stored['policy'] if stored is not None else {}).model_dump(mode='json')
            except (ValueError, KeyError, TypeError):
                raise HTTPException(503, 'Confira os horários de funcionamento deste negócio.') from None
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível consultar seus primeiros passos. Tente novamente.') from None
    profile = None
    problem = False
    if row:
        try:
            profile = BusinessProfile.model_validate(row['profile'])
        except ValueError:
            problem = True
    return {'workspace_id': workspace, 'profile_complete': profile is not None,
            'profile_problem': problem, 'offers': profile.offers if profile else [],
            'counts': dict(counts),
            'setup': {'catalog_confirmed': bool(config.get('receipt')), 'draft_revision': config['revision'],
                      'hours_configured': bool(policy['hours']), 'booking_enabled': policy['enabled']},
            'description': 'Etapas baseadas nos registros salvos deste negócio. Serviços exigem duração; produtos e recursos devem estar ativos. Agendamentos cadastrados incluem cancelados e não comprovam atendimento. Vendas válidas não incluem cancelamentos ou exclusões.'}
