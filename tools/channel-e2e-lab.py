#!/usr/bin/env python3
"""Run PR212 channel contracts in disposable local Docker, never a live target.

Default is an offline plan. Execution requires the exact reviewed bundle and a
clean source checkout. Images must already be present; this tool never pulls.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile

SOURCE_SHA = '345a074310673640084c7634e3da75dd72491813'
BUNDLE_SHA256 = '0ff6d5364e54f003016c70c2408412006e981fe3bf30831f44eb5c4970e1767a'
ARTIFACT_ID = 13414736091
PG_IMAGE = 'postgres:16-alpine'
N8N_IMAGE = 'n8nio/n8n:2.40.5'
LABEL = 'socialmei.channel-e2e'
HERE = Path(__file__).resolve().parent


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def command(argv, timeout=120, stdin=None):
    try:
        result = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('lab_command_unavailable') from None
    if result.returncode:
        try:
            controlled = json.loads(result.stdout.strip().splitlines()[-1])
            if set(controlled) == {'code'} and re.fullmatch(r'[a-z0-9_]{1,100}', controlled['code']):
                raise RuntimeError(controlled['code'])
        except (ValueError, IndexError, TypeError):
            pass
        raise RuntimeError('lab_command_failed')
    return result.stdout


def docker(*args, timeout=120):
    # Do not inherit DOCKER_HOST, contexts or a remote daemon.
    require(Path('/var/run/docker.sock').is_socket(), 'local_docker_socket_required')
    return command(['docker', '--host=unix:///var/run/docker.sock', *map(str, args)], timeout)


def validate_source(source):
    require(source.is_dir() and not source.is_symlink(), 'clean_candidate_source_required')
    require(command(['git', '-C', str(source), 'rev-parse', 'HEAD']).strip() == SOURCE_SHA,
            'candidate_source_sha_mismatch')
    require(not command(['git', '-C', str(source), 'status', '--porcelain=v1', '--untracked-files=all']).strip(),
            'candidate_source_dirty')
    migrations = sorted((source / 'database/migrations').glob('*.sql'))
    require(len(migrations) == 38 and [int(p.name[:3]) for p in migrations] == list(range(1, 39)),
            'candidate_migrations_incomplete')


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024**2), b''):
            value.update(chunk)
    return value.hexdigest()


def verify_bundle(bundle):
    require(bundle.is_file() and not bundle.is_symlink(), 'candidate_bundle_required')
    require(digest(bundle) == BUNDLE_SHA256, 'candidate_external_digest_mismatch')
    spec = importlib.util.spec_from_file_location('channel_bundle_verifier', HERE / 'team-v33-import-images.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The reviewed verifier keeps strict filename/parent confinement. This lab's
    # explicit local bundle directory replaces only its production staging root.
    module.BACKUPS = bundle.resolve().parent
    return module.read_bundle038(bundle.resolve(), SOURCE_SHA)


def plan():
    return {'mode': 'plan', 'candidate_sha': SOURCE_SHA, 'artifact_id': ARTIFACT_ID,
            'bundle_sha256': BUNDLE_SHA256, 'postgres_image': PG_IMAGE, 'n8n_image': N8N_IMAGE,
            'docker_executed': False, 'production_changed': False, 'real_provider_messages_sent': False,
            'requires': ['clean_candidate_source', 'exact_candidate_bundle', 'preloaded_images', 'local_docker'],
            'limitations': ['isolated_fixture_only', 'external_tls_not_exercised',
                            'planner_trigger_fixture_replaces_subworkflow', 'oauth_and_sessions_seeded',
                            'no_live_homologation']}


class Lab:
    def __init__(self):
        self.identity = uuid.uuid4().hex
        self.prefix = 'channel-e2e-' + self.identity[:12]
        self.network = self.prefix + '-net'
        self.filter = LABEL + '=' + self.identity

    def cleanup(self):
        # Query labels even after partial startup. Never prune a daemon globally.
        failed = False
        for kind, listing, removing in (
            ('container', ['ps', '-aq'], ['rm', '-fv']),
            ('network', ['network', 'ls', '-q'], ['network', 'rm']),
        ):
            try:
                identifiers = docker(*listing, '--filter', 'label=' + self.filter).split()
                if identifiers:
                    docker(*removing, *identifiers)
                require(not docker(*listing, '--filter', 'label=' + self.filter).strip(),
                        'lab_cleanup_incomplete')
            except RuntimeError:
                failed = True
        require(not failed, 'lab_cleanup_failed')

    def container(self, role, image, args=(), env=None, mounts=(), detach=True, aliases=(), user=None, tmpfs=()):
        name = self.prefix + '-' + role
        argv = ['run', '--pull=never', '--name', name, '--label', self.filter,
                '--network', self.network, '--cap-drop=ALL', '--security-opt', 'no-new-privileges']
        if detach:
            argv += ['-d']
        if user is not None:
            argv += ['--user', user]
        for alias in aliases:
            argv += ['--network-alias', alias]
        for key, value in (env or {}).items():
            argv += ['-e', key + '=' + str(value)]
        for mount in mounts:
            argv += ['-v', mount]
        for mount in tmpfs:
            argv += ['--tmpfs', mount]
        docker(*argv, image, *args, timeout=300)
        return name


def workflows(source, folder, config):
    planner = json.loads((source / 'n8n-workflows/experimental/whatsapp-bot-planner.json').read_text())
    planner.update(id='channelLabWA', name='Isolated channel WA fixture', active=False)
    hook = planner['nodes'][0]
    hook.update(type='n8n-nodes-base.webhook', typeVersion=2, webhookId=str(uuid.uuid4()),
                parameters={'httpMethod': 'POST', 'path': 'channel-lab-wa', 'responseMode': 'onReceived', 'options': {}})
    gate = next(node for node in planner['nodes'] if node['name'] == 'Ativacao e entrada')
    gate['parameters']['jsCode'] = gate['parameters']['jsCode'].replace('const ENABLED = false;', 'const ENABLED = true;')
    # Webhook JSON is nested under body; leave all production planner code intact.
    unwrap = {'id': 'lab-unwrap', 'name': 'Lab webhook envelope', 'type': 'n8n-nodes-base.code', 'typeVersion': 2,
              'position': [100, 0], 'parameters': {'jsCode': 'return [{json:$json.body}];'}}
    planner['nodes'].append(unwrap)
    planner['connections'][hook['name']] = {'main': [[{'node': unwrap['name'], 'type': 'main', 'index': 0}]]}
    planner['connections'][unwrap['name']] = {'main': [[{'node': gate['name'], 'type': 'main', 'index': 0}]]}
    for node in planner['nodes']:
        if node['type'] == 'n8n-nodes-base.httpRequest':
            credential = 'labWaha' if node['name'] == 'Enviar uma vez WAHA' else 'labBot'
            node['credentials'] = {'httpHeaderAuth': {'id': credential, 'name': credential}}
    # Invoke the actual versioned preparation module. The legacy branch deliberately
    # points to a counted failing provider endpoint and must remain unreachable.
    generate = '''import {prepare,WORKFLOW} from MODULE;
import {writeFileSync} from 'node:fs';
const hook={id:'fixture-hook',name:'Meta webhook',type:'n8n-nodes-base.webhook',typeVersion:2,webhookId:'channel-lab-ig',parameters:{httpMethod:'POST',path:'channel-lab-ig',options:{}}};
const legacy={id:'fixture-legacy',name:'Legacy AI and sender canary',type:'n8n-nodes-base.httpRequest',typeVersion:4.2,parameters:{method:'POST',url:'http://waha:3000/legacy-ai-sender'}};
const source={id:WORKFLOW,versionId:'fixture-version',name:'Isolated IG fixture',nodes:[hook,legacy],connections:{'Meta webhook':{main:[[{node:legacy.name,type:'main',index:0}]]}}};
const result=prepare(source,{sourceSha:'a'.repeat(64),publishedVersion:'fixture-version',apiOrigin:'https://candidate.example.test',credentialId:'labInstagram'});
const candidate={...result.candidate,id:'channelLabIG',active:false};
candidate.nodes.find(n=>n.name==='SocialMEI persistir antes da IA').parameters.url='http://team-api:8000/webhooks/instagram/n8n';
writeFileSync(OUTPUT,JSON.stringify(candidate));'''
    module = (source / 'tools/prepare-instagram-persistence.mjs').as_uri()
    generate = generate.replace('MODULE', json.dumps(module)).replace('OUTPUT', json.dumps(str(folder / 'instagram.json')))
    command(['node', '--input-type=module', '-e', generate])
    (folder / 'whatsapp.json').write_text(json.dumps(planner))
    credentials = [
        {'id': 'labBot', 'name': 'labBot', 'type': 'httpHeaderAuth', 'data': {'name': 'Authorization', 'value': 'Bearer ' + config['bot']}},
        {'id': 'labWaha', 'name': 'labWaha', 'type': 'httpHeaderAuth', 'data': {'name': 'X-Api-Key', 'value': config['waha']}},
        {'id': 'labInstagram', 'name': 'labInstagram', 'type': 'httpBearerAuth', 'data': {'token': config['bridge']}},
    ]
    (folder / 'credentials.json').write_text(json.dumps(credentials))
    for path in folder.glob('*.json'):
        path.chmod(0o600)


def execute(args):
    validate_source(args.source)
    source, bundle = args.source.resolve(), args.candidate_bundle
    image_receipt = verify_bundle(bundle)
    lab = Lab()
    report = {**plan(), 'mode': 'isolated-run', 'docker_executed': True, 'passed': False,
              'cleanup_complete': False, 'checks': [], 'api_image_id': image_receipt['images']['team-api']['image_id']}
    try:
        # No pull or provider access occurs inside this harness. CI preloads pinned
        # dependencies before the isolated network is created.
        for image in (PG_IMAGE, N8N_IMAGE):
            docker('image', 'inspect', image)
        docker('network', 'create', '--internal', '--label', lab.filter, lab.network)
        with tempfile.TemporaryDirectory(prefix='channel-e2e-') as temporary:
            folder = Path(temporary)
            folder.chmod(0o700)
            archive = folder / 'images.tar.gz'
            with zipfile.ZipFile(bundle) as zipped, zipped.open('images.tar.gz') as stream, archive.open('wb') as dest:
                shutil.copyfileobj(stream, dest)
            docker('load', '-i', archive, timeout=600)
            archive.unlink()
            image = image_receipt['images']['team-api']['tag']
            actual = json.loads(docker('image', 'inspect', image))[0]
            require(actual['Id'] == report['api_image_id'] and actual['Config']['Labels']['org.opencontainers.image.revision'] == SOURCE_SHA,
                    'loaded_candidate_identity_mismatch')
            config = {key: secrets.token_hex(32) for key in ('waha', 'bot', 'bridge', 'meta', 'session1', 'session2', 'postgres', 'encryption')}
            private_file = folder / 'private.json'
            private_file.write_text(json.dumps(config))
            private_file.chmod(0o600)
            env = {'DATABASE_URL': 'postgresql://lab:' + config['postgres'] + '@postgres:5432/channel_e2e_fixture',
                   'SOCIALMEI_AUTH_ENABLED': 'true', 'SOCIALMEI_SHARED_DATA_ENABLED': 'true',
                   'SOCIALMEI_AUTH_ORIGIN': 'https://lab.example.test',
                   'SOCIALMEI_WAHA_INGRESS_MODE': 'isolated', 'SOCIALMEI_WAHA_LAB_ENVIRONMENT': 'isolated',
                   'SOCIALMEI_WAHA_REGISTRY_FILE': '/lab/waha-registry.json', 'SOCIALMEI_WHATSAPP_BOT_ENABLED': 'true',
                   'SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED': 'true', 'SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE': 'header',
                   'SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY': config['bridge'], 'SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET': config['meta'],
                   'SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS': '{"987654321":1}'}
            user = str(os.getuid()) + ':' + str(os.getgid())
            mounts = [str(folder) + ':/lab', str(HERE / 'channel_e2e_seed.py') + ':/fixture.py:ro']
            report['stage'] = 'postgres_start'
            postgres = lab.container('postgres', PG_IMAGE, env={'POSTGRES_USER': 'lab', 'POSTGRES_PASSWORD': config['postgres'], 'POSTGRES_DB': 'channel_e2e_fixture'}, aliases=['postgres'], user='postgres',
                                     tmpfs=['/var/lib/postgresql/data:rw,noexec,nosuid,size=512m,uid=70,gid=70'])
            for _ in range(60):
                try:
                    docker('exec', postgres, 'pg_isready', '-U', 'lab', '-d', 'channel_e2e_fixture')
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError('postgres_readiness_failed')
            report['stage'] = 'database_migrate_seed'
            lab.container('seed', image, ['python', '/fixture.py', 'initialize'], env,
                          mounts + [str(source / 'database/migrations') + ':/migrations:ro'], detach=False, user=user)
            config = json.loads(private_file.read_text())
            env['SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS'] = json.dumps({'987654321': config['workspace1']})
            report['stage'] = 'prepare_ephemeral_workflows'
            workflows(source, folder, config)
            lab.container('waha', image, ['python', '/fixture.py', 'provider'], mounts=mounts, aliases=['waha'], user=user)
            api = lab.container('api', image, env=env, mounts=mounts, aliases=['team-api'], user=user)
            home = folder / 'n8n-home'
            home.mkdir(mode=0o700)
            n8n_env = {'N8N_USER_FOLDER': '/n8n', 'N8N_ENCRYPTION_KEY': config['encryption'],
                       'N8N_DIAGNOSTICS_ENABLED': 'false', 'N8N_VERSION_NOTIFICATIONS_ENABLED': 'false',
                       'N8N_TEMPLATES_ENABLED': 'false', 'N8N_PERSONALIZATION_ENABLED': 'false',
                       'N8N_SECURE_COOKIE': 'false', 'N8N_RUNNERS_ENABLED': 'true'}
            n8n_mounts = [str(home) + ':/n8n', str(folder) + ':/lab:ro']
            commands = [('credentials', ['import:credentials', '--input=/lab/credentials.json']),
                        ('wa', ['import:workflow', '--input=/lab/whatsapp.json']),
                        ('ig', ['import:workflow', '--input=/lab/instagram.json']),
                        ('publish-wa', ['publish:workflow', '--id=channelLabWA']),
                        ('publish-ig', ['publish:workflow', '--id=channelLabIG'])]
            for role, argv in commands:
                report['stage'] = 'n8n_' + role
                lab.container('n8n-' + role, N8N_IMAGE, argv, n8n_env, n8n_mounts, detach=False, user=user)
            report['stage'] = 'n8n_start'
            n8n = lab.container('n8n', N8N_IMAGE, env=n8n_env, mounts=n8n_mounts, aliases=['n8n'], user=user)
            require(docker('exec', n8n, 'n8n', '--version').strip() == '2.40.5', 'n8n_version_mismatch')
            # Readiness is checked through the real internal HTTP stack.
            readiness = "import urllib.request; urllib.request.urlopen('http://n8n:5678/healthz/readiness',timeout=2); urllib.request.urlopen('http://team-api:8000/health',timeout=2)"
            for _ in range(90):
                try:
                    docker('exec', api, 'python', '-c', readiness)
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError('api_n8n_readiness_failed')
            report['stage'] = 'exercise_channels'
            docker('exec', api, 'python', '/fixture.py', 'exercise', timeout=240)
            docker('stop', api)
            report['stage'] = 'exercise_api_outage'
            lab.container('outage', image, ['python', '/fixture.py', 'exercise', '--phase=outage'], env,
                          mounts, detach=False, user=user)
            report['checks'] = json.loads((folder / 'checks-main.json').read_text()) + json.loads((folder / 'checks-outage.json').read_text())
            report['passed'] = True
            report['stage'] = 'complete'
    except Exception as error:
        report['failure_code'] = (str(error) if isinstance(error, RuntimeError)
                                  and re.fullmatch(r'[a-z0-9_]{1,100}', str(error))
                                  else 'isolated_channel_e2e_failed')
    finally:
        try:
            lab.cleanup()
            report['cleanup_complete'] = True
        except Exception:
            report['passed'] = False
            report['failure_code'] = 'lab_cleanup_failed'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--candidate-bundle', type=Path)
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    if args.run:
        require(args.source is not None and args.candidate_bundle is not None and args.receipt is not None,
                'run_requires_source_bundle_receipt')
        try:
            report = execute(args)
        except Exception as error:
            report = {**plan(), 'mode': 'isolated-run', 'passed': False,
                      'failure_code': (str(error) if isinstance(error, RuntimeError)
                                       and re.fullmatch(r'[a-z0-9_]{1,100}', str(error))
                                       else 'isolated_channel_validation_failed')}
    else:
        report = plan()
    raw = json.dumps(report, sort_keys=True) + '\n'
    if args.receipt:
        args.receipt.write_text(raw)
    print(raw, end='')
    return 0 if report.get('passed', not args.run) else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        # Error codes are controlled, never command output or environment values.
        print(json.dumps({'passed': False, 'code': str(error), 'production_changed': False}))
        raise SystemExit(2)
