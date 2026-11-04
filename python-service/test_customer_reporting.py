from datetime import date
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException
from fastapi.testclient import TestClient
import test_account_auth as accounts
from customer_reporting import customers


class CustomerReportContracts(unittest.TestCase):
    def test_bad_dates_and_missing_session_fail_before_database(self):
        with patch('customer_reporting.scope',return_value=1), patch('customer_reporting.connect',side_effect=AssertionError('database')):
            with self.assertRaises(HTTPException) as error: customers(date(2026,11,1),None)
            self.assertEqual(error.exception.status_code,422)
        with patch.dict(os.environ,accounts.ENV), patch('customer_reporting.connect',side_effect=AssertionError('database')):
            self.assertEqual(TestClient(accounts.app,base_url=accounts.ORIGIN).get('/api/v1/reporting/customers').status_code,401)


@unittest.skipUnless(accounts.DB,'Disposable PostgreSQL required')
class CustomerReportDatabase(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login=accounts.AccountDatabaseTests.login
    register=accounts.AccountDatabaseTests.register
    invited=accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.a=self.admin_client.post('/api/v1/clientes',json={'nome':'Ana fictícia'}).json()['id']
        self.b=self.admin_client.post('/api/v1/clientes',json={'nome':'Bea fictícia'}).json()['id']
        self.product=self.admin_client.post('/api/v1/produtos',json={'nome':'Produto fictício','preco':1,'estoque':30}).json()['id']
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.crm_clientes SET criado_em='2026-10-01T15:00:00Z' WHERE id=%s",(self.a,))
            conn.execute("UPDATE socialmei.crm_clientes SET criado_em='2026-11-02T15:00:00Z' WHERE id=%s",(self.b,))
        for client,day,price in [(self.a,'2026-10-01','0.50'),(self.a,'2026-11-01','0.10'),(self.a,'2026-11-03','0.20'),(self.b,'2026-11-02','0.40'),(None,'2026-11-01','99.00')]:
            self.sale(client,day,price)
        cancelled=self.sale(self.a,'2026-11-04','100.00')
        response=self.admin_client.post('/api/v1/vendas/'+str(cancelled['id'])+'/cancelar',json={'operation_id':str(uuid4()),'expected_version':cancelled['versao']})
        self.assertEqual(response.status_code,200,response.text)

    def sale(self,client,day,price):
        response=self.admin_client.post('/api/v1/vendas',json={'operation_id':str(uuid4()),'produto_id':self.product,'cliente_id':client,'data':day,'preco':price,'quantidade':1})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def report(self,client=None):
        return (client or self.admin_client).get('/api/v1/reporting/customers?start=2026-11-01&end=2026-11-30')

    def test_purchase_definitions_and_decimal_totals_use_real_sale_rows(self):
        response=self.report()
        self.assertEqual(response.status_code,200,response.text)
        value=response.json()
        self.assertEqual(value['new_customers'],1)
        self.assertEqual(value['buyers'],2)
        self.assertEqual(value['repeat_buyers'],1)
        self.assertEqual(value['returning_buyers'],1)
        self.assertEqual(value['customers'][0],{'id':self.a,'name':'Ana fictícia','purchases':2,'total':'0.30'})
        self.assertNotIn('observacao',response.text)
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_report_only_access_never_receives_customer_identification(self):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='report_viewer' WHERE user_id=%s",(self.admin_id,))
        response=self.report()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['customers'],[])
        self.assertFalse(response.json()['identification_available'])
        self.assertEqual(response.json()['buyers'],2)
        self.assertNotIn('Ana fictícia',response.text)
        self.assertEqual(self.admin_client.get('/api/v1/clientes').status_code,403)
        self.admin_client.post('/api/v1/auth/logout',json={})
        self.assertEqual(self.report().status_code,401)

    def test_other_workspace_and_unavailable_database_are_safe(self):
        with patch.dict(os.environ,{'TZ':'America/Recife'}):
            with psycopg.connect(accounts.DB) as conn:
                conn.execute("UPDATE socialmei.crm_clientes SET criado_em='2026-11-01T02:30:00Z' WHERE id=%s",(self.b,))
            self.assertEqual(self.report().json()['new_customers'],0)
            with psycopg.connect(accounts.DB) as conn:
                conn.execute("UPDATE socialmei.crm_clientes SET criado_em='2026-11-01T03:00:00Z' WHERE id=%s",(self.b,))
            self.assertEqual(self.report().json()['new_customers'],1)
        other=self.register('customer-report-other@example.test')
        result=self.report(other).json()
        self.assertEqual(result['buyers'],0)
        self.assertEqual(result['customers'],[])
        with patch('customer_reporting.connect',side_effect=psycopg.OperationalError('private detail')):
            response=self.report()
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private detail',response.text)


if __name__=='__main__':unittest.main()
