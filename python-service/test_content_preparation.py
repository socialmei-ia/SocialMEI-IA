"""Preparation and safe scheduling, entirely isolated from provider transports."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from account_auth import COOKIE, csrf
from app import app
from content_preparation import JobInput, CaptionInput, caption_suggestions, run_due, TransientFailure, UncertainOutcome

DB = os.getenv('TEST_DATABASE_URL','').strip()
ORIGIN='https://app.example.com'
TOKEN='a'*64
ENV={'SOCIALMEI_AUTH_ENABLED':'true','SOCIALMEI_SHARED_DATA_ENABLED':'true','SOCIALMEI_AUTH_ORIGIN':ORIGIN,'SOCIALMEI_CONTENT_PREPARATION_MODE':'simulation','SOCIALMEI_INSTAGRAM_MODE':'simulation'}
MEDIA=[{'name':'fixture.png','mime':'image/png','size':512}]

class ContractTests(unittest.TestCase):
 def test_drafts_and_review_validation(self):
  base={'idempotency_key':str(uuid4()),'title':'Teste','format':'feed','caption':'Texto','media':[],'status':'draft'}
  self.assertEqual(JobInput.model_validate(base).status,'draft')
  for change in [{'status':'published'},{'status':'scheduled'},{'workspace_id':99},{'timezone':'Unknown/Place'},{'caption':'x'*2201}]:
   with self.subTest(change=change),self.assertRaises(ValueError):JobInput.model_validate({**base,**change})
 def test_caption_adapter_uses_only_supplied_facts(self):
  result=caption_suggestions(CaptionInput(topic='Corte masculino',business='Barbearia',objective='informar',tone='simples'))
  self.assertEqual(result['source'],'template_fixture')
  self.assertFalse(result['generated_by_ai'])
  self.assertEqual(len(result['alternatives']),3)
  self.assertNotIn('R$',str(result))
 def test_disabled_never_accesses_database(self):
  with patch.dict(os.environ,{**ENV,'SOCIALMEI_CONTENT_PREPARATION_MODE':'disabled'}),patch('account_auth.session_identity',return_value={'id':1,'workspace_id':1,'role':'owner','administrador_plataforma':False}),patch('content_preparation.connect',side_effect=AssertionError('DB accessed')):
   client=TestClient(app,base_url=ORIGIN);client.cookies.set(COOKIE,TOKEN)
   self.assertEqual(client.get('/api/v1/content/preparation/status').status_code,503)

@unittest.skipUnless(DB,'Postgres test database not configured')
class DatabaseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  with psycopg.connect(DB,autocommit=True) as conn:
   for f in sorted((Path(__file__).resolve().parents[1]/'database/migrations').glob('*.sql')):conn.execute(f.read_text(),prepare=False)
 def setUp(self):
  self.env=patch.dict(os.environ,{**ENV,'DATABASE_URL':DB});self.env.start();self.addCleanup(self.env.stop)
  self.identities=[]
  with psycopg.connect(DB) as conn:
   for _ in range(2):
    marker=uuid4().hex
    wid=conn.execute('INSERT INTO socialmei.workspaces(slug,nome) VALUES (%s,%s) RETURNING id',('prep-'+marker,'Fictício')).fetchone()[0]
    uid=conn.execute('INSERT INTO socialmei.users(email,nome) VALUES (%s,%s) RETURNING id',(marker+'@example.test','Fictício')).fetchone()[0]
    conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES (%s,%s,'owner')",(wid,uid))
    self.identities.append({'id':uid,'workspace_id':wid,'role':'owner','administrador_plataforma':False})
  self.identity=self.identities[0]
  auth=patch('account_auth.session_identity',side_effect=lambda _:self.identity);auth.start();self.addCleanup(auth.stop)
  self.client=TestClient(app,base_url=ORIGIN);self.client.cookies.set(COOKIE,TOKEN)
  self.headers={'Origin':ORIGIN,'X-SocialMEI-CSRF':csrf(TOKEN)}
  self.prefix='/api/v1/content/preparation'
  self.account=self.client.post('/api/v1/instagram/simulation/accounts',headers=self.headers,json={'label':'Conta fictícia'}).json()['id']
 def tearDown(self):
  with psycopg.connect(DB) as conn:
   for u in self.identities:
    conn.execute('DELETE FROM socialmei.workspaces WHERE id=%s',(u['workspace_id'],));conn.execute('DELETE FROM socialmei.users WHERE id=%s',(u['id'],))
 def payload(self,**kw):
  return {'idempotency_key':str(uuid4()),'account_id':self.account,'title':'Fictício','format':'feed','caption':'Sem envio','media':MEDIA,'status':'scheduled','reviewed':True,'scheduled_for':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),'timezone':'America/Fortaleza',**kw}
 def post(self,path,data):return self.client.post(self.prefix+path,json=data,headers=self.headers)
 def due(self,jid):
  with psycopg.connect(DB) as c:c.execute("UPDATE socialmei.content_preparation_jobs SET run_after=now()-interval '1 minute' WHERE id=%s",(jid,))
 def test_crud_cas_workspace_idempotency(self):
  p=self.payload();a=self.post('/jobs',p);self.assertEqual(a.status_code,201,a.text);job=a.json();self.assertFalse(job['published'])
  self.assertEqual(self.post('/jobs',p).json()['id'],job['id'])
  self.assertEqual(self.post('/jobs',{**p,'caption':'Outro'}).status_code,409)
  update={**p,'revision':job['revision'],'caption':'Editado'}
  changed=self.client.put(self.prefix+'/jobs/'+job['id'],headers=self.headers,json=update);self.assertEqual(changed.status_code,200,changed.text)
  self.assertEqual(self.client.put(self.prefix+'/jobs/'+job['id'],headers=self.headers,json=update).status_code,409)
  self.identity=self.identities[1]
  self.assertEqual(self.client.get(self.prefix+'/jobs').json()['items'],[])
  self.assertEqual(self.client.get(self.prefix+'/jobs/'+job['id']).status_code,404)
  self.assertEqual(self.post('/jobs',self.payload()).status_code,404)
  self.identity=self.identities[0]
  cancel=self.post('/jobs/'+job['id']+'/cancel',{'revision':changed.json()['revision']});self.assertEqual(cancel.json()['status'],'cancelled')
  self.assertEqual(self.post('/jobs/'+job['id']+'/cancel',{'revision':changed.json()['revision']}).status_code,409)
 def test_worker_persistence_retry_and_uncertain(self):
  job=self.post('/jobs',self.payload()).json();self.due(job['id']);wid=self.identity['workspace_id']
  def fail(_):raise TransientFailure()
  self.assertEqual(run_due(wid,processor=fail)['items'][0]['status'],'scheduled')
  with psycopg.connect(DB) as c:c.execute("UPDATE socialmei.content_preparation_jobs SET run_after=now()-interval '1 minute' WHERE id=%s",(job['id'],))
  result=run_due(wid)['items'][0];self.assertEqual(result['status'],'simulated');self.assertFalse(result['published']);self.assertEqual(result['attempts'],2)
  self.assertEqual(run_due(wid)['items'],[])
  uncertain=self.post('/jobs',self.payload()).json();self.due(uncertain['id'])
  def unknown(_):raise UncertainOutcome()
  self.assertEqual(run_due(wid,processor=unknown)['items'][0]['status'],'uncertain')
  self.assertEqual(run_due(wid)['items'],[])
 def test_expired_claim_recovered_only_in_simulation(self):
  job=self.post('/jobs',self.payload()).json();wid=self.identity['workspace_id']
  with psycopg.connect(DB) as c:c.execute("UPDATE socialmei.content_preparation_jobs SET status='processing',attempts=1,claim_token=%s,lease_until=now()-interval '1 minute' WHERE id=%s",(uuid4(),job['id']))
  result=run_due(wid)['items'][0];self.assertEqual(result['status'],'simulated');self.assertEqual(result['attempts'],2)
 def test_permissions_origin_and_private_validation(self):
  self.assertEqual(self.client.post(self.prefix+'/jobs',json=self.payload()).status_code,403)
  self.identity={**self.identities[0],'role':'viewer'}
  self.assertEqual(self.post('/jobs',self.payload()).status_code,403)
  self.identity=self.identities[0]
  response=self.post('/jobs',{'caption':'private-marker-unsafe','workspace_id':12});self.assertEqual(response.status_code,422);self.assertNotIn('private-marker-unsafe',response.text)

 def test_accounts_independent_from_instagram_and_two_sessions(self):
  with patch.dict(os.environ,{'SOCIALMEI_INSTAGRAM_MODE':'disabled'}):
   account=self.post('/accounts',{'label':'Outra conta fictícia'})
   self.assertEqual(account.status_code,201,account.text)
   self.assertEqual(account.json()['workspace_id'],self.identity['workspace_id'])
  original=self.payload();created=self.post('/jobs',original).json()
  second=TestClient(app,base_url=ORIGIN);second.cookies.set(COOKIE,'b'*64)
  headers={'Origin':ORIGIN,'X-SocialMEI-CSRF':csrf('b'*64)}
  self.assertEqual(second.get(self.prefix+'/jobs').json()['items'][0]['id'],created['id'])
  payload={**original,'revision':created['revision'],'caption':'Editado na segunda sessão'}
  updated=second.put(self.prefix+'/jobs/'+created['id'],headers=headers,json=payload)
  self.assertEqual(updated.status_code,200,updated.text)
  self.assertEqual(self.client.put(self.prefix+'/jobs/'+created['id'],headers=self.headers,json=payload).status_code,409)
  replay=self.post('/jobs',original)
  self.assertEqual(replay.json()['caption'],'Editado na segunda sessão')
  self.assertEqual(replay.json()['revision'],updated.json()['revision'])
 def test_concurrent_workers_claim_distinct_jobs_once(self):
  ids=[]
  for _ in range(2):
   row=self.post('/jobs',self.payload()).json();ids.append(row['id']);self.due(row['id'])
  barrier=Barrier(2)
  def processor(_):
   barrier.wait(timeout=5)
   return {'published':False,'transport':'none'}
  wid=self.identity['workspace_id']
  with ThreadPoolExecutor(max_workers=2) as pool:
   futures=[pool.submit(run_due,wid,limit=1,processor=processor) for _ in range(2)]
   results=[f.result(timeout=10)['items'][0] for f in futures]
  self.assertEqual({r['id'] for r in results},set(ids))
  self.assertTrue(all(r['attempts']==1 and r['status']=='simulated' for r in results))
  self.assertEqual(run_due(wid)['items'],[])
 def test_retry_limit_and_stale_claim_cannot_overwrite_recovery(self):
  row=self.post('/jobs',self.payload()).json();wid=self.identity['workspace_id']
  def fail(_):raise TransientFailure()
  for attempt in range(1,4):
   self.due(row['id']);result=run_due(wid,processor=fail)['items'][0]
   self.assertEqual(result['attempts'],attempt)
   self.assertEqual(result['status'],'failed' if attempt==3 else 'scheduled')
  self.assertEqual(run_due(wid)['items'],[])
  late=self.post('/jobs',self.payload()).json();self.due(late['id'])
  def recover(_):
   with psycopg.connect(DB) as conn:conn.execute("UPDATE socialmei.content_preparation_jobs SET lease_until=now()-interval '1 minute' WHERE id=%s",(late['id'],))
   self.assertEqual(run_due(wid)['items'][0]['status'],'simulated')
   return {'published':False,'transport':'none'}
  self.assertEqual(run_due(wid,processor=recover)['items'],[])
  persisted=self.client.get(self.prefix+'/jobs/'+late['id']).json()
  self.assertEqual(persisted['status'],'simulated');self.assertEqual(persisted['attempts'],2)
 def test_errors_queries_and_body_are_private_and_fail_closed(self):
  with patch('content_preparation.connect',side_effect=psycopg.OperationalError('private-db-marker')):
   response=self.client.get(self.prefix+'/jobs');self.assertEqual(response.status_code,503,response.text);self.assertNotIn('private-db-marker',response.text);self.assertEqual(response.headers['cache-control'],'no-store')
  self.assertEqual(self.client.get(self.prefix+'/jobs?workspace_id=999').status_code,422)
  self.assertEqual(self.post('/run-due',{'workspace_id':999}).status_code,422)
  self.identity={**self.identities[0],'role':'viewer'}
  self.assertEqual(self.client.get(self.prefix+'/jobs').status_code,200)
  self.assertEqual(self.post('/run-due',{}).status_code,403)
 def test_persisted_rate_limit_does_not_create_jobs(self):
  import hashlib
  key=hashlib.sha256(f"preparation:{self.identity['workspace_id']}:{self.identity['id']}".encode()).hexdigest()
  with psycopg.connect(DB) as conn:conn.execute('INSERT INTO socialmei.auth_limites(chave,tentativas) VALUES (%s,60) ON CONFLICT(chave) DO UPDATE SET tentativas=60,inicio=now()',(key,))
  response=self.post('/jobs',self.payload());self.assertEqual(response.status_code,429,response.text)
  self.assertEqual(self.client.get(self.prefix+'/jobs').json()['items'],[])
