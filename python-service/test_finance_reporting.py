from datetime import date, datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient
import test_account_auth as accounts
from finance_reporting import finance, mei_limit


class FinanceReportContracts(unittest.TestCase):
    def test_mei_limit_from_opening_month_and_unverified_later_year(self):
        self.assertEqual(str(mei_limit(2026, date(2026, 12, 31))), "6750.00")
        self.assertEqual(str(mei_limit(2026, date(2025, 12, 31))), "81000.00")
        self.assertIsNone(mei_limit(2027, date(2026, 1, 1)))

    def test_invalid_dates_and_missing_session_fail_before_database(self):
        with patch('finance_reporting.scope', return_value=1), patch('finance_reporting.connect', side_effect=AssertionError('database')):
            for start, end in [(date(2026, 11, 1), None), (date(2026, 11, 2), date(2026, 11, 1)), (date.min, date.min)]:
                with self.assertRaises(HTTPException) as error:
                    finance(start, end)
                self.assertEqual(error.exception.status_code, 422)
        with patch.dict(os.environ, accounts.ENV), patch('finance_reporting.connect', side_effect=AssertionError('database')):
            self.assertEqual(TestClient(accounts.app, base_url=accounts.ORIGIN).get('/api/v1/reporting/finance').status_code, 401)


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class FinanceReportDatabase(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.entry('receita', '0.10', '2026-12-01', '2026-11-01')
        self.entry('receita', '0.20', '2026-12-01', '2026-11-02')
        self.entry('despesa', '0.40', '2026-12-01', '2026-11-03')
        self.entry('receita', '2.00', '2026-11-01', '2026-10-31')
        self.entry('receita', '3.00', '2026-11-01')
        self.entry('despesa', '4.00', '2026-11-01')
        self.entry('receita', '99.00', '2026-11-01', '2026-11-01', excluded=True)
        self.entry('despesa', '88.00', '2026-11-01', undated=True)

    def entry(self, kind, amount, due, paid=None, excluded=False, undated=False):
        response = self.admin_client.post('/api/v1/financeiro', json={
            'operation_id': str(uuid4()), 'descricao': 'Registro fictício privado',
            'tipo': kind, 'valor': amount, 'vencimento': due,
            'status': 'pago' if paid or undated else 'aberto',
        })
        self.assertEqual(response.status_code, 201, response.text)
        if paid or undated or excluded:
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.crm_financeiro SET data_pagamento=%s, excluida=%s WHERE id=%s', (paid, excluded, response.json()['id']))
        return response.json()

    def report(self, client=None):
        return (client or self.admin_client).get('/api/v1/reporting/finance?start=2026-11-01&end=2026-11-30')

    def test_paid_date_precision_previous_period_and_pending_are_distinct(self):
        response = self.report()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['paid'], {'count': 3, 'incoming': '0.30', 'outgoing': '0.40', 'balance': '-0.10'})
        self.assertEqual(data['previous']['balance'], '2.00')
        self.assertEqual(data['balance_change'], '-2.10')
        self.assertEqual(data['pending'], {'count': 2, 'incoming': '3.00', 'outgoing': '4.00'})
        self.assertEqual(data['undated_paid_count'], 1)
        self.assertEqual(len(data['daily']), 30)
        self.assertEqual(data['daily'][2]['balance'], '-0.40')
        self.assertEqual(data['daily'][3]['balance'], '0.00')
        self.assertNotIn('Registro fictício privado', response.text)
        self.assertNotIn('cliente_id', response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_legacy_open_and_overdue_are_included_without_paid_or_excluded(self):
        legacy = self.entry('despesa', '5.00', '2026-11-09')
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.crm_financeiro SET status='atrasado' WHERE id=%s", (legacy['id'],))
        response = self.report()
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['pending'], {'count': 3, 'incoming': '3.00', 'outgoing': '9.00'})
        overdue = data['overdue']
        if date.fromisoformat(overdue['as_of']) > date(2026, 11, 9):
            self.assertEqual(overdue['count'], 3)
            self.assertEqual((overdue['incoming'], overdue['outgoing']), ('3.00', '9.00'))
        else:
            self.assertNotEqual(overdue['outgoing'], '9.00')

    def test_workspace_report_only_and_revocation(self):
        other = self.register('finance-report-other@example.test')
        result = self.report(other).json()
        self.assertEqual(result['paid']['count'], 0)
        self.assertEqual(result['pending']['count'], 0)
        self.assertEqual(result['undated_paid_count'], 0)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='report_viewer' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(self.report().status_code, 200)
        self.assertEqual(self.admin_client.get('/api/v1/financeiro').status_code, 403)
        self.admin_client.post('/api/v1/auth/logout', json={})
        self.assertEqual(self.report().status_code, 401)

    def test_mei_history_replaces_overlapping_sales_and_versions_writes(self):
        path = '/api/v1/reporting/mei'
        workspace = self.admin_client.identity['negocio']['id']
        with psycopg.connect(accounts.DB) as conn:
            for day, value, state in [
                ('2026-06-04', 23, 'Pago'),
                ('2026-07-01', 42, 'Pendente'),
                ('2026-07-03', 10, 'Cancelado'),
                ('2027-01-01', 100, 'Pago'),
            ]:
                conn.execute(
                    "INSERT INTO socialmei.crm_vendas(workspace_id,cliente,item,data,valor,status,quantidade,pagamento,preco) "
                    "VALUES(%s,'Fixture','Fixture',%s,%s,%s,1,'Pix',%s)",
                    (workspace, day, value, state, value),
                )
        payload = {
            'operation_id': str(uuid4()), 'expected_revision': 0,
            'opened_on': '2026-06-02', 'prior_through': '2026-06-30',
            'prior_amount': '100.00', 'source_note': 'Consolidado sintético',
        }
        with patch('finance_reporting.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 27, tzinfo=timezone.utc)
            self.assertEqual(self.admin_client.post(path, json=payload).json(), {'revision': 1})
            self.assertEqual(self.admin_client.post(path, json=payload).json(), {'revision': 1})
            self.assertEqual(self.admin_client.post(path, json={**payload, 'prior_amount': '101'}).status_code, 409)
            self.assertEqual(self.admin_client.post(path, json={**payload, 'operation_id': str(uuid4())}).status_code, 409)
            report = self.admin_client.get(path).json()
            self.assertEqual((report['system_sales'], report['system_sales_used'], report['estimate']), ('65.00', '42.00', '142.00'))
            self.assertEqual(report['limit'], '47250.00')
            other = self.register('mei-m09-other@example.test')
            self.assertEqual(other.get(path).json()['revision'], 0)
            with psycopg.connect(accounts.DB) as conn:
                conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE user_id=%s", (self.admin_id,))
            self.assertEqual(self.admin_client.get(path).status_code, 200)
            self.assertEqual(self.admin_client.post(path, json=payload).status_code, 403)

    def test_categories_persist_and_report_by_payment_date(self):
        path = '/api/v1/financeiro'
        payload = {
            'operation_id': str(uuid4()), 'descricao': 'Fixture',
            'tipo': 'despesa', 'valor': '12.00', 'vencimento': '2026-12-10',
            'categoria': 'Material',
        }
        created = self.admin_client.post(path, json=payload)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(self.admin_client.post(path, json=payload).json(), created.json())
        entry_path = f"{path}/{created.json()['id']}"
        changed = self.admin_client.patch(entry_path, json={
            **{key: payload[key] for key in ('descricao', 'tipo', 'valor', 'vencimento')},
            'operation_id': str(uuid4()), 'expected_version': 1,
        })
        self.assertEqual(changed.json()['categoria'], 'Material')
        with patch('finance_data.payment_date', return_value=date(2026, 11, 6)):
            paid = self.admin_client.post(entry_path+'/pagar', json={
                'operation_id': str(uuid4()), 'expected_version': 2,
            })
        self.assertEqual(paid.status_code, 200, paid.text)
        categories = self.report().json()['categories']
        self.assertIn({'category': 'Material', 'kind': 'despesa', 'total': '12.00', 'count': 1}, categories)
        other = self.register('finance-category-other@example.test')
        self.assertEqual(self.report(other).json()['categories'], [])

    def test_partial_cash_completion_correction_and_isolation(self):
        entry = self.entry('receita', '50.00', '2026-11-01')
        path = f"/api/v1/financeiro/{entry['id']}"
        payload = {'operation_id': str(uuid4()), 'expected_version': 1, 'valor': '18.15', 'data': '2026-11-07'}
        with patch('finance_data.payment_date', return_value=date(2026, 11, 28)):
            def send(_):
                return self.admin_client.post(path+'/liquidacoes', json=payload)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(send, range(2)))
            self.assertTrue(all(response.status_code == 200 for response in results), results[0].text)
            self.assertEqual(results[0].json(), results[1].json())
            self.assertEqual(results[0].json()['liquidado_parcial'], '18.15')
            self.assertEqual(self.admin_client.post(path+'/liquidacoes', json={
                **payload, 'operation_id': str(uuid4()), 'expected_version': 2, 'valor': '32',
            }).status_code, 409)
            report = self.report().json()
            self.assertEqual(report['pending']['incoming'], '34.85')
            self.assertEqual(report['paid']['incoming'], '18.45')
            self.assertEqual(self.admin_client.post(path+'/excluir', json={
                'operation_id': str(uuid4()), 'expected_version': 2,
            }).status_code, 409)
            completion = self.admin_client.post(path+'/pagar', json={
                'operation_id': str(uuid4()), 'expected_version': 2,
            })
        self.assertEqual(completion.json()['status'], 'pago', completion.text)
        self.assertEqual(self.report().json()['paid']['incoming'], '50.30')
        correction = {'operation_id': str(uuid4()), 'expected_version': 3,
                      'parcela_id': payload['operation_id'], 'motivo': 'Data lançada incorretamente'}
        reversed_item = self.admin_client.post(path+'/estornar-parcela', json=correction)
        self.assertEqual(reversed_item.status_code, 200, reversed_item.text)
        self.assertEqual(reversed_item.json()['liquidado_parcial'], '31.85')
        self.assertEqual(self.admin_client.post(path+'/estornar-parcela', json=correction).json(), reversed_item.json())
        self.assertEqual(self.report().json()['paid']['incoming'], '32.15')
        self.assertEqual(len(self.admin_client.get(path+'/liquidacoes').json()['items']), 2)
        other = self.register('partial-settlement-other@example.test')
        self.assertEqual(other.get(path+'/liquidacoes').status_code, 404)
        self.assertEqual(other.post(path+'/estornar-parcela', json=correction).status_code, 404)

    def test_linked_sale_has_one_receivable_and_only_finance_moves_cash(self):
        workspace = self.admin_client.identity['negocio']['id']
        with psycopg.connect(accounts.DB) as conn:
            sale = conn.execute(
                "INSERT INTO socialmei.crm_vendas(workspace_id,cliente,item,data,valor,status,quantidade,pagamento,preco) "
                "VALUES(%s,'Fixture','Item',CURRENT_DATE,35,'Pendente',1,'Pix',35) RETURNING id",
                (workspace,),
            ).fetchone()[0]
        link = f'/api/v1/financeiro/de-venda/{sale}'
        sale_path = f'/api/v1/vendas/{sale}'
        payload = {'operation_id': str(uuid4()), 'expected_version': 1, 'vencimento': '2026-11-30'}
        response = self.admin_client.post(link, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.admin_client.post(link, json=payload).json(), response.json())
        path = f"/api/v1/financeiro/{response.json()['id']}"
        self.assertEqual(self.admin_client.post(link, json={**payload, 'operation_id': str(uuid4())}).status_code, 409)
        self.assertEqual(self.admin_client.post(sale_path+'/pagar', json={
            'operation_id': str(uuid4()), 'expected_version': 1,
        }).status_code, 409)
        operation = str(uuid4())
        with patch('finance_data.payment_date', return_value=date(2026, 11, 10)):
            receipt = self.admin_client.post(path+'/pagar', json={'operation_id': operation, 'expected_version': 1})
        self.assertEqual(receipt.status_code, 200, receipt.text)
        self.assertEqual(self.report().json()['paid']['incoming'], '35.30')
        self.assertEqual(self.admin_client.get(sale_path).json()['status'], 'Pago')
        reversal = self.admin_client.post(path+'/estornar-parcela', json={
            'operation_id': str(uuid4()), 'expected_version': 2,
            'parcela_id': operation, 'motivo': 'Quitação digitada em duplicidade',
        })
        self.assertEqual(reversal.status_code, 200, reversal.text)
        self.assertEqual(self.admin_client.get(sale_path).json()['status'], 'Pendente')
        self.assertEqual(self.report().json()['paid']['incoming'], '0.30')
        other = self.register('linked-sale-other@example.test')
        self.assertEqual(other.post(link, json=payload).status_code, 404)

    def test_das_declaration_has_revisions_replay_permissions_and_no_cash_effect(self):
        path = '/api/v1/reporting/mei/das'
        receipt = {'operation_id': str(uuid4()), 'expected_revision': 0,
                   'competencia': '2026-10-01', 'pago_em': '2026-11-01',
                   'valor': '85.68', 'referencia': 'Recibo fictício'}
        with patch('finance_reporting.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 27, tzinfo=timezone.utc)
            stored = self.admin_client.post(path, json=receipt)
            self.assertEqual(stored.status_code, 200, stored.text)
            self.assertEqual(self.admin_client.post(path, json=receipt).json(), {'revision': 1})
            self.assertEqual(self.admin_client.post(path, json={
                **receipt, 'operation_id': str(uuid4()),
            }).status_code, 409)
            self.assertEqual(self.admin_client.get(path).json()['items'][0]['valor'], '85.68')
            revocation = self.admin_client.post(path, json={
                **receipt, 'operation_id': str(uuid4()), 'expected_revision': 1,
                'pago_em': None, 'valor': None, 'referencia': 'Recibo de outra competência',
            })
            self.assertEqual(revocation.status_code, 200, revocation.text)
            history = self.admin_client.get(path+'?competencia=2026-10-01').json()['items']
            self.assertEqual([row['valor'] for row in history], [None, '85.68'])
            self.assertEqual(self.report().json()['paid']['outgoing'], '0.40')
            other = self.register('das-other@example.test')
            self.assertEqual(other.get(path).json()['items'], [])
            with psycopg.connect(accounts.DB) as conn:
                conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE user_id=%s", (self.admin_id,))
            self.assertEqual(self.admin_client.get(path).status_code, 200)
            self.assertEqual(self.admin_client.post(path, json=receipt).status_code, 403)

    def test_database_and_timezone_failures_do_not_expose_details(self):
        with patch('finance_reporting.connect', side_effect=psycopg.OperationalError('private connection')):
            response = self.report()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private connection', response.text)
        with patch('finance_reporting.settings.business_timezone', side_effect=ValueError('private zone')):
            response = self.report()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private zone', response.text)


if __name__ == '__main__':
    unittest.main()
