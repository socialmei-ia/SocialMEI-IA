"""Explicit, read-only inspection of the team deployment. Never sends or deploys."""
import argparse
import json
import os
import re
import subprocess
import sys

API = 'socialmei-team-team-api-1'
GATEWAY = 'socialmei-team-team-gateway-1'
N8N = 'socialmei-n8n'
WAHA = 'socialmei-waha'
WORKFLOWS = {'LHlqroY2xzvpYAmD', 'A0EcNxcRvfWnMwKI'}
MIGRATIONS = ('001_initial_socialmei_schema.sql', '002_shared_crm_foundation.sql', '003_client_contract.sql', '004_client_import.sql', '005_shared_catalog.sql', '006_shared_sales.sql', '007_shared_finance.sql', '008_workspace_transfer.sql', '009_shared_channel_foundation.sql', '010_account_authentication.sql', '011_crm_workspace_links.sql', '012_instagram_simulation.sql', '013_workspace_profile_sync.sql', '014_message_enrichment.sql', '015_content_preparation.sql', '016_opportunity_lifecycle.sql', '017_integration_setup.sql', '018_instagram_provider_lab.sql', '019_instagram_persistent_oauth.sql', '020_instagram_durable_webhook.sql', '021_instagram_direct_outbox.sql', '022_opportunity_planning.sql', '023_waha_durable_ingress.sql', '024_account_recovery.sql', '025_session_management.sql', '026_recovery_delivery_queue.sql', '027_instagram_image_publications.sql', '028_instagram_temporary_media.sql', '029_workspace_pdf_knowledge.sql', '030_whatsapp_catalog_access.sql', '031_report_viewer_role.sql', '032_whatsapp_bot_conversations.sql')

API_DATABASE_INSPECTION = r'''
import json
from database import connect
result = {'status':'not_verified'}
try:
    with connect() as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SET LOCAL statement_timeout='5s'")
        result = {'status':'verified_read_only'}
        result['migrations'] = [row[0] for row in conn.execute(
            'SELECT version FROM socialmei.schema_migrations ORDER BY version LIMIT 1000')]
        exists = lambda table: conn.execute('SELECT to_regclass(%s)', ('socialmei.'+table,)).fetchone()[0] is not None
        result['instagram_table_present'] = exists('ig_meta_connections')
        if result['instagram_table_present']:
            result['instagram_active_valid'] = conn.execute(
                "SELECT count(*) FROM socialmei.ig_meta_connections WHERE status='connected' AND expires_at>NOW() AND encrypted_token IS NOT NULL"
            ).fetchone()[0]
        result['waha_table_present'] = exists('crm_canais')
        if result['waha_table_present']:
            columns = [row[0] for row in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema='socialmei' AND table_name='crm_canais'")]
            total, active = conn.execute("SELECT count(*),count(*) FILTER(WHERE ativo) FROM socialmei.crm_canais WHERE provedor='waha'").fetchone()
            channels = {'total':total,'active':active}
            if 'ingress_provisioned' in columns:
                channels['provisioned'] = conn.execute("SELECT count(*) FROM socialmei.crm_canais WHERE provedor='waha' AND ingress_provisioned").fetchone()[0]
            result['waha_channels'] = channels
except Exception:
    result = {'status':'not_verified'}
print(json.dumps(result))
'''

N8N_INSPECTION_SQL = r'''
SELECT jsonb_build_object(
  'workflow',w.id,
  'active',to_jsonb(w)->'active',
  'saved_equals_active',CASE WHEN to_jsonb(w)->>'versionId' IS NOT NULL AND to_jsonb(w)->>'activeVersionId' IS NOT NULL
       THEN to_jsonb(w)->>'versionId'=to_jsonb(w)->>'activeVersionId' ELSE NULL END,
  'webhook_count',(SELECT count(*) FROM jsonb_array_elements(w.nodes::jsonb) n
       WHERE n->>'type'='n8n-nodes-base.webhook'),
  'possible_sender_count',(SELECT count(*) FROM jsonb_array_elements(w.nodes::jsonb) n
       WHERE n->>'type'='n8n-nodes-base.httpRequest' AND
       (n->'parameters'->>'url' LIKE '%/messages%' OR n->'parameters'->>'url' LIKE '%/sendText%'
        OR n->'parameters'->>'url' LIKE '%/sendList%' OR n->'parameters'->>'url' LIKE '%/sendButtons%'
        OR n->'parameters'->>'url' LIKE '%/media_publish%'))
) FROM public.workflow_entity w WHERE w.id IN ('LHlqroY2xzvpYAmD','A0EcNxcRvfWnMwKI');
'''


def command_allowed(args, body=None):
    if not isinstance(args, list):
        return False
    if len(args) == 3 and args[:2] == ['docker', 'inspect'] and args[2] in {API, GATEWAY, N8N, WAHA}:
        return body is None
    if args == ['docker', 'exec', '-i', API, 'python', '-']:
        return body == API_DATABASE_INSPECTION
    prefix = ['docker', 'exec', '-i', '--env', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5s',
              'socialmei-postgres', 'sh', '-c',
              'exec psql -X -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -At', 'integration-read-only']
    return (len(args) == len(prefix)+1 and args[:-1] == prefix
            and isinstance(args[-1], str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args[-1]) is not None
            and body == N8N_INSPECTION_SQL)


def run(args, **kwargs):
    if set(kwargs) - {'input'} or not command_allowed(args, kwargs.get('input')):
        raise ValueError('Somente consultas Docker explícitas são permitidas.')
    env = dict(os.environ)
    for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
        env.pop(key, None)
    try:
        result = subprocess.run(['docker', '--host=unix:///var/run/docker.sock', *args[1:]], capture_output=True, text=True, timeout=30, env=env, **kwargs)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Consulta não concluída; detalhes privados não exibidos.') from None
    if result.returncode or len(result.stdout) > 4 * 1024 * 1024:
        raise RuntimeError('Consulta não concluída; detalhes privados não exibidos.')
    return result.stdout


def environment(row):
    config = row.get('Config') if isinstance(row, dict) else None
    entries = config.get('Env', []) if isinstance(config, dict) else []
    if not isinstance(entries, list):
        return {}
    return dict(value.split('=', 1) for value in entries if isinstance(value, str) and '=' in value)


def flag(value, contract='strict'):
    if not isinstance(value, str):
        return 'invalid'
    if contract in {'auth', 'normalized'}:
        value = value.strip().lower()
    enabled = {'true', '1', 'yes', 'on'} if contract == 'auth' else {'true'}
    disabled = {'false', '0', 'no', 'off', ''} if contract == 'auth' else {'false', ''}
    if value in enabled:
        return True
    if value in disabled:
        return False
    return 'invalid'


def count(value):
    return value if type(value) is int and 0 <= value <= 2**63-1 else None


def container_summary(row):
    env = environment(row)
    config, state = row.get('Config', {}), row.get('State', {})
    tag = config.get('Image', '')
    image = tag if isinstance(tag, str) and re.fullmatch(
        r'(?:socialmei-v22/(?:team-api|team-gateway):[0-9a-f]{40}|socialmei-team-(?:api|gateway):igpilot-[0-9a-f]{8})', tag) else None
    image_id = row.get('Image', '')
    if not isinstance(image_id, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image_id):
        image_id = None
    health = state.get('Health', {}).get('Status')
    health = health if health in {'healthy', 'unhealthy', 'starting'} else 'not_verified'
    running = state.get('Status') == 'running'
    modes = {
        'instagram_runtime': ('SOCIALMEI_INSTAGRAM_RUNTIME_MODE', {'disabled', 'connect', 'oauth'}),
        'instagram_oauth': ('SOCIALMEI_INSTAGRAM_OAUTH_MODE', {'disabled', 'connect', 'isolated'}),
        'waha_ingress': ('SOCIALMEI_WAHA_INGRESS_MODE', {'disabled', 'isolated'}),
    }
    result = {
        'running': running, 'health': health, 'image': image, 'image_id': image_id,
        'egress_network_attached': 'socialmei_team_egress' in row.get('NetworkSettings', {}).get('Networks', {}),
        'registry_file_configured': bool(env.get('SOCIALMEI_WAHA_REGISTRY_FILE')),
        'engine': env.get('WHATSAPP_DEFAULT_ENGINE') if env.get('WHATSAPP_DEFAULT_ENGINE') in {'WEBJS', 'GOWS', 'NOWEB', 'WPP'} else 'not_verified',
        'flags': {name:flag(env.get(key, 'false'), contract) for name,(key,contract) in {
            'authentication':('SOCIALMEI_AUTH_ENABLED', 'auth'),
            'instagram_ingress':('SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED', 'strict'),
            'instagram_send':('SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED', 'strict'),
            'instagram_publish':('SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED', 'strict'),
            'instagram_token_refresh':('SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED', 'normalized'),
            'whatsapp_bot':('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'normalized'),
            'whatsapp_catalog':('SOCIALMEI_WA_CATALOG_ENABLED', 'normalized'),
        }.items()},
    }
    result['modes'] = {name:env.get(key, 'disabled') if env.get(key, 'disabled') in allowed else 'invalid'
                       for name,(key,allowed) in modes.items()}
    return result


def database_summary(value):
    if not isinstance(value, dict) or value.get('status') != 'verified_read_only':
        return {'status':'not_verified'}
    versions = value.get('migrations', [])
    if not isinstance(versions, list):
        versions = []
    known = sorted({name for name in versions if isinstance(name, str) and name in MIGRATIONS})
    channels = value.get('waha_channels') if isinstance(value.get('waha_channels'), dict) else {}
    return {
        'status':'verified_read_only', 'migrations':known,
        'unrecognized_migrations': len(known) != len(versions),
        'instagram_table_present': value.get('instagram_table_present') is True,
        'instagram_active_valid': count(value.get('instagram_active_valid')),
        'waha_table_present': value.get('waha_table_present') is True,
        'waha_channels': {key:count(channels.get(key)) for key in ('total', 'active', 'provisioned')},
    }


def n8n_summary(raw):
    rows = []
    for line in raw.splitlines():
        value = json.loads(line)
        if not isinstance(value, dict) or value.get('workflow') not in WORKFLOWS:
            continue
        rows.append({
            'workflow':value['workflow'],
            'active':value.get('active') if type(value.get('active')) is bool else None,
            'saved_equals_active':value.get('saved_equals_active') if type(value.get('saved_equals_active')) is bool else None,
            'webhook_count':count(value.get('webhook_count')),
            'possible_sender_count':count(value.get('possible_sender_count')),
            'published_contract':'not_verified',
        })
    return {'status':'queried_saved_metadata', 'workflows':rows}


def inspect(target):
    if target != 'team':
        raise ValueError('O alvo explícito team é obrigatório.')
    result = {'mode':'read_only', 'mutations_performed':False, 'containers':{}}
    snapshots = {}
    for role,name in {'api':API, 'gateway':GATEWAY, 'n8n':N8N, 'waha':WAHA}.items():
        try:
            rows = json.loads(run(['docker', 'inspect', name]))
            if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
                raise ValueError()
            snapshots[role] = rows[0]
            summary = container_summary(rows[0])
            if role != 'api':
                for key in ('flags', 'modes', 'registry_file_configured'):
                    summary.pop(key, None)
            if role != 'waha':
                summary.pop('engine', None)
            result['containers'][role] = summary
        except (RuntimeError, ValueError, TypeError, AttributeError):
            result['containers'][role] = {'status':'not_verified'}
    try:
        raw = run(['docker', 'exec', '-i', API, 'python', '-'], input=API_DATABASE_INSPECTION)
        result['database'] = database_summary(json.loads(raw))
    except (RuntimeError, ValueError, TypeError):
        result['database'] = {'status':'not_verified'}
    result['waha'] = {'session_status':'not_verified', 'pairing_performed':False, 'provider_http_queried':False}
    db = environment(snapshots.get('n8n', {})).get('DB_POSTGRESDB_DATABASE', '')
    try:
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', db):
            raise ValueError()
        raw = run(['docker', 'exec', '-i', '--env', 'PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=5s',
                   'socialmei-postgres', 'sh', '-c',
                   'exec psql -X -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -At', 'integration-read-only', db], input=N8N_INSPECTION_SQL)
        result['n8n'] = n8n_summary(raw)
    except (RuntimeError, ValueError, TypeError):
        result['n8n'] = {'status':'not_verified', 'published_contract':'not_verified'}
    result['limitations'] = [
        'Metadados e contagens não comprovam entrega, publicação, conexão do telefone ou isolamento ponta a ponta.',
        'Registry configurado não comprova arquivo válido/montado ou ingresso ativo.',
        'Contagens de nós são da versão salva; o contrato da versão publicada precisa de revisão própria.',
        'Nenhum endpoint externo, sessão WAHA, webhook ou remetente foi ativado ou executado.',
    ]
    return result


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(file=sys.stderr)
        self.exit(2, 'Informe somente --target team. Argumentos inválidos foram omitidos.\n')


def main(argv=None):
    parser = PrivateArgumentParser(prog='integration-readiness-inspect.py', description=__doc__)
    parser.add_argument('--target', required=True, choices=('team',))
    args = parser.parse_args(argv)
    print(json.dumps(inspect(args.target), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
