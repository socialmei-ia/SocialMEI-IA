"""Only the dedicated local disposable database; synthetic incoming events, no sends.

Executed in the fixture container, never the API or production container.
Random HMACs stay in its root-owned Docker volume, mounted read-only by the API.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.error
import urllib.request

from database import connect

REGISTRY = Path('/run/socialmei/private/waha-registry.json')


def guard():
    if (os.getenv('SOCIALMEI_LOCAL_FIXTURE_KIND') != 'wa-inbox-e2e'
            or os.getenv('POSTGRES_DB') != 'socialmei_wa_inbox_e2e'
            or os.getenv('POSTGRES_HOST') != 'database'
            or os.getenv('POSTGRES_USER') != 'preview'
            or os.geteuid() != 0):
        raise ValueError('not_owned_local_fixture')
    with connect() as conn:
        if conn.execute('SELECT current_database()').fetchone()[0] != 'socialmei_wa_inbox_e2e':
            raise ValueError('not_owned_local_fixture')


def setup(workspaces):
    if (not isinstance(workspaces, list) or len(workspaces) != 2
            or len(set(workspaces)) != 2
            or any(type(w) is not int or w < 1 for w in workspaces)):
        raise ValueError('invalid_fixture_workspaces')
    registry = json.loads(REGISTRY.read_text()) if REGISTRY.exists() else {'version': 1, 'bindings': []}
    with connect() as conn:
        for workspace in workspaces:
            owner = conn.execute(
                "SELECT 1 FROM socialmei.workspace_members m JOIN socialmei.users u ON u.id=m.user_id "
                "WHERE m.workspace_id=%s AND m.role='owner' AND u.email LIKE '%%@example.test'",
                (workspace,),
            ).fetchone()
            if not owner:
                raise ValueError('fictional_owner_required')
            existing = [b for b in registry['bindings'] if b['workspace_id'] == workspace]
            if existing:
                continue
            alias = 'local-inbox-' + str(workspace)
            session = 'local-session-' + str(workspace)
            # Deliberately too short to be a real phone number; no provider exists here.
            account = str(1000000 + workspace) + '@c.us'
            channel = conn.execute(
                'INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ingress_provisioned,ativo,envio_habilitado) '
                'VALUES(%s,%s,%s,%s,true,true,false) RETURNING id,versao',
                (workspace, alias, session, account),
            ).fetchone()
            registry['bindings'].append({'workspace_id': workspace, 'channel_id': channel[0],
                'instance': alias, 'session': session, 'account_id': account,
                'revision': channel[1], 'hmac_key': secrets.token_hex(48)})
    REGISTRY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    REGISTRY.parent.chmod(0o700)
    temporary = REGISTRY.with_name('registry-' + secrets.token_hex(6) + '.tmp')
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(registry, stream)
    temporary.replace(REGISTRY)
    return {'setup': True, 'binding_count': len(workspaces)}


def emit(command):
    registry = json.loads(REGISTRY.read_text())
    binding = next(b for b in registry['bindings'] if b['workspace_id'] == command['workspace_id'])
    body = {'id': 'local-envelope', 'timestamp': command['timestamp_ms'],
        'event': command.get('event', 'message'), 'session': binding['session'],
        'me': {'id': binding['account_id']}, 'engine': 'WEBJS',
        'payload': {'id': command['mid'], 'timestamp': command['timestamp_ms'] // 1000,
            'from': command.get('sender', '222@c.us'), 'to': binding['account_id'], 'fromMe': False,
            'hasMedia': False, 'body': command['text']}}
    if command.get('forged_workspace'):
        body['workspace_id'] = command['forged_workspace']
    raw = json.dumps(body, separators=(',', ':')).encode()
    signature = hmac.new(binding['hmac_key'].encode(), raw, hashlib.sha512).hexdigest()
    if command.get('tamper'):
        raw += b' '
    request = urllib.request.Request('http://api:8000/internal/waha/' + binding['instance'] + '/webhook',
        data=raw, headers={'Content-Type': 'application/json', 'X-Webhook-Hmac': signature,
                          'X-Webhook-Hmac-Algorithm': 'sha512'})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.load(response)
            return {'status': response.status, 'processed': result.get('processed', 0),
                    'duplicates': result.get('duplicates', 0)}
    except urllib.error.HTTPError as error:
        return {'status': error.code}


def main():
    guard()
    command = json.load(sys.stdin)
    if command['action'] == 'setup':
        result = setup(command['workspaces'])
    elif command['action'] == 'emit':
        result = emit(command)
    else:
        raise ValueError('invalid_fixture_action')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print(json.dumps({'passed': False, 'code': 'local_fixture_failed_details_redacted'}))
        sys.exit(2)
