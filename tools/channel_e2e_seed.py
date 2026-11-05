#!/usr/bin/env python3
"""Private disposable lab support, executed inside the candidate Python image.

Provider transport and OAuth/session provisioning use fixtures. No application
modules are imported or patched; application requests use the real HTTP API.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def private(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    path.chmod(0o600)


def initialize(folder):
    import psycopg
    require(os.environ['DATABASE_URL'].endswith('/channel_e2e_fixture'), 'fixture_database_required')
    config = json.loads((folder / 'private.json').read_text())
    migrations = sorted(Path('/migrations').glob('*.sql'))
    require(len(migrations) == 38 and [int(p.name[:3]) for p in migrations] == list(range(1, 39)),
            'migration_sequence_invalid')
    with psycopg.connect(os.environ['DATABASE_URL']) as conn:
        conn.execute('CREATE SCHEMA IF NOT EXISTS socialmei')
        conn.execute('CREATE TABLE socialmei.schema_migrations(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())')
        for path in migrations:
            conn.execute(path.read_text(), prepare=False)
            conn.execute('INSERT INTO socialmei.schema_migrations(version) VALUES(%s)', (path.name,))
        for index in (1, 2):
            workspace = conn.execute('INSERT INTO socialmei.workspaces(slug,nome) VALUES(%s,%s) RETURNING id',
                                     ('channel-lab-' + str(index), 'Isolated fixture')).fetchone()[0]
            user = conn.execute('INSERT INTO socialmei.users(email,nome) VALUES(%s,%s) RETURNING id',
                                ('owner' + str(index) + '@example.test', 'Fixture')).fetchone()[0]
            conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')", (workspace, user))
            conn.execute("INSERT INTO socialmei.auth_credenciais(user_id,senha_hash) VALUES(%s,'$argon2id$fixture')", (user,))
            token = config['session' + str(index)]
            conn.execute("INSERT INTO socialmei.auth_sessoes(token_hash,user_id,workspace_id,expira_em) VALUES(%s,%s,%s,NOW()+INTERVAL '1 day')",
                         (hashlib.sha256(token.encode()).hexdigest(), user, workspace))
            config['workspace' + str(index)] = workspace
        workspace = config['workspace1']
        channel = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) VALUES(%s,'lab','default','111@c.us',true,true) RETURNING id,versao", (workspace,)).fetchone()
        config['channel'] = channel[0]
        fields = [workspace, channel[0], 'lab', 'default', '111@c.us', channel[1]]
        binding_hash = hashlib.sha256(json.dumps(fields, separators=(',', ':')).encode()).hexdigest()
        conn.execute('INSERT INTO socialmei.wa_bot_access(workspace_id,channel_id,token_hash,binding_hash) VALUES(%s,%s,%s,%s)',
                     (workspace, channel[0], hashlib.sha256(config['bot'].encode()).hexdigest(), binding_hash))
        conn.execute("INSERT INTO socialmei.crm_produtos(workspace_id,nome,tipo,preco,estoque,minimo) VALUES(%s,'Produto fixture','Produto',12.50,10,1)", (workspace,))
        conn.execute("INSERT INTO socialmei.ig_meta_connections(id,workspace_id,external_account_id,account_type,status,scopes,encrypted_token,token_kind,issued_at,expires_at) VALUES(%s,%s,'987654321','BUSINESS','connected',ARRAY['instagram_business_basic','instagram_business_manage_messages'],'fixture-unused','long',NOW(),NOW()+INTERVAL '1 day')", (uuid4(), workspace))
    private(folder / 'private.json', config)
    private(folder / 'waha-registry.json', {'version': 1, 'bindings': [{
        'instance': 'lab', 'session': 'default', 'account_id': '111@c.us',
        'workspace_id': workspace, 'channel_id': channel[0], 'hmac_key': config['waha'],
    }]})


def provider():
    class Handler(BaseHTTPRequestHandler):
        count = 0
        legacy = 0
        mode = 'ok'
        catalog_verified = False

        def log_message(self, *_):
            pass

        def reply(self, status, value):
            raw = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            try:
                self.wfile.write(raw)
            except BrokenPipeError:
                pass

        def do_GET(self):
            self.reply(200, {'sends': Handler.count, 'legacy': Handler.legacy,
                             'catalog_verified': Handler.catalog_verified})

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            if self.path == '/control':
                Handler.mode = json.loads(raw)['mode']
                return self.reply(200, {})
            if self.path != '/api/sendText':
                Handler.legacy += 1
                return self.reply(500, {'error': 'legacy_unreachable'})
            body = json.loads(raw)
            if body.get('session') != 'default' or body.get('chatId') != '222@c.us' or not body.get('text'):
                return self.reply(400, {})
            Handler.count += 1
            if all(value in body['text'] for value in ('Produto fixture', 'R$ 12,50', 'estoque: 10 registrado(s)')):
                Handler.catalog_verified = True
            if Handler.mode == 'timeout':
                time.sleep(12)
            return self.reply(500 if Handler.mode != 'ok' else 200,
                              {'id': 'fixture-receipt-' + str(Handler.count)})

    ThreadingHTTPServer(('0.0.0.0', 3000), Handler).serve_forever()


def request(url, body=None, headers=None):
    headers = dict(headers or {})
    if isinstance(body, dict):
        body = json.dumps(body, ensure_ascii=False).encode()
    if body is not None:
        headers.setdefault('Content-Type', 'application/json')
    try:
        with urlopen(Request(url, data=body, headers=headers), timeout=45) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def exercise(folder, phase):
    import psycopg
    require(os.environ['DATABASE_URL'].endswith('/channel_e2e_fixture'), 'fixture_database_required')
    config = json.loads((folder / 'private.json').read_text())
    checks = []

    def check(ok, code):
        require(ok, code)
        checks.append(code)

    def sql(statement, params=()):
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            return conn.execute(statement, params).fetchall()

    def inbox(token):
        status, raw = request('http://team-api:8000/api/v1/message-enrichment/conversations', headers={
            'Cookie': '__Host-socialmei-session=' + token})
        require(status == 200, 'inbox_http_failed')
        return json.loads(raw)['items']

    def incoming(mid, text='oi', **updates):
        stamp = int(time.time())
        value = {'id': 'event-' + mid, 'timestamp': stamp * 1000, 'event': 'message',
                 'session': 'default', 'me': {'id': '111@c.us'}, 'engine': 'WEBJS',
                 'payload': {'id': mid, 'timestamp': stamp, 'from': '222@c.us', 'to': '111@c.us',
                             'fromMe': False, 'hasMedia': False, 'body': text}}
        value.update(updates)
        raw = json.dumps(value).encode()
        return raw, {'X-Webhook-Hmac': hmac.new(config['waha'].encode(), raw, hashlib.sha512).hexdigest(),
                     'X-Webhook-Hmac-Algorithm': 'sha512'}

    def trigger(mid):
        status, _ = request('http://n8n:5678/webhook/channel-lab-wa', {'instance': 'lab', 'external_message_id': mid})
        require(status == 200, 'planner_webhook_failed')

    def wait_decision(mid, expected):
        for _ in range(100):
            rows = sql('SELECT d.status FROM socialmei.wa_bot_decisions d JOIN socialmei.me_messages m ON m.workspace_id=d.workspace_id AND m.id=d.source_message_id JOIN socialmei.crm_eventos_canal e ON e.workspace_id=m.workspace_id AND e.inbox_message_id=m.id WHERE e.mensagem_externa_id=%s', (mid,))
            if rows and rows[0][0] == expected:
                return
            time.sleep(.2)
        raise RuntimeError('planner_receipt_not_persisted')

    def meta(mid):
        value = {'object': 'instagram', 'entry': [{'id': '987654321', 'time': 1, 'messaging': [{
            'sender': {'id': '123456789'}, 'recipient': {'id': '987654321'},
            'timestamp': int(time.time() * 1000), 'message': {'mid': mid, 'text': '  Mensagem original\n'}}]}]}
        raw = json.dumps(value, ensure_ascii=False).encode()
        return raw, {'X-Hub-Signature-256': 'sha256=' + hmac.new(config['meta'].encode(), raw, hashlib.sha256).hexdigest()}

    if phase == 'outage':
        raw, headers = meta('ig-outage')
        status, body = request('http://n8n:5678/webhook/channel-lab-ig', raw, headers)
        check(status == 503 and body == b'INGRESS_UNAVAILABLE', 'instagram_api_outage_503_no_ack')
        private(folder / 'checks-outage.json', checks)
        return

    check(len(sql('SELECT version FROM socialmei.schema_migrations')) == 38, 'all_38_migrations_recorded')
    for mid, text in (('false_222@c.us_menu', 'oi'), ('false_222@c.us_catalog', '1')):
        raw, headers = incoming(mid, text)
        check(request('http://team-api:8000/internal/waha/lab/webhook', raw, headers)[0] == 200, 'waha_signed_' + text)
        trigger(mid)
        wait_decision(mid, 'confirmed')
        check(request('http://team-api:8000/internal/waha/lab/webhook', raw, headers)[0] == 200, 'waha_replay_' + text)
        trigger(mid)
    time.sleep(1)
    counts = json.loads(request('http://waha:3000/counts')[1])
    check(counts['sends'] == 2, 'waha_menu_catalog_exactly_once')
    check(counts['catalog_verified'], 'waha_catalog_price_stock_transport')
    check(sql("SELECT estoque FROM socialmei.crm_produtos WHERE nome='Produto fixture'") == [(10,)], 'catalog_stock_unchanged')
    raw, headers = incoming('false_222@c.us_bad')
    check(request('http://team-api:8000/internal/waha/lab/webhook', raw, {**headers, 'X-Webhook-Hmac': '0' * 128})[0] == 403, 'waha_bad_hmac_rejected')
    raw, headers = incoming('false_222@c.us_cross', workspace_id=config['workspace2'])
    check(request('http://team-api:8000/internal/waha/lab/webhook', raw, headers)[0] in (400, 403), 'waha_payload_workspace_rejected')
    for mode in ('500', 'timeout'):
        request('http://waha:3000/control', {'mode': mode})
        mid = 'false_222@c.us_' + mode
        raw, headers = incoming(mid, 'oi')
        require(request('http://team-api:8000/internal/waha/lab/webhook', raw, headers)[0] == 200, 'failure_ingress_failed')
        trigger(mid)
        wait_decision(mid, 'uncertain')
        before = json.loads(request('http://waha:3000/counts')[1])['sends']
        trigger(mid)
        time.sleep(1)
        check(json.loads(request('http://waha:3000/counts')[1])['sends'] == before, 'waha_' + mode + '_uncertain_no_resend')
    raw, headers = meta('ig-exact-newline')
    for _ in range(2):
        status, body = request('http://n8n:5678/webhook/channel-lab-ig', raw, headers)
        check(status == 200 and body == b'EVENT_RECEIVED', 'instagram_persist_before_ack')
    check(sql("SELECT m.text FROM socialmei.me_messages m JOIN socialmei.me_conversations c ON c.workspace_id=m.workspace_id AND c.id=m.conversation_id WHERE c.origin='instagram'") == [('  Mensagem original\n',)], 'instagram_binary_hmac_newline_dedup')
    status, _ = request('http://n8n:5678/webhook/channel-lab-ig', raw, {**headers, 'X-Hub-Signature-256': 'sha256=' + '0' * 64})
    check(status == 503, 'instagram_bad_meta_hmac_no_ack')
    own, foreign = inbox(config['session1']), inbox(config['session2'])
    check(any(row['channel'] == 'instagram' for row in own) and any(row['channel'] == 'whatsapp' for row in own), 'both_channels_visible_in_caixa')
    check(not foreign, 'caixa_workspace_isolation')
    check(json.loads(request('http://waha:3000/counts')[1])['legacy'] == 0, 'instagram_legacy_ai_sender_unreachable')
    private(folder / 'checks-main.json', checks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['initialize', 'provider', 'exercise'])
    parser.add_argument('--folder', type=Path, default=Path('/lab'))
    parser.add_argument('--phase', default='main')
    args = parser.parse_args()
    if args.mode == 'provider':
        provider()
    elif args.mode == 'initialize':
        initialize(args.folder)
    else:
        exercise(args.folder, args.phase)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Transport errors may contain secret-bearing headers or private bodies.
        code = str(error) if isinstance(error, RuntimeError) and re.fullmatch(r'[a-z0-9_]{1,100}', str(error)) else 'isolated_channel_fixture_failed'
        print(json.dumps({'code': code}))
        raise SystemExit(2)
