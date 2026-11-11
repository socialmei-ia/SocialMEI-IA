"""Inbox batching contracts and disposable-PostgreSQL query budget."""
import copy
import os
import unittest
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import psycopg
from fastapi import Response
from psycopg.rows import dict_row

import message_enrichment as module


def inbox_settings(stack, workspace, *, stub=True, sentiment=True):
    stack.enter_context(patch.object(module, 'guard', return_value={'workspace_id': workspace}))
    stack.enter_context(patch.object(module.settings, 'message_enrichment_mode', return_value='stub' if stub else 'disabled'))
    stack.enter_context(patch.object(module.settings, 'instagram_ingress_isolated_enabled', return_value=True))
    stack.enter_context(patch.object(module.settings, 'instagram_live_ingress_enabled', return_value=False))
    stack.enter_context(patch.object(module.settings, 'waha_inbox_enabled', return_value=True))
    stack.enter_context(patch.object(module.settings, 'provider_sentiment_enabled', return_value=sentiment))
    stack.enter_context(patch.object(module.settings, 'provider_sentiment_allowed_workspaces', return_value=(workspace,)))


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return copy.deepcopy(self.rows)


class Connection:
    def __init__(self, size=3, origins=('synthetic', 'instagram', 'waha'), message_count=3):
        self.queries = []
        self.conversations = [{'id': i, 'channel': 'instagram' if origins[(i-1) % len(origins)] == 'instagram' else 'whatsapp',
                               'account_ref': 'fixture:account', 'contact_ref': str(i), 'contact_name': 'Fixture',
                               'revision': 1, 'origin': origins[(i-1) % len(origins)]} for i in range(1, size+1)]
        self.messages = [{'conversation_id': row['id'], 'id': row['id']*100 + index,
                          'external_message_id': str(index), 'text': 'Fixture',
                          'occurred_at': '2026-11-10T10:00:00Z', 'revision': 1}
                         for row in self.conversations for index in range(message_count, 0, -1)]
        self.jobs = [{'id': UUID(int=row['id']), 'message_id': row['id'], 'message_revision': 2,
                      'revision': 7, 'status': 'approved', 'result': {'sentiment': 'neutral'}}
                     for row in self.messages if self.conversations[row['conversation_id']-1]['origin'] == 'synthetic']
        self.analysis = [{'message_id': row['id'], 'sentiment': 'positive', 'confidence': 'low',
                          'explanation': 'Fixture'} for row in self.messages
                         if self.conversations[row['conversation_id']-1]['origin'] != 'synthetic']

    def execute(self, sql, params):
        self.queries.append((sql, params))
        if 'FROM socialmei.wa_bot_decisions' in sql:
            return Cursor(getattr(self, 'bot_replies', []))
        if 'FROM socialmei.me_conversations' in sql:
            return Cursor(self.conversations)
        if 'CROSS JOIN LATERAL' in sql:
            return Cursor(self.messages)
        if 'FROM socialmei.me_provider_sentiment_jobs' in sql:
            return Cursor(self.analysis)
        if 'FROM socialmei.me_jobs' in sql:
            return Cursor(self.jobs)
        raise AssertionError('Unexpected query')


class InboxQueryBudgetTests(unittest.TestCase):
    def read(self, connection, *, sentiment=True):
        with ExitStack() as stack:
            inbox_settings(stack, 17, sentiment=sentiment)
            stack.enter_context(patch.object(module, 'db', return_value=nullcontext(connection)))
            invalidation = stack.enter_context(patch.object(module, 'invalidate_expired'))
            result = module.conversations(None, Response())
            invalidation.assert_called_once_with(connection, 17)
            return result

    def test_five_reads_for_mixed_inbox_independent_of_conversation_or_message_count(self):
        for size in (3, 100):
            with self.subTest(conversations=size):
                connection = Connection(size, message_count=100 if size == 100 else 3)
                result = self.read(connection)
                self.assertEqual(len(connection.queries), 5)
                self.assertEqual(len(result['items']), size)
                for sql, params in connection.queries:
                    self.assertIn('workspace_id=%s', sql)
                    self.assertIn(17, params)
                sql, params = connection.queries[1]
                self.assertIn('LIMIT 100', sql)
                self.assertIn('ORDER BY occurred_at DESC,id DESC', sql)
                self.assertEqual(params, (list(range(1, size+1)), 17))
                for conversation in result['items']:
                    messages = conversation['messages']
                    self.assertEqual([row['id'] for row in messages], sorted(row['id'] for row in messages))
                    self.assertNotIn('conversation_id', messages[0])
                    if 'origin' not in conversation:
                        self.assertEqual(messages[0]['enrichment']['revision'], 7)
                        self.assertNotIn('provider_analysis', messages[0])
                    else:
                        self.assertIsNone(messages[0]['enrichment'])
                        self.assertEqual(messages[0]['provider_analysis']['source'], 'automation')
                provider_ids = connection.queries[2][1][1]
                job_ids = connection.queries[3][1][1]
                self.assertTrue(set(provider_ids).isdisjoint(job_ids))
                self.assertIn('DISTINCT ON (message_id)', connection.queries[3][0])
                self.assertIn('ORDER BY message_id,message_revision DESC,id DESC', connection.queries[3][0])

    def test_disabled_sentiment_does_not_query_provider_table_or_add_analysis(self):
        connection = Connection(100, origins=('instagram', 'waha'))
        result = self.read(connection, sentiment=False)
        self.assertEqual(len(connection.queries), 3)
        self.assertFalse(any('me_provider_sentiment_jobs' in sql for sql, _ in connection.queries))
        self.assertTrue(all('provider_analysis' not in message for row in result['items'] for message in row['messages']))

    def test_empty_inbox_does_not_query_messages_jobs_or_sentiment(self):
        connection = Connection(0)
        self.assertEqual(self.read(connection), {'workspace_id': 17, 'items': []})
        self.assertEqual(len(connection.queries), 1)

    def test_confirmed_menu_reply_appears_once_with_exact_text_and_receipt_time(self):
        connection = Connection(2, origins=('waha', 'instagram'))
        connection.bot_replies = [{'conversation_id': 1, 'id': UUID(int=123),
            'result': {'text': 'Menu de teste', 'choices': [{'id': '1', 'title': 'Produtos'}]},
            'provider_message_id': 'synthetic-receipt', 'finished_at': '2026-11-10T10:00:01Z'}]
        result = self.read(connection, sentiment=False)
        outgoing = [m for m in result['items'][0]['messages'] if m.get('direction') == 'outgoing']
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0]['text'], 'Menu de teste\n\n1 - Produtos')
        self.assertEqual(outgoing[0]['provider'], 'waha')
        self.assertEqual(outgoing[0]['occurred_at'], '2026-11-10T10:00:01Z')
        self.assertFalse(any(m.get('direction') == 'outgoing' for m in result['items'][1]['messages']))
        sql, params = connection.queries[-1]
        self.assertEqual(params, ([1], 17))
        self.assertIn("d.status='confirmed'", sql)
        self.assertIn('m.workspace_id=d.workspace_id', sql)
        self.assertIn('m.conversation_id=d.conversation_id', sql)
        self.assertIn('m.external_message_id=d.provider_message_id', sql)


DB = os.getenv('TEST_DATABASE_URL', '').strip()


@unittest.skipUnless(DB, 'TEST_DATABASE_URL not configured; disposable PostgreSQL required')
class InboxBatchPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB, autocommit=True) as conn:
            for migration in sorted((Path(__file__).resolve().parents[1] / 'database/migrations').glob('*.sql')):
                conn.execute(migration.read_text(), prepare=False)

    def setUp(self):
        self.workspaces = []
        with psycopg.connect(DB) as conn:
            for _ in range(2):
                self.workspaces.append(conn.execute('INSERT INTO socialmei.workspaces(slug,nome) VALUES(%s,%s) RETURNING id',
                                                   ('inbox-budget-' + uuid4().hex, 'Disposable fixture')).fetchone()[0])

    def tearDown(self):
        with psycopg.connect(DB) as conn:
            conn.execute('DELETE FROM socialmei.workspaces WHERE id=ANY(%s)', (self.workspaces,))

    def conversation(self, conn, workspace, index):
        conversation = conn.execute("INSERT INTO socialmei.me_conversations(workspace_id,channel,account_ref,contact_ref,contact_name) VALUES(%s,'whatsapp','synthetic:account',%s,'Fixture') RETURNING id",
                                    (workspace, 'synthetic:' + str(index))).fetchone()[0]
        messages = conn.execute("INSERT INTO socialmei.me_messages(workspace_id,conversation_id,external_message_id,fingerprint,conversation_revision,text,occurred_at) SELECT %s,%s,i::text,%s,i,'Fixture',TIMESTAMPTZ '2026-01-01T00:00:00Z'+(i/2)*INTERVAL '1 second' FROM generate_series(1,105) i RETURNING id",
                                (workspace, conversation, 'f'*64)).fetchall()
        return conversation, [row[0] for row in messages]

    def read(self, workspace):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'DATABASE_URL': DB}))
            inbox_settings(stack, workspace, sentiment=False)
            return module.conversations(None, Response())

    def test_lateral_limit_order_and_workspace_isolation(self):
        expected = {}
        with psycopg.connect(DB) as conn:
            for index in range(3):
                conversation, ids = self.conversation(conn, self.workspaces[0], index)
                expected[conversation] = ids[-100:]
            foreign_id, foreign_messages = self.conversation(conn, self.workspaces[1], 99)
        result = self.read(self.workspaces[0])
        self.assertEqual([row['id'] for row in result['items']], sorted(expected, reverse=True))
        for row in result['items']:
            self.assertEqual([message['id'] for message in row['messages']], expected[row['id']])
            self.assertNotIn(foreign_id, expected)
            self.assertTrue(set(expected[row['id']]).isdisjoint(foreign_messages))

    def test_latest_job_uses_message_revision_then_uuid_and_preserves_invalidation(self):
        with psycopg.connect(DB) as conn:
            conversation, ids = self.conversation(conn, self.workspaces[0], 1)
            for job_id, message_revision in ((UUID(int=3), 1), (UUID(int=1), 2), (UUID(int=2), 2)):
                conn.execute("INSERT INTO socialmei.me_jobs(id,workspace_id,message_id,message_revision,status) VALUES(%s,%s,%s,%s,'pending')",
                             (job_id, self.workspaces[0], ids[-1], message_revision))
            conn.execute("UPDATE socialmei.me_jobs SET expires_at=NOW()-INTERVAL '1 second' WHERE id=%s", (UUID(int=2),))
        rows = self.read(self.workspaces[0])['items'][0]['messages']
        job = rows[-1]['enrichment']
        self.assertEqual(job['id'], str(UUID(int=2)))
        self.assertEqual(job['status'], 'expired')
        self.assertEqual(job['suggested_reply'], '')
        self.assertTrue(all(row['enrichment'] is None for row in rows[:-1]))


if __name__ == '__main__':
    unittest.main()
