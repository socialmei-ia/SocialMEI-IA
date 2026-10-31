"""Real accounts, current-period aggregates and revocable report-only memberships."""
import os
import unittest
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from account_auth import COOKIE
import test_account_auth as accounts
import settings
import workspace_reporting
from fastapi import HTTPException


class ReportingTimezoneTests(unittest.TestCase):
    def test_invalid_timezone_does_not_run_a_report_in_server_timezone(self):
        with patch.dict(os.environ, {'TZ': 'invalid-business-timezone'}), patch(
            'workspace_reporting.scope', return_value=1
        ), patch('workspace_reporting.connect', side_effect=AssertionError('No database')):
            with self.assertRaises(HTTPException) as error:
                workspace_reporting.summary(30)
        self.assertEqual(error.exception.status_code, 503)


@unittest.skipUnless(accounts.DB,'Disposable PostgreSQL required')
class ReportDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp=accounts.AccountDatabaseTests.setUp
    login=accounts.AccountDatabaseTests.login
    invited=accounts.AccountDatabaseTests.invited
    register=accounts.AccountDatabaseTests.register

    def seed(self, workspace, amount):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("SELECT set_config('TimeZone', %s, true)", (settings.business_timezone().key,))
            for days in (-1,0,29,30):
                conn.execute("INSERT INTO socialmei.crm_vendas(workspace_id,cliente,item,data,quantidade,preco,valor,pagamento,status) VALUES(%s,'Private customer','Synthetic item',CURRENT_DATE-%s,1,%s,%s,'Pix','Pago')",(workspace,days,amount,amount))
                conn.execute("INSERT INTO socialmei.crm_financeiro(workspace_id,descricao,tipo,valor,vencimento,status) VALUES(%s,'Private finance','receita',%s,CURRENT_DATE-%s,'pago')",(workspace,amount,days))

    def test_reporting_date_and_period_use_the_business_timezone(self):
        for index, zone in enumerate(('Pacific/Kiritimati', 'Pacific/Pago_Pago')):
            with self.subTest(zone=zone), patch.dict(os.environ, {'TZ': zone}):
                owner = self.register(f'timezone-report-{index}@example.test')
                self.seed(owner.identity['negocio']['id'], 10)
                with psycopg.connect(accounts.DB) as conn:
                    expected = conn.execute(
                        "SELECT (CURRENT_TIMESTAMP AT TIME ZONE %s)::date",
                        (zone,),
                    ).fetchone()[0]
                report = owner.get('/api/v1/reporting/overview?days=1')
                self.assertEqual(report.status_code, 200, report.text)
                self.assertEqual(report.json()['as_of'], expected.isoformat())
                self.assertEqual(report.json()['sales_by_status']['Pago'], {'quantidade': 1, 'valor': '10.00'})
                self.assertEqual(report.json()['finance_by_type_and_status'][0]['quantidade'], 1)

    def test_period_excludes_future_old_and_other_business_records(self):
        owner=self.register('reports-a@example.test');other=self.register('reports-b@example.test')
        self.seed(owner.identity['negocio']['id'],10);self.seed(other.identity['negocio']['id'],99)
        report=owner.get('/api/v1/reporting/overview?days=30')
        self.assertEqual(report.status_code,200,report.text)
        self.assertEqual(report.json()['sales_by_status']['Pago'],{'quantidade':2,'valor':'20.00'})
        self.assertEqual(report.json()['finance_by_type_and_status'][0]['quantidade'],2)
        self.assertEqual(report.json()['finance_by_type_and_status'][0]['valor'],'20.00')
        csv=owner.get('/api/v1/reporting/overview.csv?days=30')
        self.assertIn('20.00',csv.text);self.assertNotIn('Private customer',csv.text);self.assertNotIn('Private finance',csv.text)

    def test_grant_switch_and_revoke_invalidate_only_authorized_workspace_access(self):
        owner=self.register('owner-reports@example.test');viewer=self.register('viewer-reports@example.test')
        original=viewer.identity['negocio']['id'];target=owner.identity['negocio']['id']
        self.seed(target,10)
        result=owner.post('/api/v1/reporting/access',json={'email':'viewer-reports@example.test'})
        self.assertTrue(result.json()['granted'])
        choices=viewer.get('/api/v1/auth/workspaces').json()['items'];self.assertEqual({x['id'] for x in choices},{original,target})
        old=viewer.cookies.get(COOKIE)
        changed=viewer.post('/api/v1/auth/workspaces/switch',json={'workspace_id':target})
        self.assertEqual(changed.status_code,200,changed.text);self.assertEqual(changed.json()['papel'],'report_viewer')
        viewer.headers['X-SocialMEI-CSRF']=changed.json()['csrf_token']
        stale=TestClient(accounts.app,base_url=accounts.ORIGIN);stale.cookies.set(COOKIE,old)
        self.assertEqual(stale.get('/api/v1/reporting/overview').status_code,401)
        self.assertEqual(viewer.get('/api/v1/reporting/overview').status_code,200)
        for path in ('/clientes','/financeiro','/knowledge/pdf','/instagram/meta/status','/reporting/access'):
            self.assertEqual(viewer.get('/api/v1'+path).status_code,403,path)
        self.assertEqual(viewer.post('/api/v1/produtos',json={'nome':'forbidden','preco':1}).status_code,403)
        self.assertEqual(viewer.post('/api/v1/auth/workspaces/switch',json={'workspace_id':999999}).status_code,403)
        self.assertEqual(owner.delete('/api/v1/reporting/access/'+str(viewer.identity['usuario']['id'])).status_code,204)
        self.assertEqual(viewer.get('/api/v1/reporting/overview').status_code,401)
        again=self.login('viewer-reports@example.test')
        self.assertEqual(again.identity['negocio']['id'],original)
        self.assertEqual(again.get('/api/v1/auth/workspaces').json()['items'][0]['role'],'owner')
        self.assertEqual(len(again.get('/api/v1/auth/workspaces').json()['items']),1)
