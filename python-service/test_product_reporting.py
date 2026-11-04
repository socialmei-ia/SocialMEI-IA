import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
import test_account_auth as accounts


class ProductReportContracts(unittest.TestCase):
    def test_missing_session_never_queries_catalogue(self):
        with patch.dict(os.environ, accounts.ENV), patch('product_reporting.connect', side_effect=AssertionError('database')):
            self.assertEqual(TestClient(accounts.app, base_url=accounts.ORIGIN).get('/api/v1/reporting/products').status_code, 401)


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class ProductReportDatabase(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.low = self.product('Produto baixo', 1, 2)
        self.unsold = self.product('Produto sem venda', 10, 0)
        self.cancelled = self.product('Somente cancelada', 10, 0)
        self.product('Inativo', 0, 2, status='Inativo')
        response = self.admin_client.post('/api/v1/produtos', json={'nome': 'Serviço sem estoque', 'tipo': 'Serviço', 'preco': '80.00', 'duracao_minutos': 30})
        self.assertEqual(response.status_code, 201, response.text)
        self.sale(self.low, '2026-11-01')
        self.sale(self.unsold, '2026-10-31')
        sale = self.sale(self.cancelled, '2026-11-01')
        response = self.admin_client.post('/api/v1/vendas/'+str(sale['id'])+'/cancelar', json={'operation_id': str(uuid4()), 'expected_version': sale['versao']})
        self.assertEqual(response.status_code, 200, response.text)

    def product(self, name, stock, minimum, status='Ativo'):
        response = self.admin_client.post('/api/v1/produtos', json={'nome': name, 'preco': '59.90', 'estoque': stock, 'minimo': minimum, 'status': status})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def sale(self, product, day):
        response = self.admin_client.post('/api/v1/vendas', json={'operation_id': str(uuid4()), 'produto_id': product, 'data': day, 'preco': '59.90', 'quantidade': 1})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def report(self, client=None, extra=''):
        return (client or self.admin_client).get('/api/v1/reporting/products?start=2026-11-01&end=2026-11-30'+extra)

    def test_current_stock_and_no_sales_period_have_distinct_meanings(self):
        response = self.report()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['totals'], {'active_products': 3, 'low_stock': 1, 'no_sales': 2})
        self.assertEqual([p['id'] for p in data['products']], [self.low])
        self.assertEqual(data['products'][0]['stock'], 0)
        self.assertEqual(data['products'][0]['price'], '59.90')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertNotIn('custo', response.text)
        self.assertNotIn('descricao', response.text)

    def test_keyset_pagination_and_validation(self):
        first = self.report(extra='&kind=no_sales&limit=1').json()
        self.assertEqual(first['products'][0]['id'], self.unsold)
        self.assertEqual(first['next_after'], self.unsold)
        last = self.report(extra=f'&kind=no_sales&limit=1&after={first["next_after"]}').json()
        self.assertEqual(last['products'][0]['id'], self.cancelled)
        self.assertIsNone(last['next_after'])
        for query in ['&limit=51', '&after=-1', '&kind=unknown', '&end=2025-11-01']:
            self.assertEqual(self.report(extra=query).status_code, 422)

    def test_workspace_permissions_and_revocation(self):
        other = self.register('product-report-other@example.test')
        self.assertEqual(self.report(other).json()['totals']['active_products'], 0)
        self.assertEqual(self.report(other, '&after='+str(self.low)).json()['products'], [])
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='report_viewer' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(self.report().status_code, 200)
        self.assertEqual(self.admin_client.get('/api/v1/produtos').status_code, 403)
        self.admin_client.post('/api/v1/auth/logout', json={})
        self.assertEqual(self.report().status_code, 401)

    def test_error_details_are_private(self):
        with patch('product_reporting.connect', side_effect=psycopg.OperationalError('private host')):
            response = self.report()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private host', response.text)


if __name__ == '__main__':
    unittest.main()
