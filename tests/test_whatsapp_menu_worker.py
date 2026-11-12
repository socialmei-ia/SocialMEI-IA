import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
import httpx

spec = importlib.util.spec_from_file_location('menu_worker', Path(__file__).resolve().parents[1] / 'tools/whatsapp-menu-worker.py')
worker = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)


class ContinuousWorkerTests(unittest.TestCase):
    def gows_attempt(self, *, timeout=False, changed_after_claim=False, native=False, unapproved=False):
        cfg=worker.Config('trusted-a','01','111@c.us','synthetic-token-123456','synthetic-waha-key-123456',
                          'GOWS',worker.GOWS_URL, '222@c.us' if native and not unapproved else '')
        calls=[]
        versions=[]
        receipt=[]
        op='12345678-1234-1234-1234-123456789abc'
        def handler(request):
            calls.append((request.method,str(request.url)))
            path=request.url.path
            if path==worker.SOURCE_URL:
                result={'sources':[{'instance':'trusted-a','external_message_id':'synthetic-message'}]}
            elif path.endswith('/decisions'): result={'operation_id':op,'status':'planned'}
            elif path=='/api/version':
                versions.append(1)
                result={'engine':'WEBJS' if changed_after_claim and len(versions)==2 else 'GOWS'}
            elif path=='/api/sessions/01': result={'name':'01','status':'WORKING','me':{'id':'111@c.us'}}
            elif path.endswith('/claim'):
                result={'dispatch_allowed':True,'delivery':{'path':'/api/sendText','body':{
                    'session':'01','chatId':'222@c.us','text':'Synthetic menu'}}}
                if native:
                    result['delivery'] = {'path':'/api/sendList','body':{
                        'session':'01','chatId':'222@c.us','message':{
                            'title':'Atendimento','description':'Menu sint?tico','footer':'SocialMEI',
                            'button':'Ver op??es','sections':[{'title':'Escolha','rows':[
                                {'rowId':'1','title':'Produtos','description':None}]}]}}}
            elif path in {'/api/sendText', '/api/sendList'}:
                if timeout: raise httpx.ReadTimeout('synthetic timeout',request=request)
                result={'id':'synthetic-provider-receipt'}
            elif path.endswith('/receipt'):
                import json
                receipt.append(json.loads(request.content))
                result={'status':receipt[-1]['status']}
            else: raise AssertionError('Unexpected request')
            return httpx.Response(200,json=result)
        def client(**kwargs): return httpx.Client(transport=httpx.MockTransport(handler),**kwargs)
        return worker.run_once(cfg,client_factory=client),calls,receipt

    def test_gows_canary_list_is_sent_once_with_one_receipt(self):
        result,calls,receipts=self.gows_attempt(native=True)
        self.assertEqual(result,'ENVIO_CONFIRMADO')
        self.assertEqual(sum(method=='POST' and url.endswith('/api/sendList') for method,url in calls),1)
        self.assertFalse(any(url.endswith('/api/sendText') for _,url in calls))
        self.assertEqual(receipts,[{'status':'confirmed','provider_message_id':'synthetic-provider-receipt'}])

    def test_gows_canary_timeout_never_falls_back_to_another_send(self):
        result,calls,receipts=self.gows_attempt(native=True,timeout=True)
        self.assertEqual(result,'RESULTADO_INCERTO_NAO_REENVIAR')
        self.assertEqual(sum(method=='POST' and url.endswith('/api/sendList') for method,url in calls),1)
        self.assertFalse(any(url.endswith('/api/sendText') for _,url in calls))
        self.assertEqual(receipts,[{'status':'uncertain','provider_message_id':None}])

    def test_native_list_is_denied_without_explicit_canary_contact(self):
        result,calls,receipts=self.gows_attempt(native=True,unapproved=True)
        self.assertEqual(result,'RESULTADO_INCERTO_NAO_REENVIAR')
        self.assertFalse(any(url.endswith(('/api/sendList','/api/sendText')) for _,url in calls))

    def test_native_list_rejects_other_contact_duplicate_options_and_arbitrary_action(self):
        import copy
        cfg=worker.Config('trusted-a','01','111@c.us','synthetic-token-123456',
                          'synthetic-waha-key-123456','GOWS',worker.GOWS_URL,'222@c.us')
        good={'path':'/api/sendList','body':{'session':'01','chatId':'222@c.us','message':{
              'title':'Atendimento','description':'Menu','footer':'SocialMEI','button':'Ver op??es',
              'sections':[{'title':'Escolha','rows':[{'rowId':'1','title':'Produtos','description':None}]}]}}}
        self.assertEqual(worker._delivery(good,cfg)['chatId'],'222@c.us')
        wrong=copy.deepcopy(good);wrong['body']['chatId']='333@c.us'
        duplicate=copy.deepcopy(good);duplicate['body']['message']['sections'][0]['rows'] *= 2
        action=copy.deepcopy(good);action['body']['message']['sections'][0]['rows'][0]['rowId']='external-action'
        malformed=copy.deepcopy(good);malformed['body']['message']['sections'][0]['rows'][0]['rowId']=[]
        for sample in [wrong,duplicate,action,malformed]:
            with self.assertRaises(worker.Blocked):worker._delivery(sample,cfg)
        with self.assertRaises(worker.Blocked):
            worker.Config('trusted-a','default','111@c.us','synthetic-token-123456',
                          'synthetic-waha-key-123456',native_list_contact='222@c.us')

    def test_gows_success_uses_only_selected_provider_and_records_one_receipt(self):
        result,calls,receipts=self.gows_attempt()
        self.assertEqual(result,'ENVIO_CONFIRMADO')
        self.assertEqual(sum(method=='POST' and url==worker.GOWS_URL+'/api/sendText' for method,url in calls),1)
        self.assertFalse(any(url.startswith(worker.WAHA_URL+'/') for _,url in calls))
        self.assertEqual(receipts,[{'status':'confirmed','provider_message_id':'synthetic-provider-receipt'}])

    def test_gows_timeout_is_uncertain_without_second_send(self):
        result,calls,receipts=self.gows_attempt(timeout=True)
        self.assertEqual(result,'RESULTADO_INCERTO_NAO_REENVIAR')
        self.assertEqual(sum(method=='POST' and url.endswith('/api/sendText') for method,url in calls),1)
        self.assertEqual(receipts,[{'status':'uncertain','provider_message_id':None}])

    def test_gows_engine_change_after_claim_prevents_provider_post(self):
        result,calls,receipts=self.gows_attempt(changed_after_claim=True)
        self.assertEqual(result,'RESULTADO_INCERTO_NAO_REENVIAR')
        self.assertFalse(any(method=='POST' and url.endswith('/api/sendText') for method,url in calls))
        self.assertEqual(receipts,[{'status':'uncertain','provider_message_id':None}])

    def test_gows_requires_explicit_private_target_and_session(self):
        webjs = worker.Config('trusted-a', 'default', '111@c.us',
                              'synthetic-token-123456', 'synthetic-waha-key-123456')
        self.assertEqual(webjs.engine, 'WEBJS')
        self.assertEqual(webjs.waha_url, worker.WAHA_URL)
        gows = worker.Config('trusted-a', '01', '111@c.us',
                             'synthetic-token-123456', 'synthetic-waha-key-123456',
                             'GOWS', worker.GOWS_URL)
        self.assertEqual(gows.engine, 'GOWS')
        for engine, url, session in [
            ('GOWS', worker.WAHA_URL, '01'),
            ('GOWS', worker.GOWS_URL, 'default'),
            ('WEBJS', worker.GOWS_URL, 'default'),
        ]:
            with self.subTest(engine=engine, url=url, session=session):
                with self.assertRaises(worker.Blocked):
                    worker.Config('trusted-a', session, '111@c.us',
                                  'synthetic-token-123456', 'synthetic-waha-key-123456',
                                  engine, url)

    def test_gows_engine_mismatch_never_claims_or_sends(self):
        cfg = worker.Config('trusted-a', '01', '111@c.us',
                            'synthetic-token-123456', 'synthetic-waha-key-123456',
                            'GOWS', worker.GOWS_URL)
        api, provider = Mock(), Mock()
        for client in (api, provider):
            client.__enter__ = Mock(return_value=client)
            client.__exit__ = Mock(return_value=False)
        api.request.side_effect = [
            httpx.Response(200, json={'sources': [
                {'instance': 'trusted-a', 'external_message_id': 'test-message'}]}),
            httpx.Response(200, json={'operation_id': '12345678-1234-1234-1234-123456789abc',
                                      'status': 'planned'}),
        ]
        provider.request.return_value = httpx.Response(200, json={'engine': 'WEBJS'})
        with self.assertRaises(worker.Blocked):
            worker.run_once(cfg, client_factory=Mock(side_effect=[api, provider]))
        self.assertEqual(provider.request.call_count, 1)
        self.assertEqual(provider.request.call_args.args[1], worker.GOWS_URL + '/api/version')
        self.assertEqual(api.request.call_count, 2)
        self.assertTrue(all(call.args[0] != 'POST' or call.args[1].endswith('/decisions')
                            for call in api.request.call_args_list))

    def test_bounded_window_stops_new_polls_and_sends(self):
        poll = Mock(return_value='SEM_MENSAGENS_NOVAS')
        sleep = Mock()
        clock = Mock(side_effect=[100, 100, 101])
        with patch('builtins.print'):
            self.assertEqual(worker.run_continuously(object(), poll=poll, sleep=sleep,
                                                     max_seconds=1, clock=clock), 0)
        self.assertEqual(poll.call_count, 1)

    def test_unavailable_source_does_not_resume_after_window_expires(self):
        poll = Mock(side_effect=worker.SourceUnavailable())
        clock = Mock(side_effect=[100, 100, 160])
        with patch('builtins.print'):
            result = worker.run_continuously(object(), poll=poll, sleep=Mock(),
                                            max_seconds=30, clock=clock)
        self.assertEqual(result, 0)
        self.assertEqual(poll.call_count, 1)

    def test_only_source_transport_or_server_failure_is_retry_safe(self):
        config = worker.Config('isolated-instance', 'fixture', '111@c.us',
                               'isolated-token-for-test', 'isolated-key-for-test')
        for status, error in ((503, worker.SourceUnavailable), (403, worker.Blocked)):
            with self.subTest(status=status):
                api, provider = Mock(), Mock()
                api.__enter__ = Mock(return_value=api)
                api.__exit__ = Mock(return_value=False)
                provider.__enter__ = Mock(return_value=provider)
                provider.__exit__ = Mock(return_value=False)
                api.request.return_value = httpx.Response(status, json={'detail': 'unavailable'})
                factory = Mock(side_effect=[api, provider])
                with self.assertRaises(error) as raised:
                    worker.run_once(config, client_factory=factory)
                if status == 403:
                    self.assertNotIsInstance(raised.exception, worker.SourceUnavailable)
                self.assertEqual(api.request.call_count, 1)
                self.assertEqual(api.request.call_args.args[0], 'GET')
                provider.request.assert_not_called()

    def test_source_failure_backs_off_and_recovers_before_any_dispatch(self):
        poll = Mock(side_effect=[worker.SourceUnavailable(), worker.SourceUnavailable(),
                                 'SEM_MENSAGENS_NOVAS', 'RESULTADO_INCERTO_NAO_REENVIAR'])
        sleep = Mock()
        with patch('builtins.print'):
            self.assertEqual(worker.run_continuously(object(), poll=poll, sleep=sleep), 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [15, 30, 3])

    def test_unknown_failure_after_source_does_not_retry(self):
        poll = Mock(side_effect=worker.Blocked('Receipt unavailable'))
        sleep = Mock()
        with patch('builtins.print'):
            self.assertEqual(worker.run_continuously(object(), poll=poll, sleep=sleep), 3)
        self.assertEqual(poll.call_count, 1)
        sleep.assert_not_called()

    def test_default_entrypoint_never_sends(self):
        with patch.object(worker.Config, 'from_env') as config, patch('builtins.print'):
            self.assertEqual(worker.main([]), 0)
        config.assert_not_called()

    def test_continuous_uncertainty_stays_paused_instead_of_triggering_restart(self):
        with patch.object(worker.Config, 'from_env'), patch.object(worker, 'run_continuously', return_value=2) as run, patch.object(worker.time, 'sleep', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                worker.main(['--continuous'])
        run.assert_called_once()
