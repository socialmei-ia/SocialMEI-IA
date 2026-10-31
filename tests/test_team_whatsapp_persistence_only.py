"""No production fixtures: webhook isolation changes only the expected hook list."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import io
import json

PATH = Path(__file__).resolve().parents[1] / 'tools/team-whatsapp-persistence-only.py'


class PersistenceOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('persistence_only', PATH)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def fixture(self):
        direct = {'url': 'http://team-api:8000/internal/waha/pilot/webhook',
                  'events': ['message'], 'hmac': {'key': 'synthetic-key'}}
        legacy = {'url': 'http://n8n:5678/webhook-test/synthetic', 'events': ['message', 'session.status']}
        binding = {'instance': 'pilot', 'hmac_key': 'synthetic-key'}
        return {'webhooks': [legacy, direct], 'proxy': {'server': 'synthetic'}}, binding

    def test_isolates_only_legacy_hook_without_mutating_input(self):
        config, binding = self.fixture()
        before = copy.deepcopy(config)
        after = self.module.persistence_config(config, binding, before['webhooks'][:1])
        self.assertEqual(config, before)
        self.assertEqual(after, {**config, 'webhooks': [config['webhooks'][1]]})
        self.assertEqual(self.module.persistence_config(after, binding), after)

    def test_rejects_drift_unknown_extra_hook_or_wrong_signature(self):
        for change in ('unknown', 'extra', 'key', 'event', 'duplicate', 'unknown_host'):
            config, binding = self.fixture()
            legacy = copy.deepcopy(config['webhooks'][:1])
            if change == 'unknown': config['webhooks'][0]['url'] = 'http://n8n/unknown'
            if change == 'extra': config['webhooks'].append(copy.deepcopy(config['webhooks'][0]))
            if change == 'key': config['webhooks'][1]['hmac']['key'] = 'wrong'
            if change == 'event': config['webhooks'][1]['events'].append('message.any')
            if change == 'duplicate': config['webhooks'][0] = copy.deepcopy(config['webhooks'][1])
            if change == 'unknown_host': config['webhooks'][0]['url'] = 'http://unknown/webhook-test/synthetic'
            with self.subTest(change=change), self.assertRaises(self.module.Blocked):
                self.module.persistence_config(config, binding, legacy)

    def test_receipt_hash_is_stable_for_equivalent_configuration(self):
        a, _ = self.fixture()
        b = dict(reversed(list(a.items())))
        self.assertEqual(self.module.config_digest(a), self.module.config_digest(b))

    def run_apply(self, *, fail_update=False, wrong_digest=False, unsafe_bot=False, ingress_disabled=False, health_failure=False):
        m = self.module
        config, _ = self.fixture()
        config['webhooks'][1]['url'] = 'http://team-api:8000/internal/waha/socialmei-equipe-piloto/webhook'
        binding = {'instance': 'socialmei-equipe-piloto', 'hmac_key': 'synthetic-key',
                   'workspace_id': 1, 'account_id': '9915976@c.us', 'session': '01'}
        session = {'name': '01', 'status': 'WORKING', 'me': {'id': binding['account_id']},
                   'engine': {'engine': 'WEBJS'}, 'config': config}
        target = {**session, 'config': m.persistence_config(config, binding, config['webhooks'][:1])}
        responses = [session, session, {}, {**target, 'config': {}} if fail_update else target]
        if fail_update: responses.extend([{}, session])
        requests = []
        def urlopen(req, timeout):
            requests.append(req)
            return io.BytesIO(json.dumps(responses.pop(0)).encode())
        api = {'Id': 'api-id', 'State': {'Health': {'Status': 'healthy'}},
               'Config': {'Env': ['SOCIALMEI_WAHA_INGRESS_MODE=team-pilot',
                                  'SOCIALMEI_WAHA_LAB_ENVIRONMENT=' + ('' if ingress_disabled else 'team-pilot'),
                                  'SOCIALMEI_WAHA_REGISTRY_FILE=/run/socialmei/private/waha-registry.json',
                                  'SOCIALMEI_SHARED_DATA_ENABLED=true', 'SOCIALMEI_AUTH_ENABLED=true',
                                  'SOCIALMEI_WHATSAPP_BOT_ENABLED=' + (' true ' if unsafe_bot else 'false')]},
               'Mounts': [{'Destination': '/run/socialmei/private', 'Source': str(m.REGISTRY.parent), 'RW': False}],
               'NetworkSettings': {'Networks': {'private-api': {}}}}
        waha = {'Id': 'waha-id', 'Config': {'Env': ['WAHA_API_KEY=synthetic']},
                'NetworkSettings': {'Networks': {'private-api': {}}, 'Ports': {'3000/tcp': [{'HostPort': '3000'}]}}}
        args = SimpleNamespace(restore=None, apply=True, confirm='TEAM-1', legacy_backup=Path('synthetic'),
                               expected_config_sha256='wrong' if wrong_digest else m.config_digest(config))
        calls = 0
        def inspect(n):
            nonlocal calls
            if n != m.API: return waha
            calls += 1
            if health_failure and calls == 2:
                unhealthy = copy.deepcopy(api)
                unhealthy['State']['Health']['Status'] = 'unhealthy'
                return unhealthy
            return api
        if health_failure: responses.extend([{}, session])
        with patch.object(m.os, 'geteuid', return_value=0, create=True), patch.object(m, 'private'), \
             patch.object(m, 'inspect', side_effect=inspect), \
             patch.object(m, 'REGISTRY') as registry, patch.object(m, 'urlopen', side_effect=urlopen), \
             patch.object(m, 'backup', return_value=Path('synthetic-private-backup')) as backup, \
             patch.object(m, 'load_legacy', return_value={**session, 'config': {**config, 'webhooks': config['webhooks'][:1]}}):
            registry.read_text.return_value = json.dumps({'version': 1, 'bindings': [binding]})
            # Use the real path for the mount comparison while intercepting the file read.
            registry.parent.__str__.return_value = api['Mounts'][0]['Source']
            try:
                result = m.operate(args)
            except m.Blocked as exc:
                result = str(exc)
            return result, requests, backup.call_count, config

    def test_apply_requires_expected_digest_before_any_write(self):
        result, requests, backups, _ = self.run_apply(wrong_digest=True)
        self.assertEqual(result, 'confirmation_or_config_digest_missing')
        self.assertEqual([r.method for r in requests], ['GET'])
        self.assertEqual(backups, 0)

    def test_apply_verifies_health_and_only_changes_webhooks(self):
        result, requests, backups, before = self.run_apply()
        self.assertEqual(result['action'], 'persistence_only_configured')
        self.assertFalse(result['provider_messages_sent'])
        self.assertEqual(backups, 1)
        puts = [json.loads(r.data)['config'] for r in requests if r.method == 'PUT']
        self.assertEqual(puts, [{**before, 'webhooks': [before['webhooks'][1]]}])

    def test_failed_update_restores_exact_original_configuration(self):
        result, requests, backups, before = self.run_apply(fail_update=True)
        self.assertEqual(result, 'update_failed_rollback_verified')
        self.assertEqual(backups, 1)
        puts = [json.loads(r.data)['config'] for r in requests if r.method == 'PUT']
        self.assertEqual(len(puts), 2)
        self.assertEqual(puts[-1], before)

    def test_bot_whitespace_and_disabled_ingress_block_before_mutation(self):
        for kwargs in ({'unsafe_bot': True}, {'ingress_disabled': True}):
            result, requests, backups, _ = self.run_apply(**kwargs)
            self.assertEqual(result, 'receive_only_flags_required')
            self.assertFalse(any(req.method == 'PUT' for req in requests))
            self.assertEqual(backups, 0)

    def test_new_api_health_failure_rolls_back_webhook_change(self):
        result, requests, _, before = self.run_apply(health_failure=True)
        self.assertEqual(result, 'update_failed_rollback_verified')
        self.assertEqual([json.loads(r.data)['config'] for r in requests if r.method == 'PUT'][-1], before)
