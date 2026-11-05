from datetime import datetime, timedelta, timezone
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
import test_account_auth as accounts

PATH='/api/v1/onboarding/status'


class StartContracts(unittest.TestCase):
    def test_missing_session_never_reads_business_records(self):
        with patch.dict(os.environ,accounts.ENV), patch('business_start.connect',side_effect=AssertionError('database')):
            self.assertEqual(TestClient(accounts.app,base_url=accounts.ORIGIN).get(PATH).status_code,401)


@unittest.skipUnless(accounts.DB,'Disposable PostgreSQL required')
class StartDatabase(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp=accounts.AccountDatabaseTests.setUp
    login=accounts.AccountDatabaseTests.login
    register=accounts.AccountDatabaseTests.register
    invited=accounts.AccountDatabaseTests.invited

    def post(self,path,data):
        response=self.admin_client.post('/api/v1'+path,json=data)
        self.assertTrue(response.is_success,response.text)
        return response.json()

    def test_new_business_stays_empty_without_fake_setup_completion(self):
        response=self.admin_client.get(PATH)
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertFalse(data['profile_complete'])
        self.assertFalse(data['profile_problem'])
        self.assertEqual(data['offers'],[])
        self.assertTrue(all(value==0 for value in data['counts'].values()))
        self.assertEqual(response.headers['cache-control'],'no-store')

    def test_real_service_journey_and_saved_profile_are_scoped_to_one_business(self):
        profile={'version':1,'businessName':'Provided name is normalized by the existing API','segment':'services','activity':'Fictional services','offers':['services'],'services':[],'productCategories':[],
                 'capabilities':{key:key=='appointments' for key in ['appointments','orders','deliveries','inventory','team','walkIns','quotes','onlineOrders','recurring']},
                 'modules':['clients','services','appointments'],'ignoredSuggestions':[],'completed':True}
        response=self.admin_client.patch('/api/v1/workspace-profile',json={'schema_version':1,'expected_revision':0,'profile':profile})
        self.assertEqual(response.status_code,200,response.text)
        customer=self.post('/clientes',{'nome':'Cliente fictício do guia'})
        service=self.post('/produtos',{'nome':'Avaliação fictícia','tipo':'Serviço','preco':80,'duracao_minutos':30})
        resource=self.post('/agenda/resources',{'operation_id':str(uuid4()),'nome':'Recurso fictício'})
        booking=self.post('/agenda/appointments',{'operation_id':str(uuid4()),'cliente_id':customer['id'],'servico_id':service['id'],'resource_id':resource['id'],'scheduled_for':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()})
        data=self.admin_client.get(PATH).json()
        self.assertTrue(data['profile_complete'])
        self.assertEqual(data['offers'],['services'])
        self.assertEqual(data['counts'],{'customers':1,'services':1,'resources':1,'appointments_created':1,'products':0,'valid_sales':0})
        response=self.admin_client.patch('/api/v1/agenda/appointments/'+booking['id'],json={'expected_revision':booking['revision'],'status':'cancelled'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.admin_client.get(PATH).json()['counts']['appointments_created'],1)
        me=self.admin_client.get('/api/v1/auth/me').json()
        self.admin_client.headers['X-SocialMEI-Identity']=f"{me['usuario']['id']}:{me['negocio']['id']}"
        self.admin_client.headers['X-SocialMEI-CSRF']=me['csrf_token']
        created=self.post('/auth/workspaces',{'nome':'Outro negócio fictício','segmento':'Moda fictícia','idempotency_key':str(uuid4())})
        selected=self.post('/auth/workspaces/switch',{'workspace_id':created['negocio']['id']})
        self.admin_client.headers['X-SocialMEI-Identity']=f"{selected['usuario']['id']}:{selected['negocio']['id']}"
        self.admin_client.headers['X-SocialMEI-CSRF']=selected['csrf_token']
        other=self.admin_client.get(PATH+'?workspace_id='+str(data['workspace_id'])).json()
        self.assertFalse(other['profile_complete'])
        self.assertTrue(all(v==0 for v in other['counts'].values()))
        self.assertNotEqual(other['workspace_id'],data['workspace_id'])

    def test_product_and_sale_counts_follow_persisted_status(self):
        product=self.post('/produtos',{'nome':'Produto fictício','preco':'59.90','estoque':5})
        self.post('/produtos',{'nome':'Inativo','preco':1,'estoque':1,'status':'Inativo'})
        sale=self.post('/vendas',{'operation_id':str(uuid4()),'produto_id':product['id'],'preco':'59.90','quantidade':1,'data':datetime.now(timezone.utc).date().isoformat()})
        counts=self.admin_client.get(PATH).json()['counts']
        self.assertEqual(counts['products'],1)
        self.assertEqual(counts['customers'],0)
        self.assertEqual(counts['valid_sales'],1)
        self.post('/vendas/'+str(sale['id'])+'/cancelar',{'operation_id':str(uuid4()),'expected_version':sale['versao']})
        self.assertEqual(self.admin_client.get(PATH).json()['counts']['valid_sales'],0)

    def test_roles_and_session_revocation_are_checked_in_backend(self):
        for role in ['member','viewer','report_viewer','admin']:
            with psycopg.connect(accounts.DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s',(role,self.admin_id))
            self.assertEqual(self.admin_client.get(PATH).status_code,200 if role=='admin' else 403)
        self.admin_client.post('/api/v1/auth/logout',json={})
        self.assertEqual(self.admin_client.get(PATH).status_code,401)

    def test_unconfirmed_profile_and_private_database_errors_never_show_ready(self):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("INSERT INTO socialmei.workspace_profiles(workspace_id,profile) VALUES(%s,'{\"version\":1}'::jsonb)",(self.admin_client.identity['negocio']['id'],))
        data=self.admin_client.get(PATH).json()
        self.assertFalse(data['profile_complete'])
        self.assertTrue(data['profile_problem'])
        self.assertEqual(data['offers'],[])
        with patch('business_start.connect',side_effect=psycopg.OperationalError('private host and password')):
            response=self.admin_client.get(PATH)
        self.assertEqual(response.status_code,503)
        self.assertNotIn('private host',response.text)


if __name__=='__main__':unittest.main()
