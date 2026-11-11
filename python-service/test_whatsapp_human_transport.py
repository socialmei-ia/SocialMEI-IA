"""Private WAHA transport policy and bounded HTTP; all network calls are mocked."""
import io
import json
import logging
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

import httpx

import settings
from whatsapp_human_outbox import reply_service
from whatsapp_human_transport import WahaHumanTransport, WahaPolicyError, WahaTransportError

ENV = {
    'SOCIALMEI_AUTH_ENABLED': 'true',
    'SOCIALMEI_SHARED_DATA_ENABLED': 'true',
    'SOCIALMEI_WAHA_INGRESS_MODE': 'isolated',
    'SOCIALMEI_WAHA_LAB_ENVIRONMENT': 'isolated',
    'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED': 'true',
    'SOCIALMEI_WHATSAPP_HUMAN_OWNER': 'dashboard',
    'SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID': '7',
    'SOCIALMEI_WHATSAPP_HUMAN_INSTANCE': 'trusted-a',
    'SOCIALMEI_WHATSAPP_HUMAN_SESSION': 'default',
    'SOCIALMEI_WHATSAPP_HUMAN_ACCOUNT_ID': '111@c.us',
    'SOCIALMEI_WHATSAPP_HUMAN_CONTACTS': '["222@c.us","contact.primary@lid"]',
    'SOCIALMEI_WAHA_PRIVATE_BASE_URL': 'http://waha:3000',
    'SOCIALMEI_WAHA_PRIVATE_API_KEY': 'synthetic-private-api-key-123456789',
}


class HumanTransportTests(unittest.TestCase):
    def test_public_inbound_policy_keeps_workspace_and_account_guards(self):
        with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_HUMAN_PUBLIC_INBOUND_ENABLED': 'true'}):
            config = settings.whatsapp_human_configuration()
        transport = WahaHumanTransport(config)
        item = dict(workspace_id=7, instancia='trusted-a', sessao='default',
                    identificador_conta='111@c.us', contact_ref='waha:333@c.us')
        transport.validate_scope(item)
        for update in [dict(workspace_id=8), dict(identificador_conta='999@c.us'),
                       dict(contact_ref='waha:group@g.us')]:
            with self.assertRaises(WahaPolicyError):
                transport.validate_scope({**item, **update})

    def setUp(self):
        environment = patch.dict(os.environ, ENV, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.configuration = settings.whatsapp_human_configuration()
        self.calls = []
        self.delivery = {'path': '/api/sendText', 'body': {
            'session': 'default', 'chatId': '222@c.us', 'text': 'Resposta privada de teste',
        }}

    def transport(self, handler, **kwargs):
        def factory(**options):
            self.assertIs(options['follow_redirects'], False)
            self.assertIs(options['trust_env'], False)
            self.assertLessEqual(options['timeout'].connect, 2)
            def record(request):
                self.calls.append(request)
                return handler(request)
            return httpx.Client(transport=httpx.MockTransport(record), **options)
        return WahaHumanTransport(self.configuration, client_factory=factory, **kwargs)

    def session(self, **updates):
        return {'name': 'default', 'status': 'WORKING', 'me': {'id': '111@c.us'}, **updates}

    def test_configuration_and_service_do_not_make_startup_requests_and_hide_secrets(self):
        with patch('whatsapp_human_transport.WahaHumanTransport.__call__', side_effect=AssertionError('no startup I/O')):
            service = reply_service()
        self.assertTrue(service.can_send(7))
        self.assertFalse(service.can_send(8))
        for value in (repr(self.configuration), repr(service.transport)):
            self.assertNotIn(ENV['SOCIALMEI_WAHA_PRIVATE_API_KEY'], value)
            self.assertNotIn('111@c.us', value)
            self.assertNotIn('contact.primary@lid', value)

    def test_unconfigured_and_malformed_enabled_values_remain_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(settings.whatsapp_human_configuration())
            self.assertFalse(reply_service().send_enabled)
        for flag in ('false', 'false ', 'treu', '', '1'):
            with patch.dict(os.environ, {'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED': flag}):
                self.assertIsNone(settings.whatsapp_human_configuration())
                self.assertFalse(reply_service().send_enabled)

    def test_incomplete_or_unsafe_server_configuration_fails_closed(self):
        for key, bad in (
            ('SOCIALMEI_WHATSAPP_HUMAN_OWNER', 'n8n'),
            ('SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID', '0'),
            ('SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID', '9007199254740992'),
            ('SOCIALMEI_WHATSAPP_HUMAN_WORKSPACE_ID', ' 7'),
            ('SOCIALMEI_WHATSAPP_HUMAN_INSTANCE', '../other'),
            ('SOCIALMEI_WHATSAPP_HUMAN_SESSION', 'default/other'),
            ('SOCIALMEI_WHATSAPP_HUMAN_ACCOUNT_ID', 'other@lid'),
            ('SOCIALMEI_WHATSAPP_HUMAN_CONTACTS', '[]'),
            ('SOCIALMEI_WHATSAPP_HUMAN_CONTACTS', '["222@c.us","bad"]'),
            ('SOCIALMEI_WHATSAPP_HUMAN_CONTACTS', '["222@c.us","222@c.us"]'),
            ('SOCIALMEI_WHATSAPP_HUMAN_CONTACTS', '"222@c.us"'),
            ('SOCIALMEI_WAHA_PRIVATE_BASE_URL', 'https://waha:3000'),
            ('SOCIALMEI_WAHA_PRIVATE_BASE_URL', 'http://127.0.0.1:3000'),
            ('SOCIALMEI_WAHA_PRIVATE_BASE_URL', 'http://waha:3000/'),
            ('SOCIALMEI_WAHA_PRIVATE_BASE_URL', 'http://waha:3000@evil.example'),
            ('SOCIALMEI_WAHA_PRIVATE_API_KEY', 'secret\r\nInjected:value'),
            ('SOCIALMEI_AUTH_ENABLED', 'false'),
            ('SOCIALMEI_SHARED_DATA_ENABLED', 'false'),
            ('SOCIALMEI_WAHA_INGRESS_MODE', 'disabled'),
        ):
            with self.subTest(key=key, bad=bad), patch.dict(os.environ, {key: bad}):
                with self.assertRaises(ValueError) as failure:
                    settings.whatsapp_human_configuration()
                self.assertNotIn(ENV['SOCIALMEI_WAHA_PRIVATE_API_KEY'], str(failure.exception))
                self.assertFalse(reply_service().send_enabled)

    def test_scope_policy_covers_workspace_channel_identity_and_exact_contact(self):
        transport = self.transport(lambda _: self.fail('policy never performs HTTP'))
        allowed = {'workspace_id': 7, 'instancia': 'trusted-a', 'sessao': 'default',
                   'identificador_conta': '111@c.us', 'contact_ref': 'waha:222@c.us'}
        transport.validate_scope(allowed)
        transport.validate_scope({**allowed, 'contact_ref': 'waha:contact.primary@lid'})
        for update in ({'workspace_id': 8}, {'instancia': 'other'}, {'sessao': 'other'},
                       {'identificador_conta': '333@c.us'}, {'contact_ref': 'waha:333@c.us'},
                       {'contact_ref': '222@c.us'}):
            with self.subTest(update=update), self.assertRaises(WahaPolicyError):
                transport.validate_scope({**allowed, **update})
        self.assertEqual(self.calls, [])

    def test_one_checked_session_then_one_send_with_canonical_receipt(self):
        def handler(request):
            self.assertEqual(request.url.host, 'waha')
            self.assertEqual(request.headers['x-api-key'], ENV['SOCIALMEI_WAHA_PRIVATE_API_KEY'])
            if request.method == 'GET':
                self.assertEqual(request.url.path, '/api/sessions/default')
                return httpx.Response(200, json=self.session())
            self.assertEqual(request.method, 'POST')
            self.assertEqual(request.url.path, '/api/sendText')
            self.assertEqual(json.loads(request.content), self.delivery['body'])
            return httpx.Response(201, json={'id': 'provider-fixture-id'})
        self.assertEqual(self.transport(handler)(self.delivery), 'provider-fixture-id')
        self.assertEqual([r.method for r in self.calls], ['GET', 'POST'])

    def test_webjs_serialized_receipt_and_lid_destination_are_supported(self):
        self.delivery['body']['chatId'] = 'contact.primary@lid'
        result = self.transport(lambda request: httpx.Response(200, json=(
            self.session() if request.method == 'GET' else {'id': {'_serialized': 'webjs-fixture'}}
        )))(self.delivery)
        self.assertEqual(result, 'webjs-fixture')
        self.assertEqual(json.loads(self.calls[-1].content)['chatId'], 'contact.primary@lid')

    def test_stopped_or_rebound_session_never_sends(self):
        for value in (self.session(status='STOPPED'), self.session(me={'id': '333@c.us'}),
                      self.session(name='other'), self.session(me=None)):
            self.calls.clear()
            with self.subTest(value=value), self.assertRaises(WahaTransportError):
                self.transport(lambda _: httpx.Response(200, json=value))(self.delivery)
            self.assertEqual([r.method for r in self.calls], ['GET'])

    def test_redirects_never_followed_on_get_or_post(self):
        for redirect_method in ('GET', 'POST'):
            self.calls.clear()
            def handler(request):
                if request.method == redirect_method:
                    return httpx.Response(302, headers={'location': 'http://evil.example/private'})
                return httpx.Response(200, json=self.session())
            with self.subTest(method=redirect_method), self.assertRaises(WahaTransportError):
                self.transport(handler)(self.delivery)
            self.assertEqual([r.method for r in self.calls], ['GET'] if redirect_method == 'GET' else ['GET', 'POST'])

    def test_unauthorized_delivery_is_rejected_before_any_http(self):
        transport = self.transport(lambda _: self.fail('unauthorized request'))
        for update in ({'path': '/api/logout'}, {'url': 'http://evil.example'},
                       {'body': {**self.delivery['body'], 'session': 'other'}},
                       {'body': {**self.delivery['body'], 'chatId': '333@c.us'}},
                       {'body': {**self.delivery['body'], 'text': 'á' * 2049}},
                       {'body': {**self.delivery['body'], 'extra': 'unsafe'}}):
            with self.subTest(update=update), self.assertRaises(WahaPolicyError):
                transport({**self.delivery, **update})
        self.assertEqual(self.calls, [])

    def test_oversized_invalid_or_ambiguous_receipt_is_sanitized_without_retry(self):
        for response in (
            httpx.Response(200, json={'id': 'x' * 1025}),
            httpx.Response(200, content=b'{"id":"first","id":"second"}', headers={'content-type': 'application/json'}),
            httpx.Response(200, content=b'x' * 8193, headers={'content-type': 'application/json'}),
            httpx.Response(200, json={'private-token': 'private-response-body'}),
            httpx.Response(500, json={'private': 'private-response-body'}),
            httpx.Response(200, content=b'<private-response-body>', headers={'content-type': 'text/html'}),
        ):
            self.calls.clear()
            with self.subTest(status=response.status_code), self.assertRaises(WahaTransportError) as failure:
                self.transport(lambda request: httpx.Response(200, json=self.session())
                               if request.method == 'GET' else response)(self.delivery)
            self.assertNotIn('private-response-body', str(failure.exception))
            self.assertEqual([r.method for r in self.calls], ['GET', 'POST'])

    def test_timeout_and_private_http_logs_do_not_leak_or_retry(self):
        def handler(request):
            logging.getLogger('httpx').warning('private-message-and-key')
            if request.method == 'GET':
                return httpx.Response(200, json=self.session())
            raise httpx.ReadTimeout('private-message-and-key', request=request)
        output = io.StringIO()
        logger = logging.getLogger('httpx')
        capture = logging.StreamHandler(output)
        logger.addHandler(capture)
        self.addCleanup(logger.removeHandler, capture)
        with self.assertRaises(WahaTransportError) as failure:
            self.transport(handler)(self.delivery)
        self.assertNotIn('private-message-and-key', str(failure.exception))
        self.assertEqual(output.getvalue(), '')
        self.assertEqual([r.method for r in self.calls], ['GET', 'POST'])

    def test_even_injected_configuration_cannot_override_private_destination(self):
        with self.assertRaises(WahaPolicyError):
            WahaHumanTransport(replace(self.configuration, base_url='http://evil.example'))
