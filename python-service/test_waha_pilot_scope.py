"""Exact private pilot review; no database, provider or environment mutation."""
from dataclasses import replace
from types import SimpleNamespace
import os
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from starlette.datastructures import Headers
import settings
import whatsapp_bot
from test_waha_ingress import payload,raw,sign,KEY
from test_waha_team_pilot import FLAGS
from waha_ingress import WahaBinding,WahaIngressService


class PilotScopeTests(unittest.TestCase):
    def setUp(self):
        self.binding=WahaBinding('socialmei-equipe-piloto','01','551199995976@c.us',60,2,KEY,revision=2,engine='GOWS')
        b=self.binding
        self.env={**FLAGS,'SOCIALMEI_AUTH_ORIGIN':'https://app.example.test','SOCIALMEI_WAHA_PILOT_WORKSPACE_ID':'60',
          'SOCIALMEI_WAHA_PILOT_BINDING_SHA256':settings.waha_pilot_binding_digest(b.workspace_id,b.channel_id,b.instance,b.session,b.account_id,b.revision,b.engine),
          'SOCIALMEI_WHATSAPP_BOT_ENABLED':'true','SOCIALMEI_WHATSAPP_BOT_PUBLIC_INBOUND_ENABLED':'true',
          'SOCIALMEI_WHATSAPP_GOWS_PUBLIC_LISTS_ENABLED':'YES','SOCIALMEI_MENU_WAHA_ENGINE':'GOWS'}

    def packet(self,b):
        p=payload(session=b.session,me={'id':b.account_id},engine=b.engine)
        p['payload']['to']=b.account_id
        return raw(p)

    def test_nondefault_workspace_requires_full_review_and_malformed_values_close_pilot(self):
        for changes in [{'SOCIALMEI_WAHA_PILOT_BINDING_SHA256':''},
                        {'SOCIALMEI_WAHA_PILOT_BINDING_SHA256':'invalid'},
                        *[{'SOCIALMEI_WAHA_PILOT_WORKSPACE_ID':v} for v in ['0','-1','true',' 60','9007199254740992']]]:
            with self.subTest(changes=changes),patch.dict(os.environ,{**self.env,**changes}):
                self.assertFalse(settings.waha_ingress_team_pilot_enabled())
                self.assertFalse(settings.whatsapp_bot_public_inbound_enabled())

    def test_exact_binding_reaches_persistence_but_every_changed_field_stops_before_database(self):
        b=self.binding
        with patch.dict(os.environ,self.env),patch('waha_ingress.connect',side_effect=AssertionError('verified DB boundary')) as db:
            self.assertTrue(settings.waha_inbox_enabled(60))
            self.assertFalse(settings.waha_inbox_enabled(1))
            self.assertFalse(settings.waha_inbox_enabled(61))
            packet=self.packet(b)
            with self.assertRaisesRegex(AssertionError,'verified DB boundary'):
                WahaIngressService({b.instance:b}).receive(b.instance,packet,sign(packet),'sha512')
            db.reset_mock()
            for change in [{'workspace_id':1},{'channel_id':3},{'revision':3},{'account_id':'551188885976@c.us'},
                           {'instance':'other'},{'session':'other'},{'engine':'WEBJS'}]:
                other=replace(b,**change);packet=self.packet(other)
                with self.subTest(change=change),self.assertRaises(HTTPException) as error:
                    WahaIngressService({other.instance:other}).receive(other.instance,packet,sign(packet),'sha512')
                self.assertEqual(error.exception.status_code,503)
            db.assert_not_called()

    def test_native_lists_and_worker_token_require_same_reviewed_generation(self):
        b=self.binding
        row={'workspace_id':60,'channel_id':2,'instancia':b.instance,'sessao':b.session,
             'identificador_conta':b.account_id,'versao':2}
        with patch.dict(os.environ,self.env):
            self.assertTrue(whatsapp_bot.native_list_canary(row,'waha:222@c.us'))
            self.assertFalse(whatsapp_bot.native_list_canary({**row,'workspace_id':61},'waha:222@c.us'))
            self.assertFalse(whatsapp_bot.native_list_canary(row,'waha:group@g.us'))
            db=Mock();row['binding_hash']=whatsapp_bot.binding_hash(row);db.execute.return_value.fetchone.return_value=row
            request=SimpleNamespace(headers=Headers({'authorization':'Bearer '+'a'*64}))
            self.assertEqual(whatsapp_bot.authorize(db,request)['workspace_id'],60)
            old={**row,'workspace_id':1};old['binding_hash']=whatsapp_bot.binding_hash(old)
            db.execute.return_value.fetchone.return_value=old
            with self.assertRaises(HTTPException) as error:whatsapp_bot.authorize(db,request)
            self.assertEqual(error.exception.status_code,401)

    def test_human_sender_wrong_workspace_and_receive_only_mode_remain_closed(self):
        with patch.dict(os.environ,{**self.env,'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED':'true',
                                    'SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID':'1'}):
            with self.assertRaises(ValueError):settings.whatsapp_human_configuration()
        with patch.dict(os.environ,{**self.env,'SOCIALMEI_WAHA_INGRESS_MODE':'workspace-inbox',
                                    'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED':'true'}):
            self.assertIsNone(settings.whatsapp_human_configuration())
            self.assertFalse(whatsapp_bot.enabled())
            self.assertFalse(settings.whatsapp_bot_public_inbound_enabled())


if __name__=='__main__':unittest.main()
