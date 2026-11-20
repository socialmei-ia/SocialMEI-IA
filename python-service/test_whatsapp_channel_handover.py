"""Only opted-in loopback disposable PostgreSQL; signed synthetic events only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import test_account_auth as accounts
import whatsapp_channel_handover as handover
from test_waha_ingress import payload, raw, sign, KEY
from waha_ingress import WahaBinding, WahaIngressService
from workspace_access import AccessError, digest

db=urlsplit(accounts.DB)
DISPOSABLE=(os.getenv('SOCIALMEI_HANDOVER_DISPOSABLE_TESTS')=='1' and db.hostname in {'localhost','127.0.0.1'}
            and db.port==55491 and db.path in {'/socialmei_handover_test','/socialmei_demo_test'})


@unittest.skipUnless(DISPOSABLE,'Explicit disposable handover database required')
class HandoverTests(unittest.TestCase):
    setUpClass=classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login=accounts.AccountDatabaseTests.login
    invited=accounts.AccountDatabaseTests.invited
    register=accounts.AccountDatabaseTests.register

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        owner=self.register('target@example.test').identity
        self.target=owner['negocio']['id'];self.owner=owner['usuario']['id']
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        for name,value in [('waha_ingress_enabled',True),('waha_ingress_team_pilot_enabled',False)]:
            override=patch('waha_ingress.settings.'+name,return_value=value)
            override.start();self.addCleanup(override.stop)
        with psycopg.connect(accounts.DB) as c:
            self.cid=c.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) "
                               "VALUES(1,'handover-test','01','111@c.us',true,true) RETURNING id").fetchone()[0]
        self.binding=WahaBinding('handover-test','01','111@c.us',1,self.cid,KEY,engine='GOWS')
        self.service=WahaIngressService({self.binding.instance:self.binding})
        packet=payload(engine='GOWS',session='01')
        body=raw(packet)
        self.assertEqual(self.service.receive(self.binding.instance,body,sign(body),'sha512')['processed'],1)
        self.request=handover.Handover(self.admin_id,self.owner,1,self.cid,self.target,1,'handover-test','01','111@c.us',require_replies=False)
        self.proof=lambda r=None:{'scope_sha256':digest((r or self.request).__dict__),'ingress_paused':True,
            'responders_paused':True,'expires_at':(handover.now()+timedelta(seconds=60)).isoformat()}

    def rows(self,table,workspace=1):
        with psycopg.connect(accounts.DB) as c:
            return c.execute('SELECT row_to_json(t)::text FROM socialmei.'+table+' t WHERE workspace_id=%s ORDER BY id',(workspace,)).fetchall()

    def reserve(self,request=None,op=None,name='receipt.json'):
        request=request or self.request
        return handover.reserve(request,handover.inspect_handover(request)['plan_sha256'],op or uuid4(),self.proof(request),receipt_path=self.root/name)

    def target_binding(self,result):
        return replace(self.binding,workspace_id=self.target,channel_id=result['target_channel_id'],revision=2,
                       ingress_after=math.ceil(__import__('datetime').datetime.fromisoformat(result['ingress_after']).timestamp()))

    def activate(self,result,binding=None):
        binding=binding or self.target_binding(result)
        with patch('waha_ingress.waha_service',return_value=WahaIngressService({binding.instance:binding})), \
             patch('settings.waha_inbox_enabled',return_value=True):
            return handover.activate(self.request,result['id'],self.proof())

    def test_retire_reserve_preserves_history_and_replays_receipt(self):
        snapshots={t:self.rows(t) for t in ['me_conversations','me_messages','crm_eventos_canal']}
        operation=uuid4();result=self.reserve(op=operation)
        again=handover.reserve(self.request,'unused-for-exact-replay',operation,self.proof(),receipt_path=self.root/'replayed.json')
        self.assertEqual(result,again)
        with psycopg.connect(accounts.DB) as c:
            rows=c.execute('SELECT workspace_id,instancia,sessao,ativo,ingress_provisioned,retired_at IS NOT NULL FROM socialmei.crm_canais ORDER BY id').fetchall()
            self.assertEqual(rows,[(1,'handover-test','01',False,False,True),(self.target,'handover-test','01',False,False,False)])
        for table,old in snapshots.items():self.assertEqual(self.rows(table),old)
        with self.assertRaises(AccessError):handover.reserve(replace(self.request,target_owner_id=self.admin_id),'x',operation,self.proof(replace(self.request,target_owner_id=self.admin_id)),receipt_path=self.root/'bad.json')

    def test_unretired_disabled_reservation_is_still_unique(self):
        with psycopg.connect(accounts.DB) as c:c.execute('UPDATE socialmei.crm_canais SET ativo=false,ingress_provisioned=false WHERE id=%s',(self.cid,))
        with self.assertRaises(psycopg.errors.UniqueViolation),psycopg.connect(accounts.DB) as c:
            c.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao) VALUES(%s,'handover-test','01')",(self.target,))

    def test_migration_replay_preserves_installed_history(self):
        before=self.rows('me_messages')
        sql=(Path(__file__).resolve().parents[1]/'database/migrations/041_whatsapp_channel_lifecycle.sql').read_text()
        with psycopg.connect(accounts.DB) as c:
            c.execute(sql)
            c.execute(sql)
        self.assertEqual(self.rows('me_messages'),before)

    def test_active_channel_cannot_be_marked_retired(self):
        with self.assertRaises(psycopg.errors.CheckViolation),psycopg.connect(accounts.DB) as c:
            c.execute('UPDATE socialmei.crm_canais SET retired_at=NOW() WHERE id=%s',(self.cid,))

    def test_state_change_and_receipt_failure_rollback_entire_reservation(self):
        plan=handover.inspect_handover(self.request)
        with psycopg.connect(accounts.DB) as c:c.execute("UPDATE socialmei.crm_canais SET nome='Changed' WHERE id=%s",(self.cid,))
        with self.assertRaisesRegex(AccessError,'APPROVED_BASELINE_CHANGED'):
            handover.reserve(self.request,plan['plan_sha256'],uuid4(),self.proof(),receipt_path=self.root/'stale.json')
        with patch('whatsapp_channel_handover._save_receipt',side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):self.reserve()
        with psycopg.connect(accounts.DB) as c:
            self.assertEqual(c.execute('SELECT ativo,retired_at FROM socialmei.crm_canais WHERE id=%s',(self.cid,)).fetchone(),(True,None))
            self.assertEqual(c.execute('SELECT count(*) FROM socialmei.wa_channel_handovers').fetchone()[0],0)

    def test_runtime_pause_must_be_current_and_scoped(self):
        plan=handover.inspect_handover(self.request)
        for change in [{'ingress_paused':False},{'responders_paused':False},{'scope_sha256':'bad'},
                       {'expires_at':(handover.now()-timedelta(seconds=1)).isoformat()}]:
            with self.subTest(change=change),self.assertRaises(AccessError):
                handover.reserve(self.request,plan['plan_sha256'],uuid4(),{**self.proof(),**change},receipt_path=self.root/'bad-proof.json')

    def test_human_draft_requires_explicit_review_and_is_never_moved_or_sent(self):
        draft=uuid4()
        with psycopg.connect(accounts.DB) as c:
            conv,msg=c.execute('SELECT conversation_id,id FROM socialmei.me_messages WHERE workspace_id=1').fetchone()
            c.execute("INSERT INTO socialmei.wa_human_replies(workspace_id,id,channel_id,conversation_id,source_message_id,"
                      "binding_hash,fingerprint,text,created_by) VALUES(1,%s,%s,%s,%s,%s,%s,'Synthetic unsent draft',%s)",
                      (draft,self.cid,conv,msg,'a'*64,'b'*64,self.admin_id))
        with self.assertRaisesRegex(AccessError,'HUMAN_DRAFT_REVIEW_REQUIRED'):handover.inspect_handover(self.request)
        request=replace(self.request,reviewed_draft_ids=(str(draft),))
        self.reserve(request=request)
        with psycopg.connect(accounts.DB) as c:
            self.assertEqual(c.execute('SELECT workspace_id,status,text FROM socialmei.wa_human_replies WHERE id=%s',(draft,)).fetchone(),
                             (1,'draft','Synthetic unsent draft'))

    def test_uncertain_send_and_missing_target_permission_block_before_retirement(self):
        with self.assertRaisesRegex(AccessError,'ACTIVE_TARGET_OWNER_REQUIRED'):
            handover.inspect_handover(replace(self.request,target_owner_id=self.admin_id))
        with psycopg.connect(accounts.DB) as c:
            conv,msg=c.execute('SELECT conversation_id,id FROM socialmei.me_messages WHERE workspace_id=1').fetchone()
            c.execute('INSERT INTO socialmei.wa_bot_conversations(workspace_id,channel_id,conversation_id) VALUES(1,%s,%s)',(self.cid,conv))
            c.execute("INSERT INTO socialmei.wa_bot_decisions(id,workspace_id,channel_id,conversation_id,source_message_id,"
                      "binding_hash,state_revision,result,status,claimed_at,finished_at) VALUES(%s,1,%s,%s,%s,%s,1,'{}','uncertain',NOW(),NOW())",
                      (uuid4(),self.cid,conv,msg,'a'*64))
        with self.assertRaisesRegex(AccessError,'UNRECONCILED_SENDS'):handover.inspect_handover(self.request)

    def test_replying_target_cannot_activate_with_receive_only_authorization(self):
        self.request=replace(self.request,require_replies=True)
        result=self.reserve()
        with self.assertRaisesRegex(AccessError,'TARGET_REPLY_AUTHORIZATION_NOT_READY'):self.activate(result)

    def test_replying_target_requires_matching_bot_and_human_private_scope(self):
        import settings
        from test_waha_team_pilot import FLAGS
        self.request=replace(self.request,require_replies=True)
        result=self.reserve();b=self.target_binding(result)
        environment={**FLAGS,'SOCIALMEI_WAHA_PILOT_WORKSPACE_ID':str(b.workspace_id),
            'SOCIALMEI_WAHA_PILOT_BINDING_SHA256':settings.waha_pilot_binding_digest(
                b.workspace_id,b.channel_id,b.instance,b.session,b.account_id,b.revision,b.engine),
            'SOCIALMEI_WHATSAPP_BOT_ENABLED':'true','SOCIALMEI_WHATSAPP_BOT_PUBLIC_INBOUND_ENABLED':'true',
            'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED':'true','SOCIALMEI_WHATSAPP_HUMAN_OWNER':'dashboard',
            'SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID':str(b.workspace_id),
            'SOCIALMEI_WHATSAPP_HUMAN_INSTANCE':b.instance,'SOCIALMEI_WHATSAPP_HUMAN_SESSION':b.session,
            'SOCIALMEI_WHATSAPP_HUMAN_ACCOUNT_ID':b.account_id,'SOCIALMEI_WHATSAPP_HUMAN_ENGINE':'GOWS',
            'SOCIALMEI_WHATSAPP_HUMAN_CONTACTS':'["222@c.us"]',
            'SOCIALMEI_WAHA_PRIVATE_BASE_URL':'http://socialmei-waha-gows-piloto:3000',
            'SOCIALMEI_WAHA_PRIVATE_API_KEY':'synthetic-private-api-key-123456789'}
        with patch.dict(os.environ,environment),patch('settings.waha_ingress_team_pilot_enabled',return_value=True):
            with patch.dict(os.environ,{'SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID':'1'}):
                with self.assertRaisesRegex(AccessError,'TARGET_HUMAN_SENDER_NOT_READY'):self.activate(result)
            self.assertTrue(self.activate(result)['active'])

    def test_single_winner_for_simultaneous_reservations(self):
        plan=handover.inspect_handover(self.request)
        def attempt(i):
            try:return handover.reserve(self.request,plan['plan_sha256'],uuid4(),self.proof(),receipt_path=self.root/f'parallel-{i}.json')
            except AccessError:return None
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(attempt,range(2)))
        self.assertEqual(sum(v is not None for v in results),1)

    def test_activation_requires_registry_revision_cutoff_and_same_physical_identity(self):
        result=self.reserve();b=self.target_binding(result)
        for bad in [replace(b,revision=1),replace(b,workspace_id=1),replace(b,ingress_after=0),replace(b,account_id='999@c.us')]:
            with self.subTest(binding=repr(bad)),self.assertRaises(AccessError):self.activate(result,bad)
        self.assertEqual(self.activate(result)['revision'],2)
        target=WahaIngressService({b.instance:b})
        old=raw(payload(engine='GOWS',session='01'))
        self.assertEqual(target.receive(b.instance,old,sign(old),'sha512'),{'processed':0,'ignored':1,'duplicates':0})
        packet=payload('target-message',engine='GOWS',session='01',timestamp=(b.ingress_after+1)*1000)
        packet['payload']['timestamp']=b.ingress_after+1
        body=raw(packet)
        self.assertEqual(target.receive(b.instance,body,sign(body),'sha512')['processed'],1)
        self.assertEqual(len(self.rows('me_messages')),1)
        self.assertEqual(len(self.rows('me_messages',self.target)),1)
        with self.assertRaisesRegex(AccessError,'TARGET_TRAFFIC_REQUIRES_REVERSE_HANDOVER'):
            handover.rollback(self.request,result['id'],self.proof())

    def test_global_provider_deduplication_is_retained_across_generations(self):
        result=self.reserve()
        with self.assertRaises(psycopg.errors.UniqueViolation) as error,psycopg.connect(accounts.DB) as c:
            c.execute("INSERT INTO socialmei.crm_eventos_canal(workspace_id,canal_id,chave_evento,tipo,fingerprint,status,processado_em,"
                      "waha_account_snapshot,waha_event_key,inbox_origin) SELECT %s,%s,'duplicate-after-handover',tipo,fingerprint,'ignorado',NOW(),"
                      "waha_account_snapshot,waha_event_key,'waha' FROM socialmei.crm_eventos_canal WHERE workspace_id=1 LIMIT 1",
                      (self.target,result['target_channel_id']))
        self.assertEqual(error.exception.diag.constraint_name,'ux_waha_ingress_global')

    def test_rollback_preserves_both_channel_rows_and_monotonic_revision(self):
        history=self.rows('me_messages');result=self.reserve();self.activate(result)
        back=handover.rollback(self.request,result['id'],self.proof())
        self.assertEqual(back['source_revision'],3)
        self.assertEqual(self.rows('me_messages'),history)
        with psycopg.connect(accounts.DB) as c:
            self.assertEqual(c.execute('SELECT workspace_id,ativo,retired_at IS NOT NULL,versao FROM socialmei.crm_canais ORDER BY id').fetchall(),[(1,True,False,3),(self.target,False,True,3)])


if __name__=='__main__':unittest.main()
