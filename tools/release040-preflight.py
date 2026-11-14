#!/usr/bin/env python3
"""Read-only release040 artifact gate. Never deploys, migrates or approves production."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release040_profile', ROOT / 'tools/team-release-profile.py')
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)
WORKERS = ('team-recovery-worker', 'team-identity-worker',
           'team-instagram-menu-primary', 'team-instagram-menu-secondary')
DISABLED = {
    'SOCIALMEI_IDENTITY_MODE': 'disabled', 'SOCIALMEI_RECOVERY_MODE': 'disabled',
    'SOCIALMEI_INSTAGRAM_RUNTIME_MODE': 'disabled', 'SOCIALMEI_WAHA_INGRESS_MODE': 'disabled',
    'SOCIALMEI_QUEUE_WAKEUP_MODE': 'poll',
}
OFF = ('SOCIALMEI_PUBLIC_BOOKING_ENABLED', 'SOCIALMEI_WHATSAPP_BOT_ENABLED',
       'SOCIALMEI_WAHA_MANAGEMENT_ENABLED', 'SOCIALMEI_WAHA_MANAGEMENT_PROBE_ENABLED',
       'SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED', 'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED',
       'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED', 'SOCIALMEI_INSTAGRAM_TOKEN_REFRESH_ENABLED',
       'SOCIALMEI_INSTAGRAM_AUTO_MENU_ENABLED', 'SOCIALMEI_PROVIDER_SENTIMENT_ENABLED')
GATES = ['current_source_export_and_database_identity', 'external_restorable_backup',
         'current_capacity_and_private_overlay_reconciliation', 'explicit_schema040_approval',
         'explicit_publication_approval',
         'separate_authorization_for_channels_and_smtp']
NETWORKS = {
    'team-postgres': ({'database'}, {'database'}),
    'team-api': ({'database', 'api', 'automation'},
                 {'database', 'api', 'automation', 'public-booking-egress', 'egress'}),
    'team-gateway': ({'api', 'web'}, {'api', 'web'}),
    'team-recovery-worker': ({'database', 'recovery-egress'}, {'database', 'recovery-egress'}),
    'team-identity-worker': ({'database', 'identity-egress'}, {'database', 'identity-egress'}),
    'team-instagram-menu-primary': ({'database', 'instagram-menu-egress'}, {'database', 'instagram-menu-egress'}),
    'team-instagram-menu-secondary': ({'database', 'instagram-menu-egress'}, {'database', 'instagram-menu-egress'}),
}
COMMANDS = {
    'team-api': ['uvicorn', 'app:app', '--host', '0.0.0.0', '--port', '8000'],
    'team-recovery-worker': ['python', 'recovery_worker.py', '--run', '--watch', '--limit', '10', '--interval', '15'],
    'team-identity-worker': ['python', 'identity_worker.py', '--run', '--watch', '--limit', '10'],
    'team-instagram-menu-primary': ['python', '/app/instagram-auto-menu-worker.py'],
    'team-instagram-menu-secondary': ['python', '/app/instagram-auto-menu-worker.py'],
}


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def database_identity(env):
    # Compared only in memory; never return this value in a receipt or exception.
    explicit = str(env.get('DATABASE_URL') or '').strip()
    if explicit:
        return ('dsn', explicit)
    fields = ('POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD')
    values = {key: str(env.get(key) or '').strip() for key in fields}
    values['POSTGRES_PORT'] = values['POSTGRES_PORT'] or '5432'
    values['POSTGRES_PASSWORD'] = env.get('POSTGRES_PASSWORD', '')
    require(all(values[key] for key in ('POSTGRES_HOST', 'POSTGRES_DB', 'POSTGRES_USER')),
            'database_configuration_incomplete')
    return tuple(values[key] for key in fields)


def validate(model, images, sha, receipt, rollback):
    require(re.fullmatch(r'[0-9a-f]{40}', sha) is not None, 'invalid_source_sha')
    folder = ROOT / 'database/migrations'
    profile.verify040(sorted(file.name for file in folder.glob('*.sql')),
                      lambda name: (folder / name).read_bytes())
    profile.rehearsal040(receipt, sha)
    services = model.get('services', {})
    api = services.get('team-api', {})
    require(api and services.get('team-gateway'), 'required_service_missing')
    require('team-migrate' not in api.get('depends_on', {}), 'implicit_migration_dependency')
    require(services.get('team-migrate', {}).get('profiles') == ['maintenance040'], 'migration_not_quarantined')
    for name in ('database', 'api', 'automation'):
        require(model.get('networks', {}).get(name, {}).get('internal') is True,
                'private_network_required')
    require(not services.get('team-postgres', {}).get('ports'), 'database_published_port')
    require(not api.get('ports'), 'api_published_port')
    require(api.get('healthcheck', {}).get('test'), 'api_healthcheck_missing')
    baseline = database_identity(api.get('environment', {}))
    origin = api.get('environment', {}).get('SOCIALMEI_AUTH_ORIGIN')
    require(isinstance(origin, str) and origin.startswith('https://'), 'https_origin_required')
    require(api.get('environment', {}).get('SOCIALMEI_AUTH_ENABLED') == 'true', 'authentication_required')
    for name, (required, allowed) in NETWORKS.items():
        service = services.get(name, {})
        attached = set(service.get('networks', {}))
        require(required <= attached <= allowed and not service.get('network_mode'), 'service_network_mismatch')
        if name != 'team-gateway':
            require(not service.get('ports'), 'private_service_published_port')
    ids = {}
    for role in ('api', 'gateway'):
        info = images[role]
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', info.get('Id', '')) is not None,
                'invalid_image_id')
        require(info.get('Config', {}).get('Labels', {}).get('org.opencontainers.image.revision') == sha,
                'image_source_mismatch')
        require(info.get('Architecture') == 'amd64', 'unreviewed_image_architecture')
        ids[role] = info['Id']
    require(images['api'].get('Config', {}).get('Labels', {}).get('org.socialmei.release.profile') == '040',
            'release040_image_required')
    require(receipt.get('api_image_id') == ids['api'], 'rehearsal_image_mismatch')
    require(rollback.get('profile') == '040' and rollback.get('mode') == 'executed'
            and rollback.get('candidate_source_sha') == sha
            and rollback.get('candidate_image_id') == ids['api']
            and rollback.get('fallback_source_sha') == 'b2b839bae94f4eef18b670cf5a1ada68988dffe3'
            and rollback.get('fallback_api_image_id') == 'sha256:0de7e2eb7a959a21fd5a767213c69eec8f947c28092ad9bf1a736bb36e3331c7'
            and rollback.get('source_migrations') == profile.MIGRATIONS040
            and rollback.get('rehearsal_tool_sha256') == hashlib.sha256(
                (ROOT / 'tools/schema040-rollback-rehearsal.py').read_bytes()).hexdigest(), 'rollback_proof_mismatch')
    require(all(rollback.get(key) is True for key in (
        'pending_email_guard_verified', 'existing_sessions_preserved',
        'users_credentials_business_data_preserved', 'durable_mail_queue_preserved',
        'business_isolation_verified', 'fallback_restart_verified',
        'schema040_ledger_preserved', 'isolated_cleanup_verified',
        'distinct_candidate_image_verified')), 'rollback_proof_incomplete')
    require(all(rollback.get(key) is False for key in (
        'schema_downgraded', 'production_runtime_changed', 'production_database_changed',
        'production_data_used', 'provider_messages_sent',
        'real_smtp_or_provider_transport_executed')), 'rollback_environment_invalid')
    for name in ('team-api', 'team-gateway', *WORKERS):
        service = services.get(name, {})
        require(service and not service.get('build'), 'immutable_service_image_required')
        role = 'gateway' if name == 'team-gateway' else 'api'
        require(service.get('image') == ids[role], 'compose_image_mismatch')
        require(service.get('entrypoint') is None, 'unexpected_entrypoint')
        command = service.get('command')
        require(command is None and name in ('team-api', 'team-gateway') or
                name in COMMANDS and command == COMMANDS[name], 'unexpected_command')
        for volume in service.get('volumes', []):
            target = str(volume.get('target', '')).rstrip('/')
            protected = any(target == path or target.startswith(path + '/') or
                            path.startswith(target + '/') for path in ('/app', '/srv/frontend', '/etc/caddy'))
            exception = name == 'team-gateway' and target in ('/srv/frontend/config.js', '/etc/caddy/private')
            require(not protected or exception and volume.get('read_only') is True, 'mutable_application_mount')
        if name in WORKERS:
            require(service.get('profiles') and service.get('restart') == 'unless-stopped',
                    'optional_worker_not_guarded')
            require(database_identity(service.get('environment', {})) == baseline, 'worker_database_mismatch')
            require(service.get('environment', {}).get('SOCIALMEI_AUTH_ORIGIN') == origin,
                    'worker_origin_mismatch')
        if role == 'api':
            env = service.get('environment', {})
            require(env.get('SOCIALMEI_AUTH_ENABLED') == 'true', 'authentication_required')
            require(all(env.get(key, value) == value for key, value in DISABLED.items()),
                    'optional_mode_enabled')
            require(all(env.get(key, 'false') == 'false' for key in OFF), 'optional_sending_enabled')
    return {'profile': '040', 'source_sha': sha, 'images': ids,
            'rollback_rehearsal_verified': True,
            'artifact_checks_passed': True, 'production_ready': False,
            'production_changed': False, 'required_external_gates': GATES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compose-json', type=Path, required=True,
                        help='Private docker compose config --format json; never commit this file')
    parser.add_argument('--rehearsal', type=Path, required=True)
    parser.add_argument('--rollback-rehearsal', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--api-image', required=True)
    parser.add_argument('--gateway-image', required=True)
    args = parser.parse_args()
    try:
        # No arbitrary Docker subcommands, remote daemon or image pulls.
        import os
        require(not os.environ.get('DOCKER_HOST') or os.environ['DOCKER_HOST'].startswith(('npipe://', 'unix://')),
                'remote_docker_forbidden')
        context = subprocess.run([args.docker, 'context', 'inspect'], capture_output=True,
                                 text=True, timeout=20, check=True)
        endpoint = json.loads(context.stdout)[0]['Endpoints']['docker']['Host']
        require(endpoint.startswith(('npipe://', 'unix://')), 'remote_docker_forbidden')
        images = {}
        for role in ('api', 'gateway'):
            image_id = getattr(args, role + '_image')
            require(re.fullmatch(r'sha256:[0-9a-f]{64}', image_id) is not None, 'invalid_image_id')
            result = subprocess.run([args.docker, 'image', 'inspect', image_id],
                                    capture_output=True, text=True, timeout=20, check=True)
            images[role] = json.loads(result.stdout)[0]
        result = validate(json.loads(args.compose_json.read_text(encoding='utf-8-sig')),
                          images, args.source_sha,
                          json.loads(args.rehearsal.read_text(encoding='utf-8-sig')),
                          json.loads(args.rollback_rehearsal.read_text(encoding='utf-8-sig')))
        print(json.dumps(result, indent=2))
    except Exception:
        # Input/model/process errors can include private environment values.
        print(json.dumps({'artifact_checks_passed': False, 'production_ready': False,
                          'error': 'release040_preflight_rejected'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
