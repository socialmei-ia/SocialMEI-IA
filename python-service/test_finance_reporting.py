from datetime import date
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient
import test_account_auth as accounts
from finance_reporting import finance


class FinanceReportContracts(unittest.TestCase):
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
