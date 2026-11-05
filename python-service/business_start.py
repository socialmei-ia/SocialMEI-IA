"""Setup progress derived from persisted records, never from browser checkboxes."""
import psycopg
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from account_auth import current, require_enabled
from database import connect
from workspace_profile import BusinessProfile

router = APIRouter(prefix='/api/v1/onboarding', tags=['business setup'])


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
            'description': 'Etapas baseadas nos registros salvos deste negócio. Serviços exigem duração; produtos e recursos devem estar ativos. Agendamentos cadastrados incluem cancelados e não comprovam atendimento. Vendas válidas não incluem cancelamentos ou exclusões.'}
