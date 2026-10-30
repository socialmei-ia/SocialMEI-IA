"""Team pilot contracts use synthetic signed fixtures, never a provider."""
import os
import unittest
from unittest.mock import patch
from fastapi import HTTPException
import settings
from waha_ingress import WahaBinding, WahaIngressService
from test_waha_ingress import payload, raw, sign, KEY

FLAGS = {
    'SOCIALMEI_AUTH_ENABLED': 'true',
    'SOCIALMEI_SHARED_DATA_ENABLED': 'true',
    'SOCIALMEI_WAHA_INGRESS_MODE': 'team-pilot',
    'SOCIALMEI_WAHA_LAB_ENVIRONMENT': 'team-pilot',
    'SOCIALMEI_WAHA_REGISTRY_FILE': '/run/socialmei/private/waha-registry.json',
}


def binding(**updates):
    values = dict(instance='socialmei-equipe-piloto', session='default',
                  account_id='551199995976@c.us', workspace_id=1, channel_id=2,
                  hmac_key=KEY, revision=1)
    values.update(updates)
    return WahaBinding(**values)


class TeamPilotTests(unittest.TestCase):
    def test_explicit_configuration_required_and_isolated_contract_unchanged(self):
        with patch.dict(os.environ, FLAGS):
            self.assertTrue(settings.waha_ingress_team_pilot_enabled())
            self.assertTrue(settings.waha_ingress_enabled())
            self.assertFalse(settings.waha_ingress_isolated_enabled())
            for field, value in (
                ('SOCIALMEI_AUTH_ENABLED', 'false'),
                ('SOCIALMEI_SHARED_DATA_ENABLED', 'false'),
                ('SOCIALMEI_WAHA_INGRESS_MODE', 'enabled'),
                ('SOCIALMEI_WAHA_LAB_ENVIRONMENT', 'isolated'),
                ('SOCIALMEI_WAHA_REGISTRY_FILE', '/tmp/public.json'),
            ):
                with self.subTest(field=field), patch.dict(os.environ, {field: value}):
                    self.assertFalse(settings.waha_ingress_team_pilot_enabled())
                    self.assertFalse(settings.waha_ingress_enabled())
        with patch.dict(os.environ, {**FLAGS, 'SOCIALMEI_WAHA_INGRESS_MODE':'isolated', 'SOCIALMEI_WAHA_LAB_ENVIRONMENT':'isolated'}):
            self.assertTrue(settings.waha_ingress_isolated_enabled())
            self.assertTrue(settings.waha_ingress_enabled())
            self.assertFalse(settings.waha_ingress_team_pilot_enabled())

    def test_pilot_rejects_other_workspace_account_alias_before_database(self):
        with patch.dict(os.environ, FLAGS), patch('waha_ingress.connect') as database:
            for updates in ({'workspace_id':2}, {'account_id':'551199991234@c.us'}, {'instance':'other'}):
                item = binding(**updates)
                service = WahaIngressService({item.instance:item})
                event = payload(session=item.session, me={'id':item.account_id})
                event['payload']['to'] = item.account_id
                body = raw(event)
                with self.subTest(updates=updates), self.assertRaises(HTTPException) as error:
                    service.receive(item.instance, body, sign(body), 'sha512')
                self.assertEqual(error.exception.status_code, 503)
            database.assert_not_called()

    def test_pilot_signature_session_and_account_are_required_before_database(self):
        item = binding()
        service = WahaIngressService({item.instance:item})
        with patch.dict(os.environ, FLAGS), patch('waha_ingress.connect') as database:
            for event, signature in (
                (payload(me={'id':item.account_id}), '0'*128),
                (payload(session='other', me={'id':item.account_id}), None),
                (payload(me={'id':'551199991234@c.us'}), None),
                (payload(me={'id':item.account_id}, workspace_id=2), None),
            ):
                body=raw(event)
                with self.assertRaises(HTTPException):
                    service.receive(item.instance, body, signature or sign(body), 'sha512')
            database.assert_not_called()

    def test_pilot_exact_signed_binding_reaches_existing_persistence(self):
        item=binding()
        event=payload(me={'id':item.account_id})
        event['payload']['to']=item.account_id
        body=raw(event)
        with patch.dict(os.environ,FLAGS), patch('waha_ingress.connect', side_effect=AssertionError('Reached DB')) as database:
            with self.assertRaisesRegex(AssertionError,'Reached DB'):
                WahaIngressService({item.instance:item}).receive(item.instance,body,sign(body),'sha512')
            database.assert_called_once()

    def test_inbox_capability_is_scoped_to_team_and_does_not_enable_sender(self):
        from unittest.mock import Mock
        from fastapi import Response
        import message_enrichment as inbox
        request=Mock(method='GET', query_params={})
        with patch.dict(os.environ, FLAGS), patch.object(inbox,'require_enabled'), patch.object(inbox.settings,'message_enrichment_mode',return_value='disabled'):
            for workspace, allowed in ((1,True),(2,False)):
                with self.subTest(workspace=workspace), patch.object(inbox,'current',return_value={'workspace_id':workspace,'role':'owner'}):
                    value=inbox.capabilities(request,Response())
                    self.assertEqual(value.get('waha_inbox',False),allowed)
                    self.assertNotIn('waha_send',value)
                    self.assertEqual(settings.waha_inbox_enabled(workspace),allowed)
                    if allowed:
                        self.assertEqual(inbox.guard(request,Response(),read_inbox=True)['workspace_id'],1)
                    else:
                        with self.assertRaises(HTTPException) as error:
                            inbox.guard(request,Response(),read_inbox=True)
                        self.assertEqual(error.exception.status_code,503)

    def test_pilot_registry_requires_root_owned_file_even_for_current_service_user(self):
        import json
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        import waha_ingress
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'private.json'
            entry=binding()
            path.write_text(json.dumps({'version':1,'bindings':[{
                'instance':entry.instance,'session':entry.session,
                'account_id':entry.account_id,'workspace_id':1,'channel_id':2,
                'hmac_key':KEY,'revision':1}]}))
            path.chmod(0o600)
            metadata=path.stat()
            foreign=SimpleNamespace(st_mode=metadata.st_mode,st_size=metadata.st_size,st_uid=1000)
            with patch.dict(os.environ,{'SOCIALMEI_WAHA_REGISTRY_FILE':str(path)}), patch.object(waha_ingress.settings,'waha_ingress_team_pilot_enabled',return_value=True), patch.object(waha_ingress.os,'geteuid',return_value=1000), patch.object(waha_ingress.os,'fstat',return_value=foreign):
                with self.assertRaises(HTTPException) as error:
                    waha_ingress.waha_service()
                self.assertEqual(error.exception.status_code,503)
                self.assertNotIn(KEY,str(error.exception))


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class TeamPilotPersistenceTests(unittest.TestCase):
    def test_signed_message_is_durable_deduplicated_and_only_visible_to_team(self):
        import json
        from uuid import uuid4
        from unittest.mock import Mock
        import psycopg
        from fastapi import Response
        import message_enrichment as inbox
        import test_instagram_simulation as fixtures
        fixtures.DatabaseTests.setUpClass()
        database=os.environ['TEST_DATABASE_URL']
        item=binding()
        key=uuid4().hex
        created_team=False
        other=None
        channel=None
        try:
            with psycopg.connect(database) as conn:
                if not conn.execute('SELECT id FROM socialmei.workspaces WHERE id=1').fetchone():
                    conn.execute("INSERT INTO socialmei.workspaces(id,slug,nome) VALUES(1,%s,'Pilot test')",('pilot-team-'+key,))
                    created_team=True
                other=conn.execute("INSERT INTO socialmei.workspaces(slug,nome) VALUES(%s,'Other test') RETURNING id",('pilot-other-'+key,)).fetchone()[0]
                channel=conn.execute('INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ativo,ingress_provisioned) VALUES(1,%s,%s,%s,true,true) RETURNING id',(item.instance,item.session,item.account_id)).fetchone()[0]
            item=binding(channel_id=channel)
            event=payload('pilot-'+key,me={'id':item.account_id})
            event['payload']['to']=item.account_id
            event['payload']['body']='Consulta de catálogo sintética '+key
            body=raw(event)
            with patch.dict(os.environ,{**FLAGS,'DATABASE_URL':database,'SOCIALMEI_MESSAGE_ENRICHMENT_MODE':'disabled'}):
                service=WahaIngressService({item.instance:item})
                self.assertEqual(service.receive(item.instance,body,sign(body),'sha512')['processed'],1)
                # Recreate service to prove deduplication is persisted, not process-local.
                restarted=WahaIngressService({item.instance:item})
                self.assertEqual(restarted.receive(item.instance,body,sign(body),'sha512')['duplicates'],1)
                request=Mock(method='GET',query_params={})
                with patch.object(inbox,'require_enabled'), patch.object(inbox,'current',return_value={'workspace_id':1,'role':'owner'}):
                    result=inbox.conversations(request,Response())
                    self.assertIn(event['payload']['body'],json.dumps(result,default=str,ensure_ascii=False))
                # Even with another provider enabling read for the other workspace,
                # the SQL is still workspace scoped and cannot expose this message.
                with patch.object(inbox,'require_enabled'), patch.object(inbox,'current',return_value={'workspace_id':other,'role':'owner'}), patch.object(inbox.settings,'instagram_live_ingress_enabled',return_value=True):
                    result=inbox.conversations(request,Response())
                    self.assertNotIn(event['payload']['body'],json.dumps(result,default=str,ensure_ascii=False))
                with psycopg.connect(database) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.crm_eventos_canal WHERE workspace_id=1 AND canal_id=%s',(channel,)).fetchone()[0],1)
        finally:
            with psycopg.connect(database) as conn:
                if channel is not None:
                    conn.execute('DELETE FROM socialmei.crm_eventos_canal WHERE workspace_id=1 AND canal_id=%s',(channel,))
                    conn.execute('DELETE FROM socialmei.me_conversations WHERE workspace_id=1 AND account_ref=%s',('waha:'+item.account_id,))
                    conn.execute('DELETE FROM socialmei.crm_canais WHERE workspace_id=1 AND id=%s',(channel,))
                if other is not None:
                    conn.execute('DELETE FROM socialmei.workspaces WHERE id=%s',(other,))
                if created_team:
                    conn.execute('DELETE FROM socialmei.workspaces WHERE id=1')
