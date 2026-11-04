"""Read only audit entries whose existing action explicitly binds a workspace."""
from datetime import date
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from account_auth import current, require_enabled
from database import connect
from shared_data import MAX_SAFE_ID
from workspace_reporting import report_period
import settings

router = APIRouter(prefix="/api/v1/audit", tags=["workspace audit"])
TEAM = {'concedida': 'Acesso à equipe concedido', 'papel': 'Papel na equipe alterado', 'revogada': 'Acesso à equipe revogado'}
EXPORTS = {'clientes': 'CSV de clientes gerado', 'produtos': 'CSV de produtos gerado', 'vendas': 'CSV de vendas gerado', 'financeiro': 'CSV financeiro gerado', 'agendamentos': 'CSV de agendamentos gerado'}


@router.get('/workspace')
def history(start: date | None = Query(None), end: date | None = Query(None),
            kind: Literal['all', 'team', 'exports'] = Query('all'),
            before: int | None = Query(None, ge=1, le=MAX_SAFE_ID),
            limit: int = Query(30, ge=1, le=50)):
    require_enabled()
    actor = current()
    if actor.get('role') not in {'owner', 'admin'}:
        raise HTTPException(403, 'Somente responsáveis podem consultar este histórico.')
    workspace = actor['workspace_id']
    if start is not None or end is not None:
        report_period(start, end, date.min)
    try:
        zone = settings.business_timezone().key
    except ValueError:
        raise HTTPException(503, 'Confira o fuso horário do negócio.') from None
    actions = {}
    if kind in {'all', 'team'}:
        actions.update({f'equipe:{workspace}:{key}': ('team', label) for key, label in TEAM.items()})
    if kind in {'all', 'exports'}:
        actions.update({f'export_{key}:{workspace}': ('exports', label) for key, label in EXPORTS.items()})
    try:
        with connect() as conn:
            conn.row_factory = dict_row
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            conn.execute("SET LOCAL statement_timeout='3s'")
            conn.execute("SELECT set_config('TimeZone',%s,true)", (zone,))
            today = conn.execute('SELECT CURRENT_DATE AS today').fetchone()['today']
            start, end, days = report_period(start, end, today)
            rows = conn.execute(
                'SELECT a.id,a.acao,a.criado_em,u.nome AS actor_name,t.nome AS target_name '
                'FROM socialmei.auth_auditoria a LEFT JOIN socialmei.users u ON u.id=a.user_id '
                'LEFT JOIN socialmei.users t ON t.id=a.alvo_user_id '
                'WHERE a.acao=ANY(%s::text[]) AND a.criado_em>=%s::date AND a.criado_em<(%s::date+1) '
                'AND (%s::bigint IS NULL OR a.id<%s) ORDER BY a.id DESC LIMIT %s',
                (list(actions), start, end, before, before, limit + 1),
            ).fetchall()
    except psycopg.Error:
        raise HTTPException(503, 'Não foi possível consultar o histórico. Tente novamente.') from None
    page = rows[:limit]
    return {'workspace_id': workspace, 'kind': kind,
            'period': {'start': start.isoformat(), 'end': end.isoformat(), 'days': days, 'timezone': zone},
            'items': [{'id': r['id'], 'at': r['criado_em'].isoformat(), 'kind': actions[r['acao']][0],
                       'action': actions[r['acao']][1], 'actor': r['actor_name'], 'target': r['target_name']}
                      for r in page],
            'next_before': page[-1]['id'] if len(rows) > limit else None,
            'description': 'Histórico disponível: alterações de acesso da equipe e geração de CSV vinculadas explicitamente a este negócio. Não inclui todas as alterações de CRM, agenda, estoque ou conta. CSV gerado não comprova download pelo navegador. Nomes exibidos são os atuais das contas.'}
