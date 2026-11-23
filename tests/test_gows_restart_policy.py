"""Fake Docker only; never touches WhatsApp, its session or live containers."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('restart', Path(__file__).resolve().parents[1] / 'tools/gows-restart-policy.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class RestartPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name) / 'private'
        self.row = {'Name': '/' + m.NAME, 'Id': 'frozen-id', 'Image': 'frozen-image',
                    'Config': {'Env': ['PRIVATE=sentinel'], 'Labels': {}},
                    'HostConfig': {'RestartPolicy': {'Name': 'no', 'MaximumRetryCount': 0}, 'Memory': 123},
                    'Mounts': [{'Source': '/private/session', 'Destination': '/app/.sessions'}],
                    'NetworkSettings': {'Networks': {'private': {'Aliases': ['gows']}}},
                    'State': {'Running': True, 'StartedAt': 'frozen-time'}}
        self.calls = []; self.uncertain = False
        def call(args):
            self.calls.append(args)
            if args[:2] == ['docker', 'inspect']:
                return json.dumps([self.row])
            if args[:3] == ['docker', 'update', '--restart']:
                self.row['HostConfig']['RestartPolicy']['Name'] = args[3]
                if self.uncertain:
                    raise RuntimeError('uncertain')
                return ''
            raise AssertionError('Unexpected operation')
        override = patch.object(m, 'call', side_effect=call)
        override.start(); self.addCleanup(override.stop)
        self.plan = m.prepare(self.directory)

    def test_prepare_is_read_only_and_keeps_credentials_private(self):
        self.assertEqual(self.calls, [['docker', 'inspect', m.NAME]])
        self.assertFalse(self.plan['compose_managed'])
        self.assertNotIn('sentinel', json.dumps(self.plan))

    def test_policy_update_and_rollback_never_restart_or_change_session(self):
        before = copy.deepcopy(self.row)
        result = m.update(self.directory, self.plan['plan_sha256'])
        self.assertEqual(result['status'], 'applied')
        self.assertFalse(result['container_restarted'])
        self.assertEqual(m.invariant(self.row), m.invariant(before))
        m.update(self.directory, self.plan['plan_sha256'], rollback=True)
        self.assertEqual(self.row, before)
        self.assertEqual([c[:2] for c in self.calls if c[1] != 'inspect'],
                         [['docker', 'update'], ['docker', 'update']])

    def test_drift_blocks_update(self):
        for field in ('Image', 'Mounts', 'Config', 'NetworkSettings'):
            original = copy.deepcopy(self.row[field])
            self.row[field] = 'drift'
            with self.subTest(field=field), self.assertRaises((RuntimeError, TypeError)):
                m.update(self.directory, self.plan['plan_sha256'])
            self.row[field] = original
        self.assertFalse(any(c[1] == 'update' for c in self.calls))

    def test_missing_or_wrong_approval_never_updates(self):
        for value in ('', 'wrong'):
            with self.assertRaises(RuntimeError):
                m.update(self.directory, value)
        self.assertFalse(any(c[1] == 'update' for c in self.calls))

    def test_uncertain_result_is_reconciled_without_second_update(self):
        self.uncertain = True
        self.assertEqual(m.update(self.directory, self.plan['plan_sha256'])['status'], 'applied')
        self.assertEqual(sum(c[1] == 'update' for c in self.calls), 1)
        with self.assertRaises(RuntimeError):
            m.update(self.directory, self.plan['plan_sha256'])
        self.assertEqual(sum(c[1] == 'update' for c in self.calls), 1)

    def test_future_compose_requires_restart_policy_on_exact_container(self):
        service = {'container_name': m.NAME, 'restart': 'unless-stopped'}
        self.assertTrue(m.check_compose({'services': {'gows': service}})['compose_restart_policy_verified'])
        for config in ({}, {'services': {'gows': {**service, 'restart': 'no'}}},
                       {'services': {'a': service, 'b': service}}):
            with self.subTest(config=config), self.assertRaises(RuntimeError):
                m.check_compose(config)


if __name__ == '__main__':
    unittest.main()
