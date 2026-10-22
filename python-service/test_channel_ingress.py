"""Signed fixture reception reuses the synthetic Inbox, without provider transport."""
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import app
import test_account_auth as accounts
from test_account_auth import DB, ENV, ORIGIN
from channel_ingress import sign_fixture, verify_fixture

BASE = '/api/v1/channel-lab'
INTERNAL = '/internal/channel-ingress/waha'
MODE = {'SOCIALMEI_CHANNEL_INGRESS_MODE':'fixture', 'SOCIALMEI_CHANNEL_INGRESS_TEST_KEY':'fixture-only-key-for-channel-ingress-123456', 'SOCIALMEI_MESSAGE_ENRICHMENT_MODE':'stub', 'SOCIALMEI_MESSAGE_ENRICHMENT_TEST_KEY':'fixture-only-enrichment-key-1234567890'}


def event(**overrides):
    return dict(schema_version=1, event_id=str(uuid4()), timestamp=int(time.time()), instance='fixture-primary', session='fixture-shop', event='message', payload={'id':'message-1','from':'contact-1','fromMe':False,'type':'chat','body':'Preciso de um orçamento.','notifyName':'Pessoa fictícia'}, **overrides)


class IngressUnitTests(unittest.TestCase):
    def test_disabled_no_database_and_no_real_transport(self):
        with patch.dict(os.environ, ENV), patch('message_enrichment.connect', side_effect=AssertionError('DB')):
            r=TestClient(app,base_url=ORIGIN).post(INTERNAL,json={})
            self.assertEqual(r.status_code,503)
            self.assertEqual(r.headers['cache-control'],'no-store')

    def test_shared_data_off_or_invalid_origin_fails_before_storage(self):
        for options in ({'SOCIALMEI_SHARED_DATA_ENABLED':'false'},{'SOCIALMEI_AUTH_ORIGIN':'http://invalid.example'}):
            with patch.dict(os.environ,{**ENV,**MODE,**options}), patch('message_enrichment.connect',side_effect=AssertionError('DB')):
                r=TestClient(app,base_url=ORIGIN).post(INTERNAL,json=sign_fixture(event()))
                self.assertEqual(r.status_code,503)
                self.assertEqual(r.headers['cache-control'],'no-store')

    def test_signature_tampering_stale_and_forbidden_workspace(self):
        with patch.dict(os.environ,{**ENV,**MODE}):
            signed=sign_fixture(event())
            self.assertEqual(verify_fixture(signed).instance,'fixture-primary')
            signed['payload']['body']='changed'
            with self.assertRaises(HTTPException):verify_fixture(signed)
            with self.assertRaises(HTTPException):verify_fixture(sign_fixture({**event(),'timestamp':int(time.time())-121}))
            with self.assertRaises(HTTPException):verify_fixture({**sign_fixture(event()),'workspace_id':1})

    def test_media_and_outgoing_are_not_incoming_messages(self):
        with patch.dict(os.environ,{**ENV,**MODE}):
            for change in ({'fromMe':True},{'fromMe':0},{'fromMe':'false'},{'type':'image'},{'body':''}):
                e=event(); e['payload'].update(change)
                with self.assertRaises((HTTPException,ValueError)):verify_fixture(sign_fixture(e))


@unittest.skipUnless(DB,'TEST_DATABASE_URL not configured')
class IngressDatabaseTests(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login=accounts.AccountDatabaseTests.login
    invited=accounts.AccountDatabaseTests.invited
    register=accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        p=patch.dict(os.environ,MODE);p.start();self.addCleanup(p.stop)
        self.internal=TestClient(app,base_url=ORIGIN)

    def channel(self,client=None,session='fixture-shop'):
        r=(client or self.admin_client).post(BASE+'/accounts',json={'instance':'fixture-primary','session':session,'name':'Canal fictício'})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def deliver(self,body):
        return self.internal.post(INTERNAL,json=sign_fixture(body))

    def test_signed_ingress_two_sessions_native_enrich_and_review(self):
        self.channel();body=event()
        first=self.deliver(body);self.assertEqual(first.status_code,200,first.text)
        second=self.login('admin@example.com')
        rows=second.get('/api/v1/message-enrichment/conversations').json()['items']
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['messages'][0]['text'],body['payload']['body'])
        mid=first.json()['message_id']
        r=second.post('/api/v1/message-enrichment/messages/%s/enrich'%mid,json={'schema_version':1,'operation_id':str(uuid4()),'expected_revision':1})
        self.assertEqual(r.status_code,200,r.text)
        review=second.patch('/api/v1/message-enrichment/jobs/'+r.json()['id']+'/review',json={'schema_version':1,'expected_revision':r.json()['revision'],'decision':'approved','suggested_reply':'Vamos conferir sua necessidade.'})
        self.assertEqual(review.status_code,200,review.text)
        self.assertEqual(review.json()['transport'],'none')

    def test_duplicate_concurrent_events_and_content_conflict(self):
        self.channel();body=event()
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:self.deliver(body),range(2)))
        self.assertEqual([r.status_code for r in responses],[200,200])
        self.assertEqual(responses[0].json()['message_id'],responses[1].json()['message_id'])
        changed={**body,'payload':{**body['payload'],'body':'changed'}}
        self.assertEqual(self.deliver(changed).status_code,409)
        alias={**body,'event_id':str(uuid4())}
        self.assertEqual(self.deliver(alias).json()['message_id'],responses[0].json()['message_id'])

    def test_workspace_account_binding_and_identical_contact_names(self):
        self.channel();other=self.register('other@example.com');self.channel(other,'fixture-other')
        a=self.deliver(event()).json(); b=self.deliver({**event(),'session':'fixture-other'}).json()
        self.assertNotEqual(a['conversation_id'],b['conversation_id'])
        rows=other.get('/api/v1/message-enrichment/conversations').json()['items'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['id'],b['conversation_id'])
        self.assertEqual(other.get('/api/v1/message-enrichment/conversations/%s/enrichments'%a['conversation_id']).status_code,404)
        self.assertEqual(self.deliver({**event(),'session':'fixture-missing'}).status_code,404)

    def test_authorization_csrf_and_invalid_signature(self):
        self.channel()
        self.assertEqual(self.internal.post(BASE+'/accounts',json={'instance':'fixture-x','session':'fixture-y','name':'X'}).status_code,403)
        body=sign_fixture(event());body['signature']='0'*64
        self.assertEqual(self.internal.post(INTERNAL,json=body).status_code,403)
        self.assertEqual(self.internal.post(INTERNAL,content='{}',headers={'Content-Type':'text/plain'}).status_code,422)
        self.assertEqual(self.internal.post(INTERNAL,content='{"event_id":"a","event_id":"b"}',headers={'Content-Type':'application/json'}).status_code,422)
