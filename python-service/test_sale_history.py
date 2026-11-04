"""Read-only sale operation history in disposable PostgreSQL, never production."""
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from app import app
import test_account_auth as accounts


class SaleHistoryGuards(unittest.TestCase):
    def test_missing_session_cannot_query_history_database(self):
        with patch.dict(os.environ, accounts.ENV), patch('sales_data.connect') as database:
            client = TestClient(app, base_url=accounts.ORIGIN)
            self.assertEqual(client.get('/api/v1/vendas/1/history').status_code, 401)
            database.assert_not_called()


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL not configured')
class SaleHistoryDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        response = self.admin_client.post('/api/v1/produtos', json={
            'nome':'Produto fictício', 'preco':59.9, 'estoque':5,
        })
        self.assertEqual(response.status_code,201,response.text)
        self.product = response.json()

    def sale(self):
        packet = {'operation_id':str(uuid4()), 'produto_id':self.product['id'],
                  'quantidade':1, 'preco':'59.90', 'data':'2026-11-04',
                  'observacao':'PRIVATE_NOTE_NEVER_RETURN'}
        response = self.admin_client.post('/api/v1/vendas',json=packet)
        self.assertEqual(response.status_code,201,response.text)
        return response.json(), packet

    def action(self, sale, name):
        response = self.admin_client.post('/api/v1/vendas/'+str(sale['id'])+'/'+name,
            json={'operation_id':str(uuid4()),'expected_version':sale['versao']})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def history(self, sale, suffix='', client=None):
        response = (client or self.admin_client).get('/api/v1/vendas/'+str(sale['id'])+'/history'+suffix)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')
        return response.json()

    def test_actual_versions_persist_without_notes_actor_or_inferred_stock_delta(self):
        sale, packet = self.sale()
        response = self.admin_client.patch('/api/v1/vendas/'+str(sale['id']),json={
            **packet,'operation_id':str(uuid4()),'expected_version':sale['versao'],
            'quantidade':2,'cliente_id':None,
        })
        self.assertEqual(response.status_code,200,response.text)
        sale = self.action(response.json(),'pagar')
        sale = self.action(sale,'cancelar')
        sale = self.action(sale,'excluir')
        self.assertEqual(self.admin_client.get('/api/v1/vendas/'+str(sale['id'])).status_code,404)
        value = self.history(sale)
        self.assertTrue(value['deleted'])
        self.assertFalse(value['actor_recorded'])
        self.assertEqual([row['revision'] for row in value['items']],[5,4,3,2,1])
        self.assertEqual([row['stock_applied'] for row in value['items']],[False,False,True,True,True])
        self.assertEqual(value['items'][0]['total'],'119.80')
        self.assertEqual(value['items'][-1]['total'],'59.90')
        self.assertTrue(value['items'][0]['deleted'])
        raw = json.dumps(value)
        for field in ('PRIVATE_NOTE_NEVER_RETURN','observacao','cliente','item','stock_delta','actor_id'):
            self.assertNotIn('"'+field+'"' if field in ('cliente','item') else field,raw)
        self.assertEqual(self.admin_client.get('/api/v1/produtos/'+str(self.product['id'])).json()['estoque'],5)

    def test_replay_and_equal_timestamp_keyset_pagination_have_no_duplicates(self):
        sale, packet = self.sale()
        self.assertEqual(self.admin_client.post('/api/v1/vendas',json=packet).status_code,201)
        sale = self.action(sale,'pagar')
        for _ in range(5):
            sale = self.action(sale,'pagar')
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.crm_venda_operacoes SET criado_em='2026-11-04T12:00:00Z' WHERE workspace_id=%s",
                         (self.admin_client.identity['negocio']['id'],))
        found, cursor = [], None
        for _ in range(5):
            value = self.history(sale,'?limit=2'+('&before='+cursor if cursor else ''))
            self.assertLessEqual(len(value['items']),2)
            found.extend(row['id'] for row in value['items'])
            cursor = value['next_cursor']
            if cursor is None:
                break
        self.assertIsNone(cursor)
        self.assertEqual(len(found),7)
        self.assertEqual(len(set(found)),7)
        self.assertEqual(self.admin_client.get('/api/v1/produtos/'+str(self.product['id'])).json()['estoque'],4)

    def test_foreign_sale_cursor_roles_revocation_and_bounds_fail_closed(self):
        sale, _ = self.sale()
        foreign = self.register('foreign-history@example.test')
        endpoint = '/api/v1/vendas/'+str(sale['id'])+'/history'
        self.assertEqual(foreign.get(endpoint).status_code,404)
        for suffix in ('?limit=0','?limit=51','?before=invalid'):
            self.assertEqual(self.admin_client.get(endpoint+suffix).status_code,422)
        self.assertEqual(self.admin_client.get(endpoint+'?before='+str(uuid4())).status_code,404)
        for role in ('owner','admin','member','viewer'):
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s',(role,self.admin_id))
            self.assertEqual(self.admin_client.get(endpoint).status_code,200)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='report_viewer' WHERE user_id=%s",(self.admin_id,))
        self.assertEqual(self.admin_client.get(endpoint).status_code,403)
        self.assertEqual(self.admin_client.post('/api/v1/auth/logout',json={}).status_code,204)
        self.assertEqual(self.admin_client.get(endpoint).status_code,401)

    def test_empty_legacy_history_timezone_and_failures_are_explicit(self):
        sale, _ = self.sale()
        with patch.dict(os.environ,{'TZ':'America/Fortaleza'}):
            self.assertEqual(self.history(sale)['timezone'],'America/Fortaleza')
        with patch('sales_data.connect',side_effect=psycopg.OperationalError('private-db-detail')):
            response = self.admin_client.get('/api/v1/vendas/'+str(sale['id'])+'/history')
            self.assertEqual(response.status_code,503)
            self.assertNotIn('private-db-detail',response.text)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.crm_venda_operacoes SET resposta='{}' WHERE workspace_id=%s",
                         (self.admin_client.identity['negocio']['id'],))
        # Entries with no sale ID are not attributed to a different sale by guessing.
        self.assertEqual(self.history(sale)['items'],[])
        self.assertFalse(self.history(sale)['actor_recorded'])
        with psycopg.connect(accounts.DB) as conn:
            conn.execute('UPDATE socialmei.crm_venda_operacoes SET resposta=%s::jsonb WHERE workspace_id=%s',
                         (json.dumps({'id':sale['id'],'observacao':'PRIVATE_CORRUPT_SNAPSHOT'}),
                          self.admin_client.identity['negocio']['id']))
        response = self.admin_client.get('/api/v1/vendas/'+str(sale['id'])+'/history')
        self.assertEqual(response.status_code,503)
        self.assertNotIn('PRIVATE_CORRUPT_SNAPSHOT',response.text)


if __name__ == '__main__':
    unittest.main()
