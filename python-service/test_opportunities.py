"""Commercial outcomes remain independent of payments and qualitative interest."""
import unittest
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4
from unittest.mock import patch

from opportunities import Create, Edit, Close, Reopen, SaleLink, guard, transition
from fastapi import HTTPException
import psycopg
from fastapi.testclient import TestClient
from account_auth import COOKIE, csrf
from app import app
from opportunities import mutate

DB = os.getenv('TEST_DATABASE_URL', '').strip()
ORIGIN = 'https://app.example.com'
ENV = {'SOCIALMEI_AUTH_ENABLED': 'true', 'SOCIALMEI_SHARED_DATA_ENABLED': 'true', 'SOCIALMEI_AUTH_ORIGIN': ORIGIN}


class ContractTests(unittest.TestCase):
    def test_strict_fields_and_terminal_reasons(self):
        base = {'operation_id': str(uuid4()), 'client_id': 1, 'title': 'Orçamento', 'interest_level': 'hot'}
        self.assertEqual(Create.model_validate(base).interest_level, 'hot')
        for change in [{'client_id': True}, {'workspace_id': 2}, {'interest_level': 'won'}, {'title': ' '}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                Create.model_validate({**base, **change})
        for outcome, reason in [('won', 'price'), ('lost', 'sale_completed'), ('lost', 'unknown')]:
            with self.assertRaises(ValueError):
                Close(operation_id=uuid4(), expected_revision=1, outcome=outcome, reason=reason)
        Close(operation_id=uuid4(), expected_revision=1, outcome='won', reason='sale_completed')
        with self.assertRaises(ValueError):
            Edit(operation_id=uuid4(), expected_revision=1)
        with self.assertRaises(ValueError):
            Reopen(operation_id=uuid4(), expected_revision=1, reason=' ')
        with self.assertRaises(ValueError):
            SaleLink(operation_id=uuid4(), expected_revision=1, sale_id=True)

    def test_interest_and_outcome_are_independent(self):
        transition('open', 'close')
        transition('won', 'reopen')
        transition('lost', 'reopen')
        transition('won', 'sale')
        for status, action in [('won', 'close'), ('lost', 'edit'), ('open', 'reopen')]:
            with self.subTest(status=status, action=action), self.assertRaises(HTTPException) as error:
                transition(status, action)
            self.assertEqual(error.exception.status_code, 409)

    def test_role_and_auth_boundary_before_database(self):
        with patch('opportunities.require_enabled'), patch('opportunities.require_shared_data'), patch('opportunities.current', return_value={'role': 'viewer', 'workspace_id': 7}):
            self.assertEqual(guard()['workspace_id'], 7)
            with self.assertRaises(HTTPException) as error:
                guard(True)
            self.assertEqual(error.exception.status_code, 403)

    def test_http_auth_csrf_and_private_validation(self):
        with patch.dict(os.environ, ENV), patch('account_auth.session_identity', return_value={'id': 1, 'workspace_id': 1, 'role': 'viewer'}), patch('opportunities.connect', side_effect=AssertionError('DB accessed')):
            client = TestClient(app, base_url=ORIGIN)
            with patch('account_auth.session_identity', return_value=None):
                self.assertEqual(client.get('/api/v1/opportunities').status_code, 401)
            token = 'a' * 64
            client.cookies.set(COOKIE, token)
            data = {'operation_id': str(uuid4()), 'client_id': 1, 'title': 'Fictício'}
            self.assertEqual(client.post('/api/v1/opportunities', json=data, headers={'Origin': ORIGIN}).status_code, 403)
            headers = {'Origin': ORIGIN, 'X-SocialMEI-CSRF': csrf(token)}
            self.assertEqual(client.post('/api/v1/opportunities', json=data, headers=headers).status_code, 403)
        with patch.dict(os.environ, ENV), patch('account_auth.session_identity', return_value={'id': 1, 'workspace_id': 1, 'role': 'member'}):
            response = client.post('/api/v1/opportunities', json={**data, 'client_id': 'sensitive-input'}, headers=headers)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn('sensitive-input', response.text)


@unittest.skipUnless(DB, 'Postgres test database not configured')
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB, autocommit=True) as conn:
            for file in sorted((Path(__file__).resolve().parents[1] / 'database/migrations').glob('*.sql')):
                conn.execute(file.read_text(), prepare=False)

    def setUp(self):
        self.environment = patch.dict(os.environ, {**ENV, 'DATABASE_URL': DB})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.users = []
        self.clients = []
        with psycopg.connect(DB) as conn:
            for _ in range(2):
                marker = uuid4().hex
                wid = conn.execute('INSERT INTO socialmei.workspaces(slug,nome) VALUES (%s,%s) RETURNING id', ('opp-' + marker, 'Fictício')).fetchone()[0]
                uid = conn.execute('INSERT INTO socialmei.users(email,nome) VALUES (%s,%s) RETURNING id', (marker + '@example.test', 'Fictício')).fetchone()[0]
                conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES (%s,%s,'owner')", (wid, uid))
                cid = conn.execute('INSERT INTO socialmei.crm_clientes(workspace_id,nome) VALUES (%s,%s) RETURNING id', (wid, 'Cliente fictício')).fetchone()[0]
                self.users.append({'id': uid, 'workspace_id': wid, 'role': 'owner'})
                self.clients.append(cid)
        self.identity = self.users[0]
        auth = patch('opportunities.current', side_effect=lambda: self.identity)
        auth.start()
        self.addCleanup(auth.stop)

    def tearDown(self):
        with psycopg.connect(DB) as conn:
            for user in self.users:
                conn.execute('DELETE FROM socialmei.workspaces WHERE id=%s', (user['workspace_id'],))
                conn.execute('DELETE FROM socialmei.users WHERE id=%s', (user['id'],))

    def create(self):
        return mutate('create', Create(operation_id=uuid4(), client_id=self.clients[0], title='Orçamento', interest_level='hot'))

    def test_customer_deletion_preserves_commercial_history_with_clear_conflict(self):
        row = self.create()
        mutate('close', Close(operation_id=uuid4(), expected_revision=1, outcome='won', reason='sale_completed'), UUID(row['id']))
        from shared_data import delete_cliente
        with patch('shared_data.ensure_workspace', return_value=self.identity['workspace_id']):
            with self.assertRaises(HTTPException) as error:
                delete_cliente(self.clients[0], None)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn('oportunidades', error.exception.detail)
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.crm_opportunity_events WHERE workspace_id=%s', (self.identity['workspace_id'],)).fetchone()[0], 2)

    def test_lifecycle_replay_cas_history_and_tenant(self):
        row = self.create()
        close = Close(operation_id=uuid4(), expected_revision=1, outcome='lost', reason='price', note='Fictício')
        closed = mutate('close', close, UUID(row['id']))
        self.assertEqual((closed['interest_level'], closed['outcome']), ('hot', 'lost'))
        reopened = mutate('reopen', Reopen(operation_id=uuid4(), expected_revision=2, reason='Novo contato'), UUID(row['id']))
        self.assertEqual(mutate('close', close, UUID(row['id']))['revision'], reopened['revision'])
        with self.assertRaises(HTTPException) as error:
            mutate('edit', Edit(operation_id=uuid4(), expected_revision=1, title='Conflito'), UUID(row['id']))
        self.assertEqual(error.exception.status_code, 409)
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.crm_opportunity_events WHERE workspace_id=%s', (self.identity['workspace_id'],)).fetchone()[0], 3)
        self.identity = self.users[1]
        with self.assertRaises(HTTPException) as error:
            mutate('edit', Edit(operation_id=uuid4(), expected_revision=3, title='Outro negócio'), UUID(row['id']))
        self.assertEqual(error.exception.status_code, 404)

    def test_concurrent_operation_is_once_and_conflicting_reuse_rejected(self):
        payload = Create(operation_id=uuid4(), client_id=self.clients[0], title='Mesmo envio')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: mutate('create', payload), range(2)))
        self.assertEqual(results[0]['id'], results[1]['id'])
        with self.assertRaises(HTTPException) as error:
            mutate('create', payload.model_copy(update={'title': 'Outro conteúdo'}))
        self.assertEqual(error.exception.status_code, 409)

    def test_sale_link_never_changes_stock_payment_or_creates_sales(self):
        row = self.create()
        wid = self.identity['workspace_id']
        with psycopg.connect(DB) as conn:
            pid = conn.execute("INSERT INTO socialmei.crm_produtos(workspace_id,nome,tipo,preco,estoque,minimo) VALUES (%s,'Produto fictício','Produto',10,5,0) RETURNING id", (wid,)).fetchone()[0]
            sid = conn.execute("INSERT INTO socialmei.crm_vendas(workspace_id,cliente_id,produto_id,cliente,item,tipo_item,data,quantidade,preco,valor,pagamento,status) VALUES (%s,%s,%s,'Cliente fictício','Produto fictício','Produto',CURRENT_DATE,1,10,10,'Pix','Pendente') RETURNING id", (wid, self.clients[0], pid)).fetchone()[0]
            original = conn.execute('SELECT row_to_json(s) FROM socialmei.crm_vendas s WHERE id=%s', (sid,)).fetchone()[0]
        linked = mutate('sale', SaleLink(operation_id=uuid4(), expected_revision=1, sale_id=sid), UUID(row['id']))
        self.assertEqual((linked['outcome'], linked['sale_status']), ('open', 'Pendente'))
        other = self.create()
        with self.assertRaises(HTTPException) as error:
            mutate('sale', SaleLink(operation_id=uuid4(), expected_revision=1, sale_id=sid), UUID(other['id']))
        self.assertEqual(error.exception.status_code, 409)
        with psycopg.connect(DB) as conn:
            self.assertEqual(conn.execute('SELECT row_to_json(s) FROM socialmei.crm_vendas s WHERE id=%s', (sid,)).fetchone()[0], original)
            self.assertEqual(conn.execute('SELECT estoque FROM socialmei.crm_produtos WHERE id=%s', (pid,)).fetchone()[0], 5)
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.crm_vendas WHERE workspace_id=%s', (wid,)).fetchone()[0], 1)
            conn.execute("UPDATE socialmei.crm_vendas SET status='Cancelado',excluida=true WHERE id=%s", (sid,))
        from opportunities import record, transaction
        with transaction() as cursor:
            current_row = record(cursor, wid, UUID(row['id']))
        self.assertTrue(current_row['sale_unavailable'])
        self.assertEqual(current_row['outcome'], 'open')


if __name__ == '__main__':
    unittest.main()
