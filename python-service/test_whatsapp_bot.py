"""Bot planning uses signed persisted fixtures and disposable PostgreSQL only."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from app import app
import test_account_auth as account_fixtures
from test_waha_ingress import payload, raw, sign, KEY
from waha_ingress import WahaBinding, WahaIngressService

PATH = '/internal/whatsapp/bot'
BOT_ACCOUNT = '991234567890@c.us'


class BotClosedContracts(unittest.TestCase):
    def test_live_contact_allowlist_fails_closed_and_validates_every_entry(self):
        import settings
        with patch.dict(os.environ, {'SOCIALMEI_WAHA_INGRESS_MODE': 'team-pilot'}):
            for raw_contacts in ('', 'not-json', '[]', '["222@c.us", "bad"]', '"222@c.us"'):
                with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_BOT_ALLOWED_CONTACTS': raw_contacts}):
                    self.assertEqual(settings.whatsapp_bot_allowed_contacts(), frozenset())
            with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_BOT_ALLOWED_CONTACTS': '["222@c.us"]'}):
                self.assertEqual(settings.whatsapp_bot_allowed_contacts(), frozenset({'waha:222@c.us'}))

    def test_pending_sources_are_closed_before_database_when_bot_disabled(self):
        with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_BOT_ENABLED': 'false'}), patch(
            'whatsapp_bot.connect', side_effect=AssertionError('unexpected database')
        ):
            response = TestClient(app).get(PATH + '/sources')
        self.assertEqual(response.status_code, 503)

    def test_database_failure_is_sanitized_without_provider_or_message_details(self):
        with patch.dict(os.environ, {
            'SOCIALMEI_WHATSAPP_BOT_ENABLED': 'true',
            'SOCIALMEI_AUTH_ENABLED': 'true',
            'SOCIALMEI_SHARED_DATA_ENABLED': 'true',
            'SOCIALMEI_AUTH_ORIGIN': 'https://app.example.com',
        }), patch('whatsapp_bot.connect', side_effect=psycopg.OperationalError('private-database-details')):
            response = TestClient(app, raise_server_exceptions=False).post(PATH + '/decisions', json={
                'instance': 'trusted-a', 'external_message_id': 'hello',
            })
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-database', response.text)

    def test_unconfigured_bot_is_closed_not_missing(self):
        with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_BOT_ENABLED': 'false'}):
            response = TestClient(app).post(PATH + '/decisions', json={
                'instance': 'trusted-a', 'external_message_id': 'hello',
            })
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_menu_renderer_is_explicit_about_engine_support(self):
        from whatsapp_bot import render_waha
        choices = [{'id': '1', 'title': 'Ver produtos'}, {'id': '5', 'title': 'Atendente'}]
        for engine in ('WEBJS', 'UNKNOWN', 'GOWS', 'NOWEB'):
            result = render_waha('main', '222@c.us', 'Olá', choices, engine=engine)
            self.assertEqual(result['path'], '/api/sendText')
            self.assertIn('1 - Ver produtos', result['body']['text'])
        for engine in ('GOWS', 'NOWEB'):
            result = render_waha('main', '222@c.us', 'Olá', choices,
                                 engine=engine, list_verified=True)
            self.assertEqual(result['path'], '/api/sendList')
            rows = result['body']['message']['sections'][0]['rows']
            self.assertEqual([r['rowId'] for r in rows], ['1', '5'])
        self.assertEqual(render_waha('main', '222@c.us', 'Olá', choices,
                                     engine='WEBJS', list_verified=True)['path'], '/api/sendText')


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class BotDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(account_fixtures.AccountDatabaseTests.setUpClass.__func__)
    register = account_fixtures.AccountDatabaseTests.register
    invited = account_fixtures.AccountDatabaseTests.invited
    login = account_fixtures.AccountDatabaseTests.login

    def setUp(self):
        account_fixtures.AccountDatabaseTests.setUp(self)
        flags = patch.dict(os.environ, {
            'SOCIALMEI_WHATSAPP_BOT_ENABLED': 'true',
            'SOCIALMEI_WAHA_INGRESS_MODE': 'isolated',
            'SOCIALMEI_WAHA_LAB_ENVIRONMENT': 'isolated',
        })
        flags.start()
        self.addCleanup(flags.stop)
        self.owner = self.register('bot-owner@example.test')
        self.workspace = self.owner.identity['negocio']['id']
        with self.db() as conn:
            self.channel = conn.execute(
                "INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) "
                "VALUES(%s,'trusted-a','default',%s,true,true) RETURNING id", (self.workspace, BOT_ACCOUNT),
            ).fetchone()[0]
        self.service = WahaIngressService({'trusted-a': WahaBinding(
            'trusted-a', 'default', BOT_ACCOUNT, self.workspace, self.channel, KEY,
        )})
        self.tech = TestClient(app)
        response = self.owner.post('/api/v1/whatsapp/bot/access', json={'channel_id': self.channel})
        self.assertEqual(response.status_code, 200, response.text)
        self.token = response.json()['token_once']
        self.headers = {'Authorization': 'Bearer ' + self.token}

    def db(self):
        return psycopg.connect(os.environ['TEST_DATABASE_URL'])

    def incoming(self, text, *, sender='222@c.us', timestamp=None):
        import time
        mid = 'false_' + sender + '_' + uuid4().hex
        event = payload(mid)
        event['me']['id'] = BOT_ACCOUNT
        event['payload']['to'] = BOT_ACCOUNT
        event['payload'].update(body=text, **{'from': sender})
        event['payload']['timestamp'] = timestamp or int(time.time())
        event['timestamp'] = event['payload']['timestamp'] * 1000
        data = raw(event)
        self.service.receive('trusted-a', data, sign(data), 'sha512')
        return mid

    def decide(self, mid, **extra):
        return self.tech.post(PATH + '/decisions', headers=self.headers, json={
            'instance': 'trusted-a', 'external_message_id': mid, **extra,
        })

    def product(self, name='Óleo de motor', stock=7):
        r = self.owner.post('/api/v1/produtos', json={
            'nome': name, 'tipo': 'Produto', 'preco': 12.5, 'estoque': stock, 'minimo': 0,
        })
        self.assertEqual(r.status_code, 201, r.text)

    def test_pending_references_only_include_recent_unplanned_own_received_messages(self):
        import time
        mid = self.incoming('Private fixture text')
        self.incoming('old', timestamp=int(time.time()) - 3600)
        response = self.tech.get(PATH + '/sources', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'sources': [{'instance': 'trusted-a', 'external_message_id': mid}]})
        self.assertNotIn('Private fixture', response.text)
        # Provider IDs may embed contact identity: references stay private and are never logged.
        self.assertEqual(set(response.json()['sources'][0]), {'instance', 'external_message_id'})
        planned = self.decide(mid).json()
        replay = self.tech.get(PATH + '/sources', headers=self.headers).json()['sources']
        self.assertEqual(replay, [{'instance': 'trusted-a', 'external_message_id': mid}])
        self.tech.post(PATH + '/decisions/' + planned['operation_id'] + '/claim', headers=self.headers, json={})
        self.assertEqual(self.tech.get(PATH + '/sources', headers=self.headers).json(), {'sources': []})
        self.assertEqual(self.tech.get(PATH + '/sources').status_code, 401)

    def test_owner_pause_before_first_decision_is_durable_and_resume_is_explicit(self):
        mid = self.incoming('Hello')
        with self.db() as c:
            conv = c.execute('SELECT conversation_id FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s', (self.workspace, mid)).fetchone()[0]
        base = '/api/v1/whatsapp/bot/conversations/' + str(conv)
        status = self.owner.get(base + '/status')
        self.assertEqual(status.status_code, 200, status.text)
        self.assertEqual(status.json()['channel_id'], self.channel)
        self.assertEqual(status.json()['state'], 'menu')
        for _ in range(2):
            self.assertEqual(self.owner.post(base + '/pause', json={'channel_id': self.channel}).status_code, 204)
        self.assertEqual(self.owner.get(base + '/status').json()['state'], 'human')
        self.assertEqual(self.decide(mid).json()['action'], 'human_wait')
        self.assertEqual(self.owner.post(base + '/resume', json={'channel_id': self.channel}).status_code, 204)
        self.assertEqual(self.decide(self.incoming('Hello again')).json()['action'], 'menu')

    def test_pause_invalidates_unclaimed_decision_and_reports_existing_claim(self):
        first = self.decide(self.incoming('Hello')).json()
        base = '/api/v1/whatsapp/bot/conversations/' + str(first['conversation_id'])
        self.assertEqual(self.owner.post(base + '/pause', json={'channel_id': self.channel}).status_code, 204)
        claim = self.tech.post(PATH + '/decisions/' + first['operation_id'] + '/claim', headers=self.headers, json={})
        self.assertFalse(claim.json()['dispatch_allowed'])
        self.owner.post(base + '/resume', json={'channel_id': self.channel})
        second = self.decide(self.incoming('Hello again')).json()
        self.tech.post(PATH + '/decisions/' + second['operation_id'] + '/claim', headers=self.headers, json={})
        self.owner.post(base + '/pause', json={'channel_id': self.channel})
        self.assertTrue(self.owner.get(base + '/status').json()['claimed_in_flight'])

    def test_explicit_pause_cancels_unclaimed_customer_handoff_acknowledgement(self):
        decision = self.decide(self.incoming('5')).json()
        self.owner.post('/api/v1/whatsapp/bot/conversations/' + str(decision['conversation_id']) + '/pause',
                        json={'channel_id': self.channel})
        result = self.tech.post(PATH + '/decisions/' + decision['operation_id'] + '/claim', headers=self.headers, json={})
        self.assertFalse(result.json()['dispatch_allowed'])

    def test_pilot_allowlist_covers_sources_planning_and_claim_after_revocation(self):
        mid = self.incoming('Hello')
        with patch.dict(os.environ, {'SOCIALMEI_WAHA_INGRESS_MODE': 'team-pilot',
                                    'SOCIALMEI_WHATSAPP_BOT_ALLOWED_CONTACTS': '[]'}):
            self.assertEqual(self.tech.get(PATH + '/sources', headers=self.headers).json(), {'sources': []})
            self.assertEqual(self.decide(mid).status_code, 403)
            with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_BOT_ALLOWED_CONTACTS': '["222@c.us"]'}):
                self.assertEqual(len(self.tech.get(PATH + '/sources', headers=self.headers).json()['sources']), 1)
                planned = self.decide(mid).json()
            claim = self.tech.post(PATH + '/decisions/' + planned['operation_id'] + '/claim', headers=self.headers, json={})
            self.assertFalse(claim.json()['dispatch_allowed'])

    def test_pause_refuses_cross_workspace_wrong_channel_and_missing_csrf(self):
        decision = self.decide(self.incoming('Hello')).json()
        base = '/api/v1/whatsapp/bot/conversations/' + str(decision['conversation_id'])
        foreign = self.register('other-bot-owner@example.test')
        self.assertEqual(foreign.get(base + '/status').status_code, 404)
        self.assertEqual(foreign.post(base + '/pause', json={'channel_id': self.channel}).status_code, 404)
        self.assertEqual(self.owner.post(base + '/pause', json={'channel_id': self.channel + 100}).status_code, 404)
        self.assertEqual(self.owner.post(base + '/pause', headers={'X-SocialMEI-CSRF': ''}, json={'channel_id': self.channel}).status_code, 403)

    def test_menu_catalog_prompt_persists_and_uses_real_price(self):
        self.product()
        first = self.decide(self.incoming('Olá'))
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['action'], 'menu')
        self.assertEqual(len(first.json()['choices']), 5)
        ask = self.decide(self.incoming('2')).json()
        self.assertEqual(ask['action'], 'ask_product')
        found = self.decide(self.incoming('óleo')).json()
        self.assertEqual(found['action'], 'availability')
        self.assertIn('Óleo de motor', found['text'])
        self.assertIn('12,50', found['text'])
        self.assertIn('7', found['text'])
        self.assertEqual(found['items'][0]['disponibilidade'], 'em_estoque')

    def test_zero_stock_not_claimed_unavailable_and_services_have_no_stock(self):
        self.product(stock=0)
        self.decide(self.incoming('2'))
        found = self.decide(self.incoming('óleo')).json()
        self.assertIn('confirmar', found['text'].lower())
        self.assertNotIn('esgotado', found['text'].lower())
        r = self.owner.post('/api/v1/produtos', json={'nome': 'Troca', 'tipo': 'Serviço', 'preco': 20})
        self.assertEqual(r.status_code, 201, r.text)
        service = self.decide(self.incoming('3')).json()
        self.assertEqual(service['items'][0]['tipo'], 'Serviço')
        self.assertNotIn('estoque:', service['text'].lower())

    def test_handoff_is_durable_silent_until_owner_resumes(self):
        handoff = self.decide(self.incoming('5')).json()
        self.assertTrue(handoff['handoff'])
        silent = self.decide(self.incoming('oi de novo')).json()
        self.assertEqual(silent['action'], 'human_wait')
        self.assertEqual(silent['text'], '')
        self.assertEqual(silent['status'], 'skipped')
        response = self.owner.post('/api/v1/whatsapp/bot/conversations/' + str(handoff['conversation_id']) + '/resume',
                                   json={'channel_id': self.channel})
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(self.decide(self.incoming('Olá')).json()['action'], 'menu')

    def test_replay_and_concurrency_create_one_decision_and_one_claim(self):
        mid = self.incoming('Olá')
        def prepare(_):
            return self.decide(mid)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(prepare, range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        one, two = [r.json() for r in responses]
        self.assertEqual(one['operation_id'], two['operation_id'])
        claim_path = PATH + '/decisions/' + one['operation_id'] + '/claim'
        def claim(_):
            return self.tech.post(claim_path, headers=self.headers, json={})
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, range(2)))
        self.assertEqual(sorted(r.json()['dispatch_allowed'] for r in claims), [False, True])
        winner = next(r.json() for r in claims if r.json()['dispatch_allowed'])
        self.assertEqual(winner['delivery']['path'], '/api/sendText')
        self.assertEqual(winner['delivery']['body']['chatId'], '222@c.us')

    def test_receipt_requires_claim_is_idempotent_and_never_releases_retry(self):
        decision = self.decide(self.incoming('Olá')).json()
        base = PATH + '/decisions/' + decision['operation_id']
        receipt = {'status': 'confirmed', 'provider_message_id': 'true_222@c.us_provider'}
        self.assertEqual(self.tech.post(base + '/receipt', headers=self.headers, json=receipt).status_code, 409)
        self.assertTrue(self.tech.post(base + '/claim', headers=self.headers, json={}).json()['dispatch_allowed'])
        for _ in range(2):
            self.assertEqual(self.tech.post(base + '/receipt', headers=self.headers, json=receipt).status_code, 200)
        self.assertFalse(self.tech.post(base + '/claim', headers=self.headers, json={}).json()['dispatch_allowed'])
        changed = {**receipt, 'provider_message_id': 'different'}
        self.assertEqual(self.tech.post(base + '/receipt', headers=self.headers, json=changed).status_code, 409)

    def test_tenant_binding_revocation_and_unverified_messages_are_rejected(self):
        other = self.register('bot-other@example.test')
        self.assertEqual(other.post('/api/v1/whatsapp/bot/access', json={'channel_id': self.channel}).status_code, 404)
        self.assertEqual(self.decide('not-a-received-message').status_code, 404)
        self.assertEqual(self.decide(self.incoming('oi'), workspace_id=self.workspace).status_code, 422)
        route = PATH + '/decisions'
        body = {'instance': 'wrong-instance', 'external_message_id': self.incoming('oi')}
        self.assertEqual(self.tech.post(route, headers=self.headers, json=body).status_code, 401)
        secret = self.owner.post('/api/v1/whatsapp/catalog/access', json={'channel_id': self.channel}).json()['token_once']
        body['instance'] = 'trusted-a'
        self.assertEqual(self.tech.post(route, headers={'Authorization': 'Bearer ' + secret}, json=body).status_code, 401)
        self.assertEqual(self.owner.delete('/api/v1/whatsapp/bot/access/' + str(self.channel)).status_code, 204)
        self.assertEqual(self.decide(self.incoming('oi')).status_code, 401)

    def test_old_and_superseded_decisions_never_authorize_send(self):
        import time
        stale = self.decide(self.incoming('oi', timestamp=int(time.time()) - 3600)).json()
        self.assertEqual(stale['status'], 'skipped')
        one = self.decide(self.incoming('oi')).json()
        self.decide(self.incoming('5'))
        result = self.tech.post(PATH + '/decisions/' + one['operation_id'] + '/claim', headers=self.headers, json={})
        self.assertFalse(result.json()['dispatch_allowed'])

    def test_credentials_do_not_leak_and_csrf_stays_required(self):
        status = self.owner.get('/api/v1/whatsapp/bot/access')
        self.assertEqual(status.status_code, 200, status.text)
        self.assertNotIn(self.token, status.text)
        self.owner.headers.pop('X-SocialMEI-CSRF')
        self.assertEqual(self.owner.post('/api/v1/whatsapp/bot/access', json={'channel_id': self.channel}).status_code, 403)

    def test_rotation_rejects_old_token_and_history_is_owner_scoped(self):
        self.decide(self.incoming('5'))
        other = self.register('different-bot@example.test')
        self.assertEqual(other.get('/api/v1/whatsapp/bot/conversations').json()['items'], [])
        self.assertEqual(other.get('/api/v1/whatsapp/bot/decisions').json()['items'], [])
        state = self.owner.get('/api/v1/whatsapp/bot/conversations').json()['items'][0]
        self.assertEqual(state['state'], 'human')
        old = self.token
        self.token = self.owner.post('/api/v1/whatsapp/bot/access', json={'channel_id': self.channel}).json()['token_once']
        self.assertNotEqual(old, self.token)
        self.assertEqual(self.decide(self.incoming('Olá')).status_code, 401)
        self.headers = {'Authorization': 'Bearer ' + self.token}
        self.assertEqual(self.decide(self.incoming('Olá')).json()['action'], 'human_wait')

    def test_uncertain_receipt_never_retries(self):
        item = self.decide(self.incoming('Olá')).json()
        path = PATH + '/decisions/' + item['operation_id']
        self.tech.post(path + '/claim', json={}, headers=self.headers)
        data = {'status': 'uncertain'}
        for _ in range(2):
            r = self.tech.post(path + '/receipt', json=data, headers=self.headers)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['status'], 'uncertain')
        self.assertFalse(self.tech.post(path + '/claim', json={}, headers=self.headers).json()['dispatch_allowed'])

    def test_stale_event_does_not_invalidate_newer_reply_or_change_menu(self):
        import time
        fresh = self.decide(self.incoming('2')).json()
        self.decide(self.incoming('5', timestamp=int(time.time()) - 3600))
        claimed = self.tech.post(PATH + '/decisions/' + fresh['operation_id'] + '/claim', json={}, headers=self.headers)
        self.assertTrue(claimed.json()['dispatch_allowed'])
        self.assertEqual(self.owner.get('/api/v1/whatsapp/bot/conversations').json()['items'][0]['state'], 'ask_product')

    def test_engine_unsupported_payload_is_not_accepted_as_verified_text(self):
        item = payload('unsupported-button')
        item['me']['id'] = BOT_ACCOUNT
        item['payload']['to'] = BOT_ACCOUNT
        import time
        item['payload'].update(timestamp=int(time.time()), type='buttons_response', body='5')
        body = raw(item)
        self.service.receive('trusted-a', body, sign(body), 'sha512')
        self.assertEqual(self.decide('unsupported-button').status_code, 404)

    def test_other_channel_same_workspace_cannot_use_decision(self):
        item = self.decide(self.incoming('Olá')).json()
        with self.db() as conn:
            channel = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) "
                                   "VALUES(%s,'trusted-b','main','998877665544@c.us',true,true) RETURNING id", (self.workspace,)).fetchone()[0]
        token = self.owner.post('/api/v1/whatsapp/bot/access', json={'channel_id': channel}).json()['token_once']
        headers = {'Authorization': 'Bearer ' + token}
        self.assertEqual(self.tech.post(PATH + '/decisions/' + item['operation_id'] + '/claim', headers=headers, json={}).status_code, 404)

    def test_invalid_input_response_never_echoes_private_text(self):
        r = self.decide(self.incoming('Olá'), text='private-input-not-allowed')
        self.assertEqual(r.status_code, 422)
        self.assertNotIn('private-input', r.text)

    def test_viewer_cannot_manage_credentials_or_resume_conversations(self):
        with self.db() as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE workspace_id=%s AND user_id=%s",
                         (self.workspace, self.owner.identity['usuario']['id']))
        self.assertEqual(self.owner.get('/api/v1/whatsapp/bot/access').status_code, 403)
        self.assertEqual(self.owner.post('/api/v1/whatsapp/bot/access', json={'channel_id': self.channel}).status_code, 403)

    def test_changed_channel_requires_new_credential_and_cancels_old_decision(self):
        item = self.decide(self.incoming('Olá')).json()
        with self.db() as conn:
            conn.execute("UPDATE socialmei.crm_canais SET sessao='other-session',versao=versao+1 WHERE id=%s", (self.channel,))
        path = PATH + '/decisions/' + item['operation_id'] + '/claim'
        response = self.tech.post(path, json={}, headers=self.headers)
        self.assertEqual(response.status_code, 401, response.text)
        token = self.owner.post('/api/v1/whatsapp/bot/access', json={'channel_id': self.channel}).json()['token_once']
        response = self.tech.post(path, json={}, headers={'Authorization': 'Bearer ' + token})
        self.assertEqual(response.status_code, 409, response.text)

    def test_limit_does_not_prevent_customer_from_requesting_human(self):
        for _ in range(20):
            self.assertEqual(self.decide(self.incoming('Olá')).json()['status'], 'planned')
        limited = self.decide(self.incoming('Olá')).json()
        self.assertEqual(limited['status'], 'skipped')
        self.assertEqual(limited['action'], 'rate_limited')
        handoff = self.decide(self.incoming('5')).json()
        self.assertTrue(handoff['handoff'])
        self.assertEqual(handoff['action'], 'human_handoff')
