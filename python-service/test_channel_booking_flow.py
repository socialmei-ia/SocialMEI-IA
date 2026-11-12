"""Signed synthetic WAHA inputs through the existing planner, never a real sender."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import test_account_auth as accounts
import test_whatsapp_bot as bot_fixtures
from test_waha_ingress import payload, gows_list_payload, raw, sign
from waha_ingress import WahaIngressService

PATH = bot_fixtures.PATH
BOT_ACCOUNT = bot_fixtures.BOT_ACCOUNT


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class ChannelBookingFlowTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited
    login = accounts.AccountDatabaseTests.login
    db = bot_fixtures.BotDatabaseTests.db
    decide = bot_fixtures.BotDatabaseTests.decide

    def setUp(self):
        bot_fixtures.BotDatabaseTests.setUp(self)
        self.native = False
        self.last_mid = None
        self.customer = self.create('/api/v1/clientes', {'nome': 'Cliente canal fictício'})
        self.service_row = self.create('/api/v1/produtos', {'nome': 'Avaliação fictícia',
            'tipo': 'Serviço', 'preco': 80, 'duracao_minutos': 30})
        self.resource = self.create('/api/v1/agenda/resources', {'operation_id': str(uuid4()), 'nome': 'Consultório fictício'})
        policy = {'enabled': True, 'timezone': 'UTC', 'lead_minutes': 0,
            'hours': [{'weekday': day, 'opens': '09:00', 'closes': '17:00'} for day in range(7)]}
        response = self.owner.put('/api/v1/agenda/channel-booking', json={'expected_revision': 0, 'policy': policy})
        self.assertEqual(response.status_code, 200, response.text)
        registry = patch('waha_ingress.waha_service', side_effect=lambda: self.service)
        registry.start()
        self.addCleanup(registry.stop)

    def create(self, path, value):
        result = self.owner.post(path, json=value)
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def plan(self, text, *, link_customer=True):
        mid = 'false_222@c.us_' + uuid4().hex
        if text.startswith('sm:'):
            sample = gows_list_payload(choice=text, mid=mid, me={'id': BOT_ACCOUNT})
        else:
            sample = payload(mid=mid, engine='GOWS' if self.native else 'WEBJS', me={'id': BOT_ACCOUNT})
            sample['payload'].update(body=text, to=BOT_ACCOUNT)
        sample['payload']['timestamp'] = int(datetime.now(timezone.utc).timestamp())
        sample['timestamp'] = sample['payload']['timestamp'] * 1000
        body = raw(sample)
        self.assertEqual(self.service.receive('trusted-a', body, sign(body), 'sha512')['processed'], 1)
        if link_customer:
            with self.db() as conn:
                conn.execute('UPDATE socialmei.me_conversations SET cliente_id=%s WHERE workspace_id=%s',
                             (self.customer['id'], self.workspace))
        response = self.decide(mid)
        self.assertEqual(response.status_code, 200, response.text)
        self.last_mid = mid
        result = response.json()
        if result['status'] == 'planned':
            path = PATH + '/decisions/' + result['operation_id']
            claimed = self.tech.post(path + '/claim', headers=self.headers, json={})
            self.assertEqual(claimed.status_code, 200, claimed.text)
            self.assertTrue(claimed.json()['dispatch_allowed'])
            self.assertEqual(claimed.json()['delivery']['path'], '/api/sendList' if self.native else '/api/sendText')
            receipt = self.tech.post(path + '/receipt', headers=self.headers,
                json={'status': 'confirmed', 'provider_message_id': 'isolated-receipt-' + uuid4().hex})
            self.assertEqual(receipt.status_code, 200, receipt.text)
        return result

    def choose(self, result, predicate=lambda choice: choice['id'] == '1'):
        index = next(index for index, choice in enumerate(result['choices']) if predicate(choice))
        value = ('sm:' + UUID(result['operation_id']).hex + ':' + str(index)
                 if self.native else result['choices'][index]['id'])
        return self.plan(value)

    def journey(self):
        services = self.plan('6')
        self.assertEqual(services['action'], 'booking_services')
        resources = self.choose(services)
        self.assertEqual(resources['action'], 'booking_resources')
        days = self.choose(resources)
        self.assertEqual(days['action'], 'booking_days')
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
        slots = self.choose(days, lambda choice: choice.get('target', {}).get('day') == tomorrow)
        self.assertEqual(slots['action'], 'booking_slots')
        review = self.choose(slots)
        self.assertEqual(review['action'], 'booking_review')
        with self.db() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.agenda_appointments '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 0)
        saved = self.choose(review)
        self.assertEqual(saved['action'], 'booking_confirmed')
        again = self.decide(self.last_mid)
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()['operation_id'], saved['operation_id'])
        rows = self.owner.get('/api/v1/agenda/appointments?from_date=' + tomorrow + '&to_date=' + tomorrow)
        self.assertEqual(rows.status_code, 200, rows.text)
        self.assertEqual(len(rows.json()['items']), 1)
        self.assertEqual(rows.json()['items'][0]['cliente_id'], self.customer['id'])
        with self.db() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.agenda_appointment_history '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 1)

    def test_textual_journey_books_only_after_confirmation_and_replay_is_deduplicated(self):
        menu = self.plan('0')
        self.assertTrue(any(choice['id'] == '6' for choice in menu['choices']))
        self.journey()

    def test_native_list_journey_uses_opaque_offered_options_with_same_core(self):
        self.native = True
        binding = replace(self.service.registry['trusted-a'], engine='GOWS')
        self.service = WahaIngressService({'trusted-a': binding})
        with patch('whatsapp_bot.native_list_canary', return_value=True):
            self.journey()

    def test_later_slot_page_can_be_selected_from_native_list(self):
        self.native = True
        binding = replace(self.service.registry['trusted-a'], engine='GOWS')
        self.service = WahaIngressService({'trusted-a': binding})
        with patch('whatsapp_bot.native_list_canary', return_value=True):
            services = self.plan('6')
            resources = self.choose(services)
            days = self.choose(resources)
            tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()
            slots = self.choose(days, lambda choice: choice.get('target', {}).get('day') == tomorrow)
            self.assertEqual(slots['action'], 'booking_slots')
            self.assertTrue(any(choice['id'] == '6' for choice in slots['choices']))
            later = self.choose(slots, lambda choice: choice['id'] == '6')
            self.assertEqual(later['action'], 'booking_slots')
            self.assertTrue(any(choice['id'] == '7' for choice in later['choices']))
            self.assertNotEqual([choice['title'] for choice in slots['choices'][:3]],
                                [choice['title'] for choice in later['choices'][:3]])
            review = self.choose(later, lambda choice: choice['id'] == '3')
            self.assertEqual(review['action'], 'booking_review')
            saved = self.choose(review)
            self.assertEqual(saved['action'], 'booking_confirmed')
            rows = self.owner.get('/api/v1/agenda/appointments?from_date='
                                  + tomorrow + '&to_date=' + tomorrow)
            self.assertEqual(len(rows.json()['items']), 1)

    def test_missing_customer_hands_off_without_fake_client_or_booking(self):
        result = self.plan('6', link_customer=False)
        self.assertEqual(result['action'], 'booking_handoff')
        self.assertTrue(result['handoff'])
        silent = self.plan('6', link_customer=False)
        self.assertEqual(silent['action'], 'human_wait')
        self.assertEqual(silent['text'], '')
        with self.db() as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.agenda_appointments '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 0)

    def test_human_pause_and_disabled_policy_preserve_existing_menu(self):
        self.plan('6')
        handoff = self.plan('5')
        self.assertTrue(handoff['handoff'])
        self.assertEqual(self.plan('1')['action'], 'human_wait')
        response = self.owner.put('/api/v1/agenda/channel-booking',
            json={'expected_revision': 1, 'policy': {'enabled': False}})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.plan('0')['action'], 'human_wait')


if __name__ == '__main__':
    unittest.main()
