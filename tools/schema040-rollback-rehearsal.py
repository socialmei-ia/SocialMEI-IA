#!/usr/bin/env python3
"""Rehearse compatible API rollback on owned, network-none synthetic PostgreSQL."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import time

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('migration040', ROOT / 'tools/release040-migration-rehearsal.py')
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)
require = migration.profile.require
SOURCE = 'b2b839bae94f4eef18b670cf5a1ada68988dffe3'
IMAGE = 'sha256:0de7e2eb7a959a21fd5a767213c69eec8f947c28092ad9bf1a736bb36e3331c7'
LABEL = 'socialmei.rollback-rehearsal040'

HTTP = r'''
import json
from http.cookies import SimpleCookie
from urllib.request import Request, urlopen
from urllib.error import HTTPError
ORIGIN = 'https://rollback.example.test'
def request(path, method='GET', payload=None, account=None, extra=None):
    headers = {'Origin': ORIGIN, 'X-SocialMEI-Client': 'browser', 'Content-Type': 'application/json'}
    if account:
        headers.update(Cookie=account['cookie'])
        headers['X-SocialMEI-CSRF'] = account['identity']['csrf_token']
    headers.update(extra or {})
    req = Request('http://127.0.0.1:8000/api/v1/' + path, method=method, headers=headers,
                  data=None if payload is None else json.dumps(payload).encode())
    try:
        response = urlopen(req, timeout=10)
    except HTTPError as error:
        response = error
    content = response.read()
    return response.status, json.loads(content) if content else None, response.headers
def check(value, code):
    if not value:
        raise RuntimeError(code)
'''

REGISTER = HTTP + r'''
accounts = []
for name in ('pending', 'verified'):
    status, identity, headers = request('auth/register', 'POST',
        {'nome': 'Synthetic ' + name, 'email': name + '@example.test', 'senha': 'Synthetic-proof-123!'})
    check(status == 201, 'registration_failed')
    cookies = SimpleCookie(headers['Set-Cookie'])
    cookie = '__Host-socialmei-session=' + cookies['__Host-socialmei-session'].value
    accounts.append({'identity': identity, 'cookie': cookie})
print(json.dumps(accounts))
'''

PROBE = HTTP + r'''
pending, verified = state
for account, expected in ((pending, False), (verified, True)):
    status, identity, _ = request('auth/me', account=account)
    check(status == 200 and identity['usuario']['id'] == account['identity']['usuario']['id']
          and identity['negocio']['id'] == account['identity']['negocio']['id'], 'session_not_preserved')
    check(identity['email_verification'] == {'required': True, 'verified': expected}, 'activation_not_preserved')
    status, identity, _ = request('auth/session', account=account)
    check(status == 200 and identity is not None, 'session_probe_failed')
for method, payload in (('GET', None), ('POST', {'nome': 'Forbidden synthetic write'})):
    check(request('clientes', method, payload, pending)[0] == 403, 'pending_business_access_opened')
status, clients, _ = request('clientes', account=verified)
check(status == 200 and [item['id'] for item in clients] == [3002], 'workspace_list_leaked')
check(request('clientes/3001', account=verified)[0] == 404, 'foreign_read_allowed')
check(request('clientes/3001', 'DELETE', account=verified)[0] == 404, 'foreign_delete_allowed')
status, clients, _ = request('clientes?workspace_id=' + str(pending['identity']['negocio']['id']), account=verified)
check(status == 200 and [item['id'] for item in clients] == [3002], 'workspace_parameter_trusted')
check(request('clientes', account=verified, extra={'X-SocialMEI-Identity':
    str(verified['identity']['usuario']['id']) + ':' + str(pending['identity']['negocio']['id'])})[0] == 409,
    'foreign_identity_header_trusted')
print(json.dumps({'sessions': True, 'pending_guard': True, 'business_isolation': True}))
'''

SNAPSHOT = r'''
import hashlib
import json
from psycopg import sql
from database import connect
result = {}
with connect() as conn:
    conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
    names = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='socialmei' ORDER BY tablename").fetchall()
    for (table,) in names:
        rows = conn.execute(sql.SQL("SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),'[]'::jsonb)::text FROM socialmei.{} t").format(sql.Identifier(table))).fetchone()[0]
        result[table] = hashlib.sha256(rows.encode()).hexdigest()
    for name, query in (
        ('_sequences', "SELECT jsonb_agg(to_jsonb(s) ORDER BY sequencename)::text FROM pg_sequences s WHERE schemaname='socialmei'"),
        ('_indexes', "SELECT jsonb_agg(to_jsonb(i) ORDER BY tablename,indexname)::text FROM pg_indexes i WHERE schemaname='socialmei'")):
        result[name] = hashlib.sha256(conn.execute(query).fetchone()[0].encode()).hexdigest()
print(json.dumps(result))
'''


def options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--receipt')
    return parser.parse_args(argv)


def approved_image(value):
    require(len(value) == 1 and value[0]['Id'] == IMAGE
            and value[0]['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == SOURCE,
            'approved_image_revision_mismatch')


def owned_container(value, token, network):
    require(len(value) == 1 and value[0]['Config'].get('Labels', {}).get(LABEL) == token
            and value[0]['HostConfig']['NetworkMode'] == network,
            'cleanup_target_not_owned')


def rehearse(args, root=ROOT):
    root = root.resolve()
    hashes = migration.manifest(root)
    evidence = json.loads((root / 'docs/evidence/20261113-selfservice-release.json').read_text())
    require(evidence['source_sha'] == SOURCE and evidence['images']['api']['id'] == IMAGE,
            'approved_release_evidence_mismatch')
    proof = dict(format='socialmei-rollback040-rehearsal-v1', profile='040',
                 fallback_source_sha=SOURCE, fallback_api_image_id=IMAGE,
                 rehearsal_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                 source_migrations=hashes, schema_downgraded=False,
                 production_runtime_changed=False, production_database_changed=False,
                 production_data_used=False, provider_messages_sent=False,
                 scope='synthetic API process failure and compatible image fallback; no deployment')
    if not args.run:
        return dict(proof, mode='plan')
    require(not os.environ.get('DOCKER_HOST') or migration.local_docker(os.environ['DOCKER_HOST']),
            'local_docker_required')
    docker = lambda *values, **kw: migration.run(args.docker, *values, **kw)
    context = json.loads(docker('context', 'inspect'))
    require(len(context) == 1 and migration.local_docker(context[0]['Endpoints']['docker']['Host']),
            'local_docker_required')
    approved_image(json.loads(docker('image', 'inspect', IMAGE)))
    postgres = json.loads(docker('image', 'inspect', 'postgres:16-alpine'))
    require(len(postgres) == 1 and re.fullmatch(r'sha256:[0-9a-f]{64}', postgres[0]['Id']),
            'local_postgres_image_required')
    token = secrets.token_hex(6)
    receipt = migration.workspace_path(root, args.receipt or '.preview/rollback040-' + token + '.json')
    require(not receipt.exists(), 'receipt_already_exists')
    containers = []

    def create(network, image, *values, command=()):
        container = docker('create', '--pull=never', '--label', LABEL + '=' + token,
                           '--network', network, *values, image, *command).decode().strip()
        require(bool(re.fullmatch(r'[0-9a-f]{64}', container)), 'owned_container_not_created')
        containers.append((container, network))
        return container

    def sql(statement):
        return docker('exec', '-i', database, 'psql', '-X', '-U', 'rehearsal', '-d', 'rollback040',
                      '-v', 'ON_ERROR_STOP=1', '-Atq', data=statement.encode()).decode().strip()

    def snapshot():
        return python(runner, SNAPSHOT)

    def python(container, source, state=None):
        if state is not None:
            source = 'state = ' + repr(state) + '\n' + source
        return json.loads(docker('exec', '-i', container, 'python', '-', data=source.encode()))

    env = ['-e', 'DATABASE_URL=', '-e', 'POSTGRES_HOST=127.0.0.1', '-e', 'POSTGRES_PORT=5432',
           '-e', 'POSTGRES_USER=rehearsal', '-e', 'POSTGRES_PASSWORD=', '-e', 'POSTGRES_DB=rollback040']

    def start_api(mode):
        api = create('container:' + database, IMAGE, *env,
                     '-e', 'SOCIALMEI_AUTH_ENABLED=true', '-e', 'SOCIALMEI_SHARED_DATA_ENABLED=true',
                     '-e', 'SOCIALMEI_AUTH_ORIGIN=https://rollback.example.test',
                     '-e', 'SOCIALMEI_REGISTRATION_MODE=open', '-e', 'SOCIALMEI_IDENTITY_MODE=' + mode,
                     '-e', 'SOCIALMEI_SMTP_HOST=smtp.example.test', '-e', 'SOCIALMEI_SMTP_PORT=465',
                     '-e', 'SOCIALMEI_SMTP_USER=synthetic', '-e', 'SOCIALMEI_SMTP_PASSWORD=synthetic',
                     '-e', 'SOCIALMEI_SMTP_FROM=sender@example.test')
        docker('start', api)
        wait_api(api)
        return api

    def wait_api(api):
        for attempt in range(40):
            try:
                python(api, HTTP + "check(request('auth/registration')[0] == 200, 'api_not_ready'); print('{}')")
                return
            except RuntimeError:
                if attempt == 39:
                    raise
                time.sleep(.25)

    try:
        database = create('none', postgres[0]['Id'], '-e', 'POSTGRES_USER=rehearsal',
                          '-e', 'POSTGRES_DB=rollback040', '-e', 'POSTGRES_HOST_AUTH_METHOD=trust')
        docker('start', database)
        for attempt in range(40):
            try:
                docker('exec', database, 'pg_isready', '-h', '127.0.0.1', '-U', 'rehearsal')
                break
            except RuntimeError:
                if attempt == 39:
                    raise
                time.sleep(.25)
        require(sql("SELECT current_setting('server_version_num')::int/10000;") == '16', 'postgres_16_required')
        runner = create('container:' + database, IMAGE, *env,
                        '-e', 'PGOPTIONS=-c lock_timeout=3s -c statement_timeout=30s',
                        '-v', str(root / 'database/migrations') + ':/migrations:ro',
                        command=('sleep', '600'))
        docker('start', runner)
        docker('exec', '-i', runner, 'python', '-', data=(root / 'tools/team_migrate.py').read_bytes())
        require(sql('SELECT count(*) FROM socialmei.schema_migrations;') == '40', 'schema040_ledger_required')
        candidate = start_api('enforced')
        accounts = python(candidate, REGISTER)
        pending, verified = [account['identity'] for account in accounts]
        sql("UPDATE socialmei.auth_email_activation SET verified_at=NOW() WHERE user_id=" + str(verified['usuario']['id']) + ';'
            "UPDATE socialmei.auth_identity_mail SET status='used' WHERE user_id=" + str(verified['usuario']['id']) + ';'
            'INSERT INTO socialmei.crm_clientes(id,workspace_id,nome) VALUES (3001,' + str(pending['negocio']['id'])
            + ",'Synthetic pending client'),(3002," + str(verified['negocio']['id']) + ",'Synthetic verified client');")
        python(candidate, PROBE, accounts)
        before = snapshot()
        docker('kill', '--signal', 'KILL', candidate)
        require(json.loads(docker('inspect', candidate))[0]['State']['ExitCode'] == 137,
                'candidate_failure_not_observed')
        fallback = start_api('disabled')
        first = python(fallback, PROBE, accounts)
        require(snapshot() == before, 'fallback_changed_durable_state')
        docker('restart', fallback)
        wait_api(fallback)
        second = python(fallback, PROBE, accounts)
        require(first == second and snapshot() == before, 'restart_changed_durable_state')
        proof.update(mode='executed', candidate_failure='owned API SIGKILL exit 137',
                     candidate_image_id=IMAGE, candidate_source_sha=SOURCE,
                     fallback_identity_mode='disabled', postgres_image_id=postgres[0]['Id'],
                     pending_email_guard_verified=True, existing_sessions_preserved=True,
                     users_credentials_business_data_preserved=True, durable_mail_queue_preserved=True,
                     business_isolation_verified=True, fallback_restart_verified=True,
                     schema040_ledger_preserved=True, durable_table_sha256=before,
                     real_smtp_or_provider_transport_executed=False,
                     limitation='same approved image in both roles; simulates process failure, not an unapproved candidate binary')
    finally:
        for container, network in reversed(containers):
            owned_container(json.loads(docker('inspect', container)), token, network)
            docker('rm', '-f', '-v', container)
        require(not docker('ps', '-aq', '--filter', 'label=' + LABEL + '=' + token).strip(),
                'owned_cleanup_incomplete')
    proof['isolated_cleanup_verified'] = True
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, indent=2)
        stream.write('\n')
    return proof


if __name__ == '__main__':
    try:
        print(json.dumps(rehearse(options()), indent=2))
    except Exception:
        raise SystemExit('rollback040_rehearsal_failed; no production action performed') from None
