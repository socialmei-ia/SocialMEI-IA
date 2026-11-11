import os
import time
import unittest
from uuid import uuid4

import test_whatsapp_bot as fixtures
from test_waha_ingress import payload, raw, sign


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class MenuSelectionFlowTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.BotDatabaseTests.setUpClass.__func__)
    register = fixtures.BotDatabaseTests.register
    invited = fixtures.BotDatabaseTests.invited
    login = fixtures.BotDatabaseTests.login
    setUp = fixtures.BotDatabaseTests.setUp
    db = fixtures.BotDatabaseTests.db
    decide = fixtures.BotDatabaseTests.decide
    incoming = fixtures.BotDatabaseTests.incoming

    def selection(self, choice, *, sender='222@c.us', kind='list_response'):
        mid = 'false_' + sender + '_' + uuid4().hex
        event = payload(mid)
        event['me']['id'] = fixtures.BOT_ACCOUNT
        event['payload'].update({
            'to': fixtures.BOT_ACCOUNT, 'from': sender, 'type': kind,
            'body': 'Titulo visual sem autoridade', 'timestamp': int(time.time()),
        })
        event['timestamp'] = event['payload']['timestamp'] * 1000
        if kind == 'list_response':
            event['payload']['_data'] = {'listResponse': {'singleSelectReply': {'selectedRowId': choice}}}
        else:
            event['payload']['selectedButtonId'] = choice
        body = raw(event)
        first = self.service.receive('trusted-a', body, sign(body), 'sha512')
        replay = self.service.receive('trusted-a', body, sign(body), 'sha512')
        self.assertEqual(first['processed'], 1)
        self.assertEqual(replay['duplicates'], 1)
        return mid

    def test_each_selected_option_executes_its_corresponding_action_once(self):
        expected = {'0': 'menu', '1': 'products', '2': 'ask_product',
                    '3': 'services', '4': 'quote_handoff', '5': 'human_handoff',
                    '9': 'human_handoff'}
        for choice, action in expected.items():
            with self.subTest(choice=choice):
                mid = self.selection(choice, sender='22' + choice + '@c.us')
                response = self.decide(mid)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['action'], action)
                self.assertEqual(self.decide(mid).json()['operation_id'], response.json()['operation_id'])
                with self.db() as conn:
                    count = conn.execute('SELECT count(*) FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s', (self.workspace, mid)).fetchone()[0]
                self.assertEqual(count, 1)

    def test_button_handoff_is_in_inbox_and_manual_draft_never_dispatches(self):
        mid = self.selection('5', kind='buttons_response')
        handoff = self.decide(mid).json()
        self.assertTrue(handoff['handoff'])
        quiet = self.decide(self.incoming('Outra mensagem')).json()
        self.assertEqual((quiet['action'], quiet['status']), ('human_wait', 'skipped'))
        inbox = self.owner.get('/api/v1/message-enrichment/conversations')
        self.assertEqual(inbox.status_code, 200, inbox.text)
        conversation = next(c for c in inbox.json()['items'] if c['id'] == handoff['conversation_id'])
        self.assertEqual(conversation['origin'], 'waha')
        self.assertEqual(sum(m['external_message_id'] == mid for m in conversation['messages']), 1)
        with self.db() as conn:
            source_id = conn.execute('SELECT id FROM socialmei.me_messages WHERE workspace_id=%s AND external_message_id=%s', (self.workspace, mid)).fetchone()[0]
        draft = self.owner.post('/api/v1/whatsapp/replies', json={
            'operation_id': str(uuid4()), 'source_message_id': source_id,
            'text': 'Resposta manual ficticia',
        })
        self.assertEqual(draft.status_code, 201, draft.text)
        denied = self.owner.post('/api/v1/whatsapp/replies/' + draft.json()['id'] + '/send', json={})
        self.assertEqual(denied.status_code, 503, denied.text)
        self.assertEqual(self.owner.get('/api/v1/whatsapp/replies/' + draft.json()['id']).json()['status'], 'draft')
