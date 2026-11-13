"""Bounded WAHA management contracts; no real pairing, sending or provider access."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from dataclasses import replace
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from fastapi.testclient import TestClient

from app import app
import settings
import test_account_auth as accounts
import test_waha_ingress as fixtures
from waha_ingress import WahaBinding, WahaIngressService
from whatsapp_human_transport import WahaHumanTransport, WahaTransportError
import whatsapp_connection_management as management

PATH = '/api/v1/whatsapp/connection'


class SessionInspectionContracts(unittest.TestCase):
    def test_read_only_session_probe_requires_exact_private_account(self):
        config = settings.WhatsAppHumanConfiguration(7, 'private-test', 'default', '111@c.us', frozenset(),
                                                   'http://waha:3000', 'synthetic-private-key-never-real')
        calls = []
        def factory(**options):
            self.assertFalse(options['follow_redirects'])
            self.assertFalse(options['trust_env'])
            def handle(request):
                calls.append((request.method, request.url.path))
                return httpx.Response(200, json={'name': 'default', 'status': 'WORKING', 'me': {'id': '111@c.us'}})
            return httpx.Client(transport=httpx.MockTransport(handle), **options)
        self.assertEqual(WahaHumanTransport(config, client_factory=factory).inspect_session(), {'status': 'WORKING'})
        self.assertEqual(calls, [('GET', '/api/sessions/default')])
        with self.assertRaises(WahaTransportError):
            WahaHumanTransport(replace(config, account_id='999@c.us'), client_factory=factory).inspect_session()

    def test_gows_probe_checks_engine_without_enabling_another_session(self):
        config = settings.WhatsAppHumanConfiguration(7, 'private-test', '01', '111@c.us', frozenset(),
            'http://socialmei-waha-gows-piloto:3000', 'synthetic-private-key-never-real', engine='GOWS')
        calls = []
        def factory(**options):
            def handle(request):
                calls.append(request.url.path)
                return httpx.Response(200, json={'engine': 'WEBJS'})
            return httpx.Client(transport=httpx.MockTransport(handle), **options)
        with self.assertRaises(WahaTransportError):
            WahaHumanTransport(config, client_factory=factory).inspect_session()
        self.assertEqual(calls, ['/api/version'])


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class ConnectionManagementDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.flags = patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled',
            'SOCIALMEI_WAHA_MANAGEMENT_ENABLED': 'true', 'SOCIALMEI_WAHA_MANAGEMENT_MAX_SESSIONS': '3',
            'SOCIALMEI_WAHA_MANAGEMENT_PROBE_ENABLED': 'false'})
        self.flags.start(); self.addCleanup(self.flags.stop)
        self.workspace = self.admin_client.identity['negocio']['id']
        self.admin_client.headers['X-SocialMEI-Identity'] = f'{self.admin_id}:{self.workspace}'
        self.bindings = []
        self.registry = patch('whatsapp_connection_management.registry', side_effect=lambda: self.bindings)
        self.registry.start(); self.addCleanup(self.registry.stop)

    def packet(self, **updates):
        return {'operation_id': str(uuid4()), 'expected_revision': 0, 'action': 'connect',
                'confirmed': True, 'phone': '+5581999990000', **updates}

    def request(self, payload, client=None):
        return (client or self.admin_client).post(PATH + '/requests', json=payload)

    def own_binding(self, account='5581999990000@c.us'):
        with psycopg.connect(accounts.DB) as conn:
            channel = conn.execute("INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ingress_provisioned,ativo) VALUES(%s,'managed-test','default',%s,true,true) RETURNING id", (self.workspace, account)).fetchone()[0]
        binding = WahaBinding(instance='managed-test', session='default', account_id=account,
                              workspace_id=self.workspace, channel_id=channel, hmac_key=fixtures.KEY)
        self.bindings.append(binding)
        return binding

    def test_request_is_durable_idempotent_and_not_a_connection(self):
        payload = self.packet()
        first = self.request(payload)
        self.assertEqual(first.status_code, 202, first.text)
        self.assertFalse(first.json()['executed'])
        self.assertEqual(self.request(payload).json(), first.json())
        self.assertEqual(self.request({**payload, 'phone': '+5581999990001'}).status_code, 409)
        value = self.admin_client.get(PATH).json()
        self.assertEqual(value['connection_state'], 'configuration_pending')
        self.assertFalse(value['session_live_verified'])
        self.assertFalse(value['pairing_available'])
        self.assertEqual(value['request']['phone_hint'], '•••• 0000')
        self.assertNotIn('5581999990000', json.dumps(value))
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.crm_canais').fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.auth_auditoria WHERE acao=%s', (f'waha:{self.workspace}:solicitacao',)).fetchone()[0], 1)

    def test_two_businesses_cannot_claim_the_same_number(self):
        other = self.register('second-owner@example.test')
        other.headers['X-SocialMEI-Identity'] = f"{other.identity['usuario']['id']}:{other.identity['negocio']['id']}"
        def submit(client):
            return self.request(self.packet(), client).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(submit, [self.admin_client, other])), [202, 409])
        first = self.admin_client.get(PATH).json()
        second = other.get(PATH).json()
        self.assertNotEqual(first['workspace_id'], second['workspace_id'])
        self.assertEqual(sum(v['request'] is not None for v in [first, second]), 1)

    def test_private_registry_number_and_capacity_cannot_be_bypassed(self):
        own = self.own_binding()
        foreign = self.register('foreign-owner@example.test')
        foreign.headers['X-SocialMEI-Identity'] = f"{foreign.identity['usuario']['id']}:{foreign.identity['negocio']['id']}"
        self.assertEqual(self.request(self.packet(), foreign).status_code, 409)
        with patch.dict(os.environ, {'SOCIALMEI_WAHA_MANAGEMENT_MAX_SESSIONS': '1'}):
            self.assertEqual(self.request(self.packet(phone='+5581999990001'), foreign).status_code, 429)
        self.assertEqual(self.request(self.packet(action='reconnect', phone=None)).status_code, 202)
        self.assertEqual(self.bindings, [own])

    def test_owner_context_and_explicit_consent_are_required(self):
        self.assertEqual(self.request(self.packet(confirmed=False)).status_code, 422)
        self.admin_client.headers['X-SocialMEI-Identity'] = '999:999'
        self.assertEqual(self.request(self.packet()).status_code, 409)
        self.admin_client.headers['X-SocialMEI-Identity'] = f'{self.admin_id}:{self.workspace}'
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='admin' WHERE user_id=%s", (self.admin_id,))
        self.assertEqual(self.admin_client.get(PATH).status_code, 200)
        self.assertEqual(self.request(self.packet()).status_code, 403)

    def test_missing_registry_or_disabled_feature_never_provisions(self):
        with patch('whatsapp_connection_management.registry', return_value=None):
            self.assertEqual(self.request(self.packet()).status_code, 503)
        with patch.dict(os.environ, {'SOCIALMEI_WAHA_MANAGEMENT_ENABLED': 'false'}):
            self.assertEqual(self.request(self.packet()).status_code, 503)
        with patch('whatsapp_human_transport.WahaHumanTransport.inspect_session', side_effect=AssertionError('provider called')):
            self.assertEqual(self.admin_client.get(PATH).status_code, 200)
            self.assertEqual(self.admin_client.post(PATH + '/inspect', json={}).status_code, 503)

    def test_inspection_is_explicit_scoped_and_expires_without_polling(self):
        self.own_binding()
        flags = {'SOCIALMEI_WAHA_MANAGEMENT_PROBE_ENABLED': 'true', 'SOCIALMEI_WAHA_PRIVATE_BASE_URL': 'http://waha:3000',
                 'SOCIALMEI_WAHA_PRIVATE_API_KEY': 'synthetic-probe-secret-never-real'}
        with patch.dict(os.environ, flags), patch('whatsapp_human_transport.WahaHumanTransport.inspect_session', return_value={'status': 'WORKING'}) as probe:
            result = self.admin_client.post(PATH + '/inspect', json={})
            self.assertEqual(result.status_code, 200, result.text)
            self.assertTrue(result.json()['session_live_verified'])
            self.assertFalse(result.json()['receiving_messages'])
            self.assertEqual(self.admin_client.get(PATH).json()['connection_state'], 'connected')
            probe.assert_called_once()
            future = management.now() + timedelta(minutes=3)
            with patch('whatsapp_connection_management.now', return_value=future):
                self.assertFalse(self.admin_client.get(PATH).json()['session_live_verified'])
        self.assertNotIn('synthetic-probe-secret', result.text)
        self.assertNotIn('5581999990000', result.text)

    def test_disconnect_request_preserves_channel_and_history(self):
        self.own_binding()
        result = self.request(self.packet(action='disconnect', phone=None))
        self.assertEqual(result.status_code, 202, result.text)
        value = self.admin_client.get(PATH).json()
        self.assertEqual(value['request']['action'], 'disconnect')
        self.assertNotEqual(value['connection_state'], 'disconnected')
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.crm_canais WHERE ativo').fetchone()[0], 1)
        cancel = self.request(self.packet(action='cancel', phone=None, expected_revision=1))
        self.assertEqual(cancel.status_code, 202, cancel.text)
        self.assertIsNone(self.admin_client.get(PATH).json()['request'])

    def test_future_cached_check_is_not_live_session_evidence(self):
        binding = self.own_binding()
        value = {'revision': 0, 'receipts': [], 'observation': {
            'binding': management.binding_hash(binding), 'status': 'WORKING',
            'checked_at': (management.now() + timedelta(hours=1)).isoformat()}}
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{whatsapp_management}',%s::jsonb) WHERE id=%s", (json.dumps(value), self.workspace))
        result = self.admin_client.get(PATH)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertFalse(result.json()['session_live_verified'])

    def test_old_backlog_processed_now_does_not_claim_current_receiving(self):
        binding = self.own_binding('111@c.us')
        value = {'revision': 0, 'receipts': [], 'observation': {
            'binding': management.binding_hash(binding), 'status': 'WORKING', 'checked_at': management.now().isoformat(),
            'first_verified_at': (management.now() - timedelta(minutes=1)).isoformat()}}
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{whatsapp_management}',%s::jsonb) WHERE id=%s", (json.dumps(value), self.workspace))
        service = WahaIngressService({binding.instance: binding})
        old = fixtures.raw(fixtures.payload('false_222@c.us_old-backlog'))
        with patch.dict(os.environ, fixtures.FLAGS):
            self.assertEqual(service.receive(binding.instance, old, fixtures.sign(old), 'sha512')['processed'], 1)
        result = self.admin_client.get(PATH)
        self.assertTrue(result.json()['session_live_verified'])
        self.assertFalse(result.json()['receiving_messages'])
        timestamp = int(management.now().timestamp()) - 1
        recent = fixtures.payload('false_222@c.us_recent')
        recent['timestamp'] = timestamp * 1000
        recent['payload']['timestamp'] = timestamp
        raw = fixtures.raw(recent)
        with patch.dict(os.environ, fixtures.FLAGS):
            self.assertEqual(service.receive(binding.instance, raw, fixtures.sign(raw), 'sha512')['processed'], 1)
        self.assertTrue(self.admin_client.get(PATH).json()['receiving_messages'])
