"""Private candidate generation only; no database, Docker, files or provider."""
from copy import deepcopy
from datetime import datetime, timezone
import unittest
from uuid import uuid4

from whatsapp_channel_handover import Handover
from whatsapp_handover_runtime_plan import prepare_runtime_plan
from workspace_access import AccessError
from settings import waha_pilot_binding_digest


class RuntimePlanTests(unittest.TestCase):
    def setUp(self):
        self.request=Handover(1,34,1,1,60,3,'pilot','01','111@c.us')
        self.receipt={'id':str(uuid4()),'source_workspace_id':1,'source_channel_id':1,
                      'target_workspace_id':60,'target_channel_id':2,'status':'reserved',
                      'ingress_after':'2026-11-20T12:00:00.123456+00:00'}
        self.registry={'version':1,'bindings':[{'workspace_id':1,'channel_id':1,'instance':'pilot',
                       'session':'01','account_id':'111@c.us','revision':3,'engine':'GOWS',
                       'hmac_key':'synthetic-private-hmac-key-1234567890','ingress_after':1}]}

    def test_candidate_preserves_physical_session_hmac_and_source_object(self):
        before=deepcopy(self.registry)
        plan=prepare_runtime_plan(self.request,self.receipt,self.registry)
        b=plan['candidate_registry']['bindings'][0]
        self.assertEqual(self.registry,before)
        self.assertEqual((b['workspace_id'],b['channel_id'],b['revision']),(60,2,2))
        for field in ['instance','session','account_id','engine','hmac_key']:
            self.assertEqual(b[field],before['bindings'][0][field])
        self.assertGreaterEqual(b['ingress_after'],datetime.fromisoformat(self.receipt['ingress_after']).timestamp())
        self.assertLess(b['ingress_after']-datetime.fromisoformat(self.receipt['ingress_after']).timestamp(),1)
        self.assertEqual(plan['configuration_delta']['SOCIALMEI_WAHA_PILOT_BINDING_SHA256'],
                         waha_pilot_binding_digest(60,2,'pilot','01','111@c.us',2,'GOWS'))
        self.assertTrue(plan['new_worker_credential_required'])
        self.assertFalse(plan['runtime_modified'])
        self.assertFalse(plan['responders_started'])

    def test_foreign_or_reused_receipts_and_bad_dates_are_rejected(self):
        for change in [{'status':'active'},{'source_workspace_id':61},{'target_workspace_id':61},
                       {'source_channel_id':3},{'target_channel_id':1},{'target_channel_id':True},
                       {'ingress_after':'2026-11-20T12:00:00'},{'ingress_after':'invalid'},
                       {'ingress_after':'1970-01-01T00:00:00+00:00'}]:
            with self.subTest(change=change),self.assertRaises(AccessError):
                prepare_runtime_plan(self.request,{**self.receipt,**change},self.registry)

    def test_changed_registry_and_additional_binding_are_rejected(self):
        for change in [{'workspace_id':61},{'channel_id':3},{'revision':4},{'session':'02'},
                       {'instance':'other'},{'account_id':'999@c.us'},{'engine':'WEBJS'}]:
            registry=deepcopy(self.registry);registry['bindings'][0].update(change)
            with self.subTest(change=change),self.assertRaises((AccessError,ValueError)):
                prepare_runtime_plan(self.request,self.receipt,registry)
        registry=deepcopy(self.registry);registry['bindings']*=2
        with self.assertRaises(AccessError):prepare_runtime_plan(self.request,self.receipt,registry)


if __name__=='__main__':unittest.main()
