"""Channel booking contracts and disposable PostgreSQL only; no provider calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import os
import unittest
from unittest.mock import patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
import psycopg
from psycopg.rows import dict_row

import appointments
import channel_booking as booking
import test_account_auth as accounts
import test_service_appointments as fixtures
from test_waha_ingress import KEY, payload, raw, sign
from waha_ingress import WahaBinding, WahaIngressService
from message_enrichment import _append_inbox_message

PATH = '/api/v1/agenda/channel-booking'


class BookingContractTests(unittest.TestCase):
    def test_policy_fails_closed_and_rejects_invalid_hours_and_client_identity(self):
        self.assertFalse(booking.BookingPolicy().enabled)
        for value in ({'enabled': True}, {'timezone': 'unknown/zone'},
                      {'hours': [{'weekday': 0, 'opens': '18:00', 'closes': '09:00'}]},
                      {'hours': [{'weekday': 0, 'opens': '09:00', 'closes': '11:00'},
                                 {'weekday': 0, 'opens': '10:00', 'closes': '12:00'}]}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                booking.BookingPolicy.model_validate(value)
        with self.assertRaises(ValidationError):
            booking.MessageContext(origin='waha', conversation_id=1, source_message_id=1,
                                   cliente_id=3, workspace_id=2)

    def test_token_is_signed_domain_separated_and_never_returns_key(self):
        value = dict(binding='a', policy='b', service=1, service_revision=1,
                     resource=str(uuid4()), resource_revision=1,
                     start='2026-11-15T12:00:00Z', expires=2000000000)
        token = booking.confirmation_token(value, KEY)
        self.assertNotIn(KEY, token)
        self.assertEqual(booking.decode_confirmation(token, KEY), value)
        for changed in ('x' + token, token[:-1], token + '.', ''):
            with self.subTest(changed=changed), self.assertRaises(HTTPException):
                booking.decode_confirmation(changed, KEY)
        with self.assertRaises(HTTPException) as error:
            booking.decode_confirmation(token, KEY + 'other')
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(HTTPException) as error:
            booking.confirmation_token(value, '')
        self.assertEqual(error.exception.status_code, 503)

    def test_hours_lead_grid_horizon_and_dst_boundaries(self):
        policy = booking.BookingPolicy(enabled=True, timezone='America/Recife', lead_minutes=60,
            hours=[{'weekday': day, 'opens': '09:00', 'closes': '17:00'} for day in range(7)])
        now = datetime(2026, 11, 12, 10, tzinfo=timezone.utc)
        start = datetime(2026, 11, 12, 9, tzinfo=ZoneInfo(policy.timezone))
        self.assertTrue(booking.allowed_start(policy, start, 30, now))
        for changed, duration in ((start.replace(hour=8), 30), (start.replace(minute=1), 30),
                                  (start.replace(hour=16, minute=45), 30),
                                  (start + timedelta(days=31), 30)):
            self.assertFalse(booking.allowed_start(policy, changed, duration, now))
        dst = booking.BookingPolicy(enabled=True, timezone='America/New_York', lead_minutes=0,
            hours=[{'weekday': 6, 'opens': '00:00', 'closes': '06:00'}])
        for day, hour in ((datetime(2026, 3, 8), 2), (datetime(2026, 11, 1), 1)):
            ambiguous = day.replace(hour=hour, tzinfo=ZoneInfo(dst.timezone))
            self.assertFalse(booking.allowed_start(dst, ambiguous, 30,
                             ambiguous.astimezone(timezone.utc) - timedelta(days=1)))

    def test_supplied_connection_is_not_committed_closed_or_replaced(self):
        conn = SimpleNamespace(row_factory=None, execute=lambda *_: None)
        with patch('channel_booking.connect', side_effect=AssertionError('must reuse transaction')):
            with booking.transaction(conn) as actual:
                self.assertIs(actual, conn)


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class ChannelBookingDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register
    post = fixtures.AppointmentDatabaseTests.post

    def setUp(self):
        fixtures.AppointmentDatabaseTests.setUp(self)
        self.workspace = self.client.identity['negocio']['id']
        flags = patch.dict(os.environ, {'SOCIALMEI_WAHA_INGRESS_MODE': 'isolated',
                                       'SOCIALMEI_WAHA_LAB_ENVIRONMENT': 'isolated'})
        flags.start()
        self.addCleanup(flags.stop)
        with psycopg.connect(accounts.DB) as conn:
            channel = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,"
                "identificador_conta,ingress_provisioned,ativo) VALUES(%s,'booking-fixture','default',"
                "'111@c.us',true,true) RETURNING id", (self.workspace,)).fetchone()[0]
        self.binding = WahaBinding(instance='booking-fixture', session='default',
            account_id='111@c.us', workspace_id=self.workspace, channel_id=channel, hmac_key=KEY)
        self.ingress = WahaIngressService({self.binding.instance: self.binding})
        registry = patch('waha_ingress.waha_service', return_value=self.ingress)
        registry.start()
        self.addCleanup(registry.stop)
        self.context = self.incoming()
        self.policy = {'enabled': True, 'timezone': 'UTC', 'lead_minutes': 0,
            'hours': [{'weekday': day, 'opens': '09:00', 'closes': '17:00'} for day in range(7)]}
        response = self.client.put(PATH, json={'expected_revision': 0, 'policy': self.policy})
        self.assertEqual(response.status_code, 200, response.text)
        self.day = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

    def incoming(self, sender='222@c.us'):
        sample = payload(mid='false_' + sender + '_' + uuid4().hex)
        sample['payload']['from'] = sender
        sample['payload']['timestamp'] = int(datetime.now(timezone.utc).timestamp())
        body = raw(sample)
        self.assertEqual(self.ingress.receive(self.binding.instance, body, sign(body), 'sha512')['processed'], 1)
        with psycopg.connect(accounts.DB) as conn:
            message, conversation = conn.execute('SELECT id,conversation_id FROM socialmei.me_messages '
                'WHERE workspace_id=%s AND external_message_id=%s',
                (self.workspace, sample['payload']['id'])).fetchone()
            conn.execute('UPDATE socialmei.me_conversations SET cliente_id=%s WHERE workspace_id=%s AND id=%s',
                         (self.person['id'], self.workspace, conversation))
        return {'origin': 'waha', 'conversation_id': conversation, 'source_message_id': message}

    def offer(self, context=None):
        response = self.client.post(PATH + '/slots', json={**(context or self.context),
            'service_id': self.service['id'], 'resource_id': self.resource['id'], 'day': self.day})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['items'])
        return response.json()['items'][0]['confirmation']

    def confirm(self, token, context=None, client=None):
        return (client or self.client).post(PATH + '/confirm', json={**(context or self.context),
                                            'confirmation': token, 'confirmed': True})

    def test_authenticated_journey_persists_once_and_uses_existing_agenda(self):
        services = self.client.post(PATH + '/services', json=self.context)
        self.assertEqual(services.status_code, 200, services.text)
        self.assertEqual(services.json()['items'][0]['id'], self.service['id'])
        resources = self.client.post(PATH + '/resources', json={**self.context, 'service_id': self.service['id']})
        self.assertEqual(resources.status_code, 200, resources.text)
        token = self.offer()
        created = self.confirm(token)
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(self.confirm(token).json(), created.json())
        fresh = self.login('admin@example.com')
        items = fresh.get('/api/v1/agenda/appointments?from_date=' + self.day + '&to_date=' + self.day)
        self.assertEqual([row['id'] for row in items.json()['items']], [created.json()['id']])
        history = fresh.get('/api/v1/agenda/appointments/' + created.json()['id'] + '/history')
        self.assertEqual(len(history.json()['items']), 1)

    def test_explicit_confirmation_binding_human_pause_and_policy_revision(self):
        token = self.offer()
        other = self.incoming('333@c.us')
        self.assertEqual(self.confirm(token, other).status_code, 409)
        self.assertEqual(self.client.post(PATH + '/confirm', json={**self.context,
            'confirmation': token, 'confirmed': False}).status_code, 409)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.wa_bot_conversations SET state='human' "
                'WHERE workspace_id=%s AND conversation_id=%s', (self.workspace, self.context['conversation_id']))
        self.assertEqual(self.confirm(token).status_code, 409)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.wa_bot_conversations SET state='menu' "
                'WHERE workspace_id=%s AND conversation_id=%s', (self.workspace, self.context['conversation_id']))
        changed = self.client.put(PATH, json={'expected_revision': 1, 'policy': self.policy})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.confirm(token).status_code, 409)

    def test_lost_response_retry_survives_expiry_and_policy_change_without_new_booking(self):
        token = self.offer()
        other_context = self.incoming('333@c.us')
        pending = self.offer(other_context)
        created = self.confirm(token)
        self.assertEqual(created.status_code, 200, created.text)
        # The first response was lost; an expired offer may identify an existing
        # operation, but it must never authorize a new booking.
        with patch('channel_booking.datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime.now(timezone.utc) + timedelta(minutes=20)
            self.assertEqual(self.confirm(token).json(), created.json())
            self.assertEqual(self.confirm(pending, other_context).status_code, 409)
        changed = self.client.put(PATH, json={'expected_revision': 1,
                                             'policy': {**self.policy, 'enabled': False}})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.confirm(token).json(), created.json())
        self.assertEqual(self.confirm(pending, other_context).status_code, 409)
        self.assertEqual(self.confirm(token, other_context).status_code, 409)
        self.assertEqual(self.confirm(token[:-1]).status_code, 409)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.agenda_appointments '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 1)
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.agenda_appointment_history '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 1)

    def test_two_contacts_compete_for_one_slot_and_only_one_is_committed(self):
        second = self.incoming('333@c.us')
        tokens = [(self.offer(), self.context), (self.offer(second), second)]
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda pair: self.confirm(*pair), tokens))
        self.assertEqual(sorted(row.status_code for row in results), [200, 409])
        with psycopg.connect(accounts.DB) as conn:
            count = conn.execute('SELECT count(*) FROM socialmei.agenda_appointments WHERE workspace_id=%s',
                                 (self.workspace,)).fetchone()[0]
        self.assertEqual(count, 1)

    def test_failure_rolls_back_booking_and_history_without_reserving_slot(self):
        token = self.offer()
        with patch('appointments.history', side_effect=RuntimeError('isolated failure')):
            self.assertEqual(self.confirm(token).status_code, 503)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.agenda_appointments '
                'WHERE workspace_id=%s', (self.workspace,)).fetchone()[0], 0)
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_instagram_uses_same_appointment_engine_and_checks_human_pause(self):
        connection_id = uuid4()
        with psycopg.connect(accounts.DB, row_factory=dict_row) as conn:
            conn.execute("INSERT INTO socialmei.ig_meta_connections(id,workspace_id,external_account_id,"
                "account_type,status,scopes,encrypted_token,token_kind,issued_at,expires_at) "
                "VALUES(%s,%s,'123456789','BUSINESS','connected',"
                "ARRAY['instagram_business_basic','instagram_business_manage_messages'],"
                "'isolated-not-a-provider-token','long',NOW(),NOW()+INTERVAL '1 day')",
                (connection_id, self.workspace))
            message = _append_inbox_message(conn, self.workspace, SimpleNamespace(channel='instagram',
                account_ref='instagram:123456789', contact_ref='instagram:987654321',
                contact_name='Cliente Instagram fictício', external_message_id='isolated-booking-ig',
                text='Agendar', occurred_at=datetime.now(timezone.utc)), 'a' * 64, origin='instagram')
            conn.execute("INSERT INTO socialmei.ig_meta_ingress_events(external_account_id,event_key,"
                "workspace_id,connection_id,kind,fingerprint,status,message_id) "
                "VALUES('123456789',%s,%s,%s,'message',%s,'processed',%s)",
                ('a' * 64, self.workspace, connection_id, 'a' * 64, message['message_id']))
            conn.execute('UPDATE socialmei.me_conversations SET cliente_id=%s WHERE workspace_id=%s AND id=%s',
                         (self.person['id'], self.workspace, message['conversation_id']))
        context = {'origin': 'instagram', 'conversation_id': message['conversation_id'],
                   'source_message_id': message['message_id']}
        with patch('channel_booking.settings.instagram_n8n_ingress_configuration',
                   return_value={'meta_app_secret': KEY}):
            token = self.offer(context)
            result = self.confirm(token, context)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['cliente_id'], self.person['id'])
            with psycopg.connect(accounts.DB) as conn:
                conn.execute("UPDATE socialmei.ig_menu_conversations SET state='human' "
                    'WHERE workspace_id=%s AND conversation_id=%s', (self.workspace, context['conversation_id']))
            self.assertEqual(self.confirm(token, context).status_code, 409)

    def test_permissions_csrf_revocation_and_foreign_workspace_are_enforced(self):
        outsider = self.register('isolated-booking@example.com')
        self.assertEqual(outsider.post(PATH + '/services', json=self.context).status_code, 404)
        token = self.offer()
        self.assertEqual(outsider.post(PATH + '/confirm', json={**self.context,
            'confirmation': token, 'confirmed': True}).status_code, 404)
        self.client.headers.pop('X-SocialMEI-CSRF')
        self.assertEqual(self.confirm(token).status_code, 403)
        self.client = self.login('admin@example.com')
        uid = self.client.identity['usuario']['id']
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE workspace_id=%s AND user_id=%s",
                         (self.workspace, uid))
        self.assertEqual(self.confirm(token).status_code, 403)
        self.assertEqual(self.client.put(PATH, json={'expected_revision': 1, 'policy': self.policy}).status_code, 403)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute('UPDATE socialmei.auth_sessoes SET revogada_em=NOW() WHERE user_id=%s', (uid,))
        self.assertEqual(self.client.get(PATH).status_code, 401)


if __name__ == '__main__':
    unittest.main()
