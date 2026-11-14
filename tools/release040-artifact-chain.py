#!/usr/bin/env python3
"""Bind exact040 images to fresh probes; inherit schema evidence without rerunning SQL."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = '8db028cb630e7047c13e6dcca104bbcd17bf0c77'
BASE_SOURCE = '9b34ac80ee5f2d9d6a12aa1b5c7e254bccb0c4d8'
B2 = 'b2b839bae94f4eef18b670cf5a1ada68988dffe3'
MANIFEST_SHA = '310c66cf0183238020f556f09bc0c0f59139987a93b0e5d8db20dd1233c4a195'
IMAGES = {
    'api': 'sha256:c07fa5bd22b143b24ddd505206a03b21d6aba7315e9b2d5d06a4dd831021d28e',
    'gateway': 'sha256:d121598bfbe80da7901cfedab5dc37c9a55b5ba0c1c2a5a405fc912ea269feb5',
    'fallback': 'sha256:c09248e80186c0e78e5cfa9500c4d3c729ad671871a646d1105e65ac917715ee',
}
CHECKS = ('pending_email_guard_verified', 'existing_sessions_preserved', 'business_isolation_verified',
          'durable_state_preserved', 'nonempty_mail_queue_preserved', 'fallback_new_process_verified',
          'schema040_ledger_preserved', 'owned_test_processes_cleaned', 'production_configurations_unchanged')


def require(value):
    if not value:
        raise ValueError('artifact_chain_rejected')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def runner_sha():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate(receipt, manifest, historical, profile):
    require(receipt.get('format') == 'socialmei-release040-chain-v1')
    require(receipt.get('source_sha') == SOURCE and receipt.get('images') == IMAGES)
    require(digest(manifest) == MANIFEST_SHA and receipt.get('source_manifest_sha256') == MANIFEST_SHA)
    require(manifest['sources'] == {'api': SOURCE, 'gateway': SOURCE, 'fallback': B2})
    profile.rehearsal040(historical, BASE_SOURCE)
    require(historical.get('api_image_id') == 'sha256:0a7050f73cab2b06b89b5b91fc0232c92fd0b41b029ac9710518d5255ca8a569')
    require(receipt.get('historical_migration_receipt_sha256') == digest(historical))
    require(receipt.get('source_migrations') == profile.MIGRATIONS040)
    require(receipt.get('runner_sha256') == runner_sha())
    require(receipt.get('mail_fixture_count') == 2)
    require(receipt.get('snapshot_tool_sha256') == hashlib.sha256(
        (ROOT / 'tools/schema040-rollback-rehearsal.py').read_bytes()).hexdigest())
    require(receipt.get('schema_evidence_scope') == 'unchanged_sql_only')
    for role in IMAGES:
        audit = receipt.get('audits', {}).get(role, {})
        require(audit.get('id') == IMAGES[role] and audit.get('files') == manifest['files'][role])
        require(audit.get('source') == manifest['sources'][role] and audit.get('architecture') == 'amd64')
        require(audit.get('entrypoint') is None and audit.get('sensitive_env_keys') == [])
        command = (['caddy', 'run', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile']
                   if role == 'gateway' else ['uvicorn', 'app:app', '--host', '0.0.0.0', '--port', '8000'])
        require(audit.get('command') == command)
    require(all(receipt.get('checks', {}).get(key) is True for key in CHECKS))
    require(receipt.get('gateway_config_validated') is True)
    require(receipt.get('synthetic_database') == 'socialmei_tests040_20261114')
    require(all(receipt.get(key) is False for key in ('migrations_executed', 'restores_executed',
                'production_changed', 'provider_sends', 'production_ready')))
    return True


def run(args, data=None, timeout=120):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('isolated_chain_command_failed')
    return result.stdout


def audit(role, image):
    info = json.loads(run(['docker', 'image', 'inspect', image]))[0]
    require(info['Id'] == image)
    env = dict(item.split('=', 1) for item in info['Config'].get('Env', []) if '=' in item)
    secret_keys = [key for key, value in env.items() if value and any(
        word in key.upper() for word in ('PASSWORD', 'SECRET', 'TOKEN', 'KEYRING', 'DATABASE_URL'))]
    base = ['docker', 'run', '--rm', '-i', '--network', 'none', '--read-only', '--memory', '128m']
    if role == 'gateway':
        command = ('test -z "$(find /srv/frontend -type l -print -quit)" && '
                   "find /srv/frontend -type f -exec sha256sum {} ';' && sha256sum /etc/caddy/Caddyfile")
        output = run(base + ['--entrypoint', 'sh', image, '-c', command]).decode()
        files = {line[66:]: line[:64] for line in output.splitlines()}
    else:
        code = """import pathlib,json,hashlib
p=pathlib.Path('/app');files=list(p.rglob('*.py'))+[p/'requirements.txt']
assert not any(f.is_symlink() for f in files) and not list(p.glob('*.pyc'))
print(json.dumps({str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}))
"""
        files = json.loads(run(base + ['--entrypoint', 'python', image, '-B', '-'], code.encode()))
    return {'id': image, 'source': info['Config'].get('Labels', {}).get('org.opencontainers.image.revision'),
            'architecture': info['Architecture'], 'entrypoint': info['Config'].get('Entrypoint'),
            'command': info['Config'].get('Cmd'), 'sensitive_env_keys': secret_keys, 'files': files}


CLIENT = """import os,json,hashlib,psycopg
from fastapi.testclient import TestClient
from app import app
ORIGIN='https://chain.example.test'
client=TestClient(app,base_url=ORIGIN)
def request(path,method='GET',payload=None,account=None,extra=None):
 headers={'Origin':ORIGIN,'X-SocialMEI-Client':'browser'}
 if account:headers.update(Cookie=account['cookie'],**{'X-SocialMEI-CSRF':account['identity']['csrf_token']})
 headers.update(extra or {})
 response=client.request(method,'/api/v1/'+path,headers=headers,json=payload)
 return response.status_code,response.json() if response.content else None,response.headers
def check(value,code):
 if not value:raise RuntimeError(code)
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
 check(conn.execute('SELECT current_database()').fetchone()[0]=='socialmei_tests040_20261114','wrong_database')
 check(conn.execute('SELECT count(*) FROM socialmei.schema_migrations').fetchone()[0]==40,'wrong_schema')
"""

SEED = CLIENT + """
from http.cookies import SimpleCookie
from uuid import uuid4
accounts=[];nonce=uuid4().hex
for name in ('pending','verified'):
 status,identity,headers=request('auth/register','POST',{'nome':'Chain synthetic '+name,'email':name+'-'+nonce+'@example.test','senha':'Synthetic-proof-123!'})
 check(status==201,'registration_failed')
 cookies=SimpleCookie(headers['set-cookie']);accounts.append({'identity':identity,'cookie':'__Host-socialmei-session='+cookies['__Host-socialmei-session'].value})
ids=[]
with psycopg.connect(os.environ['DATABASE_URL']) as conn:
 verified=accounts[1]['identity']['usuario']['id']
 conn.execute('UPDATE socialmei.auth_email_activation SET verified_at=NOW() WHERE user_id=%s',(verified,))
 conn.execute("UPDATE socialmei.auth_identity_mail SET status='used' WHERE user_id=%s",(verified,))
 for account in accounts:
  ids.append(conn.execute('INSERT INTO socialmei.crm_clientes(workspace_id,nome) VALUES(%s,%s) RETURNING id',(account['identity']['negocio']['id'],'Chain synthetic client')).fetchone()[0])
state={'accounts':accounts,'clients':ids}
with open('/results/state.private.json','x') as out:os.chmod(out.name,0o600);json.dump(state,out)
print('{}')
"""

PROBE = CLIENT + """
state=json.load(open('/results/state.private.json'));pending,verified=state['accounts']
for account,expected in ((pending,False),(verified,True)):
 status,identity,_=request('auth/me',account=account)
 check(status==200 and identity['usuario']['id']==account['identity']['usuario']['id'] and identity['negocio']['id']==account['identity']['negocio']['id'],'session_not_preserved')
 check(identity['email_verification']=={'required':True,'verified':expected},'activation_not_preserved')
 check(request('auth/session',account=account)[0]==200,'session_probe_failed')
for method,payload in (('GET',None),('POST',{'nome':'Forbidden synthetic write'})):
 check(request('clientes',method,payload,pending)[0]==403,'pending_access_opened')
status,clients,_=request('clientes',account=verified)
check(status==200 and [x['id'] for x in clients]==[state['clients'][1]],'workspace_list_leaked')
check(request('clientes/'+str(state['clients'][0]),account=verified)[0]==404,'foreign_read_allowed')
check(request('clientes/'+str(state['clients'][0]),'DELETE',account=verified)[0]==404,'foreign_delete_allowed')
status,clients,_=request('clientes?workspace_id='+str(pending['identity']['negocio']['id']),account=verified)
check(status==200 and [x['id'] for x in clients]==[state['clients'][1]],'workspace_parameter_trusted')
check(request('clientes',account=verified,extra={'X-SocialMEI-Identity':str(verified['identity']['usuario']['id'])+':'+str(pending['identity']['negocio']['id'])})[0]==409,'foreign_identity_trusted')
print('{}')
"""


def execute(workspace):
    require(workspace.is_dir() and not workspace.is_symlink())
    base = workspace.parent.parent
    envfile = base / 'tests.private.env'
    env = dict(line.split('=', 1) for line in envfile.read_text().splitlines() if '=' in line)
    url = urlsplit(env['DATABASE_URL']); query = parse_qs(url.query, keep_blank_values=True)
    require(env.get('TEST_DATABASE_URL') == env['DATABASE_URL'] and url.path == '/socialmei_tests040_20261114')
    require(url.hostname == 'socialmei-postgres-relocation-20261112' and (url.port or 5432) == 5432
            and query == {'sslmode': ['verify-full'], 'sslrootcert': ['/run/database-ca.crt']})
    manifest = json.loads((workspace / 'source/source-manifest.json').read_text())
    require(digest(manifest) == MANIFEST_SHA)
    historical = json.loads((ROOT / 'docs/evidence/20261113-mission3-schema040-rehearsal.json').read_text())
    profile = load_module('chain_profile', 'team-release-profile.py')
    receipt = {'format': 'socialmei-release040-chain-v1', 'source_sha': SOURCE, 'images': IMAGES,
               'source_manifest_sha256': MANIFEST_SHA, 'historical_migration_receipt_sha256': digest(historical),
               'source_migrations': profile.MIGRATIONS040, 'runner_sha256': runner_sha(),
               'schema_evidence_scope': 'unchanged_sql_only', 'synthetic_database': 'socialmei_tests040_20261114',
               'migrations_executed': False, 'restores_executed': False, 'production_changed': False,
               'provider_sends': False, 'production_ready': False}
    receipt['audits'] = {role: audit(role, image) for role, image in IMAGES.items()}
    for role in IMAGES:
        require(receipt['audits'][role]['files'] == manifest['files'][role])
    run(['docker', 'run', '--rm', '--network', 'none', '--memory', '96m', '--tmpfs', '/data', '--tmpfs', '/config',
         '--env', 'SOCIALMEI_TEAM_HOST=chain.example.test', '--entrypoint', 'caddy', IMAGES['gateway'],
         'validate', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'])
    receipt['gateway_config_validated'] = True
    live = run(['docker', 'ps', '-q']).decode().split()
    before = {identity: json.loads(run(['docker', 'inspect', identity]))[0] for identity in live}
    results = workspace / 'results'; results.mkdir(mode=0o700)
    token = secrets.token_hex(8)
    def probe(image, code, mode='disabled'):
        args = ['docker', 'run', '--rm', '-i', '--label', 'socialmei.chain040=' + token,
                '--network', 'socialmei-postgres-relocation-20261112-isolated', '--read-only',
                '--user', str(os.getuid()) + ':' + str(os.getgid()), '--memory', '192m', '--memory-swap', '256m',
                '--cpus', '0.35', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--tmpfs', '/tmp:rw,size=32m', '--env-file', str(envfile),
                '--mount', 'type=bind,src=' + str(base / 'database-ca.crt') + ',dst=/run/database-ca.crt,readonly',
                '--mount', 'type=bind,src=' + str(results) + ',dst=/results',
                '--env', 'SOCIALMEI_AUTH_ORIGIN=https://chain.example.test', '--env', 'SOCIALMEI_REGISTRATION_MODE=open',
                '--env', 'SOCIALMEI_IDENTITY_MODE=' + mode,
                '--env', 'SOCIALMEI_SMTP_HOST=smtp.example.test', '--env', 'SOCIALMEI_SMTP_PORT=465',
                '--env', 'SOCIALMEI_SMTP_USER=synthetic', '--env', 'SOCIALMEI_SMTP_PASSWORD=synthetic',
                '--env', 'SOCIALMEI_SMTP_FROM=sender@example.test', '--entrypoint', 'python', image, '-B', '-']
        try:
            return json.loads(run(args, code.encode()))
        finally:
            for identity in run(['docker', 'ps', '-aq', '--filter', 'label=socialmei.chain040=' + token]).decode().split():
                obj = json.loads(run(['docker', 'inspect', identity]))[0]
                require(obj['Config']['Labels'].get('socialmei.chain040') == token
                        and set(obj['NetworkSettings']['Networks']) == {'socialmei-postgres-relocation-20261112-isolated'})
                run(['docker', 'rm', '-f', '-v', identity])
    old_runner = load_module('old_chain_probe', 'schema040-rollback-rehearsal.py')
    receipt['snapshot_tool_sha256'] = hashlib.sha256(
        (ROOT / 'tools/schema040-rollback-rehearsal.py').read_bytes()).hexdigest()
    snapshot = old_runner.SNAPSHOT
    probe(IMAGES['api'], SEED, 'enforced')
    probe(IMAGES['api'], PROBE, 'enforced')
    mail = probe(IMAGES['api'], CLIENT + """
state=json.load(open('/results/state.private.json'));ids=[a['identity']['usuario']['id'] for a in state['accounts']]
with psycopg.connect(os.environ['DATABASE_URL']) as c:
 row=c.execute("SELECT count(*),count(*) FILTER(WHERE status='pending'),count(*) FILTER(WHERE status='used') FROM socialmei.auth_identity_mail WHERE user_id=ANY(%s)",(ids,)).fetchone()
 check(row==(2,1,1),'mail_fixture_missing')
print(json.dumps({'mail_fixture_count':row[0]}))
""")
    state = probe(IMAGES['api'], snapshot)
    require(state.get('auth_identity_mail') and state.get('schema_migrations'))
    for _ in range(2):
        probe(IMAGES['fallback'], PROBE)
        require(probe(IMAGES['fallback'], snapshot) == state)
    require(not run(['docker', 'ps', '-aq', '--filter', 'label=socialmei.chain040=' + token]).strip())
    require(all(all(json.loads(run(['docker', 'inspect', identity]))[0][key] == obj[key]
                    for key in ('Image', 'Config', 'HostConfig', 'Mounts')) for identity, obj in before.items()))
    receipt['checks'] = dict.fromkeys(CHECKS, True)
    receipt.update(mail)
    receipt['durable_state_sha256'] = digest(state)
    receipt['test_process_transition'] = 'candidate exited; two distinct fresh fallback processes; no existing service restart'
    receipt['test_fixtures_retained'] = True
    validate(receipt, manifest, historical, profile)
    output = workspace / 'artifact-chain-receipt.json'
    with output.open('x') as stream:
        os.chmod(output, 0o600); json.dump(receipt, stream, indent=2)
    return {'artifact_chain_checks_passed': True, 'images': IMAGES, 'production_ready': False,
            'new_restores_or_migrations': False, 'receipt': str(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--workspace', type=Path)
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'mode': 'plan', 'production_changed': False, 'restores_or_migrations': False}))
        return
    try:
        print(json.dumps(execute(args.workspace)))
    except Exception:
        raise SystemExit('artifact_chain_failed; no production action authorized') from None


if __name__ == '__main__':
    main()
