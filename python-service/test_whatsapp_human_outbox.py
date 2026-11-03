"""Human replies use signed fixtures, an injected provider and disposable PostgreSQL."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

import psycopg
from pydantic import ValidationError

from app import app
from whatsapp_human_outbox import DraftInput, WhatsAppReplyService, reply_service
import test_whatsapp_bot as bot_fixtures
import test_account_auth as fixtures

PATH = '/api/v1/whatsapp/replies'


class ReplyValidationTests(unittest.TestCase):
    def test_text_and_browser_selected_destination_are_rejected(self):
        valid = {'operation_id': str(uuid4()), 'source_message_id': 1, 'text': 'Olá'}
        self.assertEqual(DraftInput(**valid).text, 'Olá')
        for update in ({'text': ''}, {'text': '\x00'}, {'text': '\ud800'},
                       {'text': 'á' * 2049}, {'text': 1}, {'source_message_id': True},
                       {'destination': '222@c.us'}, {'workspace_id': 2}):
            with self.subTest(update=repr(update)), self.assertRaises(ValidationError):
                DraftInput(**{**valid, **update})

    def test_production_service_has_no_transport_and_is_closed_by_default(self):
        service = reply_service()
        self.assertFalse(service.send_enabled)
        self.assertIsNone(service.transport)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class HumanReplyDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.AccountDatabaseTests.setUpClass.__func__)
    register = fixtures.AccountDatabaseTests.register
    invited = fixtures.AccountDatabaseTests.invited
    login = fixtures.AccountDatabaseTests.login
    db = bot_fixtures.BotDatabaseTests.db
    incoming = bot_fixtures.BotDatabaseTests.incoming

    def setUp(self):
        bot_fixtures.BotDatabaseTests.setUp(self)
        self.sent = []
        self.reply_service = WhatsAppReplyService(transport=self.transport, allow_dispatch=True)
        app.dependency_overrides[reply_service] = lambda: self.reply_service
        self.addCleanup(app.dependency_overrides.pop, reply_service, None)
        self.external_id = self.incoming('Mensagem autorizada de teste')
        with self.db() as conn:
            self.source_id, self.conversation = conn.execute(
                'SELECT id,conversation_id FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s',
                (self.workspace, self.external_id),
            ).fetchone()

    def transport(self, delivery):
        self.sent.append(delivery)
        return 'human-fixture-' + str(len(self.sent))

    def draft(self, **updates):
        data = {'operation_id': str(uuid4()), 'source_message_id': self.source_id,
                'text': 'Resposta humana de teste'}
        data.update(updates)
        return self.owner.post(PATH, json=data), data

    def send(self, reply):
        return self.owner.post(PATH + '/' + reply['id'] + '/send', json={})

    def test_persisted_draft_pauses_bot_replays_and_rejects_changed_content(self):
        response, data = self.draft()
        self.assertEqual(response.status_code, 201, response.text)
        reply = response.json()
        self.assertEqual(reply['id'], data['operation_id'])
        self.assertEqual(reply['status'], 'draft')
        self.assertEqual(self.owner.post(PATH, json=data).json(), reply)
        self.assertEqual(self.owner.post(PATH, json={**data, 'text': 'Diferente'}).status_code, 409)
        with self.db() as conn:
            self.assertEqual(conn.execute(
                'SELECT state FROM socialmei.wa_bot_conversations WHERE workspace_id=%s AND conversation_id=%s',
                (self.workspace, self.conversation),
            ).fetchone()[0], 'human')
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.wa_human_replies').fetchone()[0], 1)
        history = self.owner.get(PATH, params={'conversation_id': self.conversation}).json()
        self.assertEqual(history['items'], [reply])
        self.assertTrue(history['send_enabled'])
        self.assertFalse(self.sent)

    def test_disabled_send_preserves_draft_and_never_calls_provider(self):
        reply = self.draft()[0].json()
        self.reply_service.send_enabled = False
        response = self.send(reply)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertFalse(self.sent)
        self.assertEqual(self.owner.get(PATH + '/' + reply['id']).json()['status'], 'draft')

    def test_private_transport_policy_rejects_contact_before_claim_or_provider(self):
        from settings import WhatsAppHumanConfiguration
        from whatsapp_human_transport import WahaHumanTransport
        configuration = WhatsAppHumanConfiguration(
            self.workspace, 'trusted-a', 'default', bot_fixtures.BOT_ACCOUNT,
            frozenset({'333@c.us'}), 'http://waha:3000', 'synthetic-private-key-only',
        )
        transport = WahaHumanTransport(configuration)
        self.reply_service.workspace_id = self.workspace
        self.reply_service.policy = transport.validate_scope
        reply = self.draft()[0].json()
        self.assertEqual(self.send(reply).status_code, 403)
        self.assertFalse(self.sent)
        with self.db() as conn:
            row = conn.execute('SELECT status,claimed_at FROM socialmei.wa_human_replies WHERE id=%s',
                               (reply['id'],)).fetchone()
        self.assertEqual(row, ('draft', None))

    def test_send_capability_is_not_advertised_to_other_workspace_or_viewer(self):
        self.reply_service.workspace_id = self.workspace
        self.assertTrue(self.owner.get(PATH).json()['send_enabled'])
        other = self.register('human-capability-other@example.test')
        self.assertFalse(other.get(PATH).json()['send_enabled'])
        with self.db() as conn:
            conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE workspace_id=%s',
                         ('viewer', self.workspace))
        self.assertFalse(self.owner.get(PATH).json()['send_enabled'])

    def test_confirmed_receipt_is_durable_and_replay_never_sends_twice(self):
        reply = self.draft()[0].json()
        response = self.send(reply)
        self.assertEqual(response.status_code, 200, response.text)
        confirmed = response.json()
        self.assertEqual(confirmed['status'], 'confirmed')
        self.assertEqual(confirmed['provider_confirmation'], 'accepted')
        self.assertEqual(confirmed['provider_message_id'], 'human-fixture-1')
        self.assertEqual(self.send(reply).json(), confirmed)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.sent[0], {'path': '/api/sendText', 'body': {
            'session': 'default', 'chatId': '222@c.us', 'text': reply['text'],
        }})
        self.assertEqual(self.owner.get(PATH + '/' + reply['id']).json()['status'], 'confirmed')

    def test_signed_lid_and_long_direct_sender_keep_exact_verified_destination(self):
        for sender in ('contact.primary-123@lid', '2' * 40 + '@c.us'):
            external = self.incoming('Mensagem direta autorizada', sender=sender)
            with self.db() as conn:
                source_id = conn.execute(
                    'SELECT id FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s',
                    (self.workspace, external),
                ).fetchone()[0]
            response, _ = self.draft(source_message_id=source_id)
            self.assertEqual(response.status_code, 201, response.text)
            result = self.send(response.json())
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['status'], 'confirmed')
            self.assertEqual(self.sent[-1]['body']['chatId'], sender)

    def test_timeout_and_invalid_receipt_become_uncertain_without_retry(self):
        for index, transport in enumerate((lambda _: (_ for _ in ()).throw(TimeoutError('private-provider-details')),
                                           lambda _: {'id': 'not-an-accepted-receipt'})):
            external = self.incoming('Teste autorizado', sender=str(300 + index) + '@c.us')
            with self.db() as conn:
                self.source_id = conn.execute(
                    'SELECT id FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s',
                    (self.workspace, external),
                ).fetchone()[0]
            self.reply_service.transport = transport
            reply = self.draft()[0].json()
            result = self.send(reply)
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(result.json()['status'], 'uncertain')
            with patch.object(self.reply_service, 'transport', side_effect=AssertionError('never resend')):
                self.assertEqual(self.send(reply).json()['status'], 'uncertain')
            self.assertNotIn('private-provider', result.text)
            self.assertEqual(self.draft()[0].status_code, 409)

    def test_foreign_workspace_roles_csrf_and_browser_destination_are_blocked(self):
        reply = self.draft()[0].json()
        other = self.register('human-other@example.test')
        self.assertEqual(other.get(PATH + '/' + reply['id']).status_code, 404)
        self.assertEqual(other.post(PATH + '/' + reply['id'] + '/send', json={}).status_code, 404)
        self.assertEqual(other.post(PATH, json={
            'operation_id': str(uuid4()), 'source_message_id': self.source_id, 'text': 'No',
        }).status_code, 404)
        self.assertEqual(self.owner.post(PATH + '/' + reply['id'] + '/send',
                                        headers={'X-SocialMEI-CSRF': ''}, json={}).status_code, 403)
        self.assertEqual(self.draft(destination='forged@c.us')[0].status_code, 422)
        with self.db() as conn:
            conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE workspace_id=%s', ('viewer', self.workspace))
        self.assertEqual(self.owner.get(PATH).status_code, 200)
        self.assertEqual(self.draft()[0].status_code, 403)
        with self.db() as conn:
            conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE workspace_id=%s', ('report_viewer', self.workspace))
        self.assertEqual(self.owner.get(PATH).status_code, 403)
        self.assertFalse(self.sent)

    def test_claimed_and_uncertain_bot_reply_block_draft_without_partial_pause_or_write(self):
        decision = self.tech.post('/internal/whatsapp/bot/decisions', headers=self.headers, json={
            'instance': 'trusted-a', 'external_message_id': self.external_id,
        }).json()
        base = '/internal/whatsapp/bot/decisions/' + decision['operation_id']
        self.assertTrue(self.tech.post(base + '/claim', headers=self.headers, json={}).json()['dispatch_allowed'])
        for status in ('claimed', 'uncertain'):
            with self.subTest(status=status):
                if status == 'uncertain':
                    receipt = self.tech.post(base + '/receipt', headers=self.headers, json={'status': status})
                    self.assertEqual(receipt.status_code, 200, receipt.text)
                response, _ = self.draft()
                self.assertEqual(response.status_code, 409, response.text)
                with self.db() as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.wa_human_replies').fetchone()[0], 0)
                    self.assertEqual(conn.execute('SELECT state FROM socialmei.wa_bot_conversations').fetchone()[0], 'menu')
                self.assertFalse(self.sent)

    def test_rebound_channel_refuses_send_before_provider(self):
        reply = self.draft()[0].json()
        with self.db() as conn:
            conn.execute('UPDATE socialmei.crm_canais SET versao=versao+1 WHERE id=%s', (self.channel,))
        self.assertEqual(self.send(reply).status_code, 409)
        self.assertFalse(self.sent)

    def test_bot_resume_and_claim_remain_blocked_during_human_send_and_uncertain_result(self):
        decision = self.tech.post('/internal/whatsapp/bot/decisions', headers=self.headers, json={
            'instance': 'trusted-a', 'external_message_id': self.external_id,
        }).json()
        reply = self.draft()[0].json()
        base = '/api/v1/whatsapp/bot/conversations/' + str(self.conversation)
        def bot_state():
            resumed = self.owner.post(base + '/resume', json={'channel_id': self.channel})
            claimed = self.tech.post('/internal/whatsapp/bot/decisions/' + decision['operation_id'] + '/claim',
                                     headers=self.headers, json={})
            return resumed.status_code, claimed.status_code, claimed.json().get('dispatch_allowed')
        during_dispatch = []
        def uncertain_transport(delivery):
            self.sent.append(delivery)
            during_dispatch.append(bot_state())
            raise TimeoutError('synthetic timeout')
        self.reply_service.transport = uncertain_transport
        self.assertEqual(self.send(reply).json()['status'], 'uncertain')
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(during_dispatch, [(409, 200, False)])
        self.assertEqual(bot_state(), (409, 200, False))

    def test_concurrent_send_claim_is_committed_once(self):
        reply = self.draft()[0].json()
        # Use the service with a server-authenticated identity/session, independent HTTP clients are unnecessary.
        from account_auth import COOKIE, digest
        user = {'id': self.owner.identity['usuario']['id'], 'workspace_id': self.workspace}
        session = digest(self.owner.cookies.get(COOKIE))
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.reply_service.send(user, session, reply['id']), range(2)))
        self.assertEqual(len(self.sent), 1)
        self.assertTrue(all(item['status'] in {'dispatching', 'confirmed'} for item in results))
        self.assertEqual(self.owner.get(PATH + '/' + reply['id']).json()['status'], 'confirmed')

    def test_failed_receipt_persistence_does_not_resend_after_accepted_provider(self):
        reply = self.draft()[0].json()
        finish = self.reply_service.finish
        def unavailable(*args):
            with patch('whatsapp_human_outbox.connect', side_effect=psycopg.OperationalError('private-database')):
                return finish(*args)
        with patch.object(self.reply_service, 'finish', side_effect=unavailable):
            response = self.send(reply)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('private-database', response.text)
        self.assertEqual(self.send(reply).json()['status'], 'dispatching')
        self.assertEqual(len(self.sent), 1)

    def test_duplicate_provider_receipt_becomes_uncertain(self):
        self.reply_service.transport = lambda _: 'same-provider-id'
        first = self.send(self.draft()[0].json()).json()
        second = self.send(self.draft()[0].json()).json()
        self.assertEqual(first['status'], 'confirmed')
        self.assertEqual(second['status'], 'uncertain')
        self.assertIsNone(second['provider_message_id'])
