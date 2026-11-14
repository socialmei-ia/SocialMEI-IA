"""No SSH, SQL, Docker, SDK or real backup data in this suite."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    'backup_plan', Path(__file__).resolve().parents[1] / 'tools/postgres-external-backup-plan.py')
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


class ExternalBackupPlanTests(unittest.TestCase):
    def test_unknown_facts_are_not_certified_or_echoed(self):
        sentinel = 'DO_NOT_ECHO_PRIVATE_SENTINEL'
        evidence = {'DATABASE_URL': 'postgresql://' + sentinel, 'source_identity_sha256': sentinel,
                    'last_backup': {'sha256': sentinel, 'created_at_utc': sentinel}}
        value = plan.make_plan(evidence)
        self.assertNotIn(sentinel, json.dumps(value))
        self.assertIsNone(value['source']['identity_sha256'])
        self.assertTrue(value['uncertainty'])
        self.assertFalse(value['activation_authorized'])

    def test_historical_receipt_never_becomes_current_production(self):
        value = plan.make_plan({'source_identity_sha256': 'a' * 64,
            'persistence': 'existing_volume', 'last_backup': {
                'sha256': 'b' * 64, 'schema': 38, 'bytes': 447575,
                'created_at_utc': '20261114T010202Z-19a3b6da',
                'archive_index_verified': True, 'current_production_backup': False}})
        self.assertIn('current_production_freshness_unproven', value['uncertainty'])
        self.assertNotIn('complete_verified_backup_receipt_required', value['uncertainty'])

    def test_policy_requires_versioned_encrypted_verified_transport(self):
        value = plan.make_plan({})['storage_contract']
        self.assertEqual(value['versioning'], 'Enabled')
        self.assertEqual(value['encryption'], 'AES256')
        self.assertTrue(value['tls_verify'])
        self.assertTrue(value['https_only'])
        self.assertIn('VersionId', value['readback'])
        self.assertEqual(value['conditional_create'], 'If-None-Match: *')

    def test_restore_has_no_network_production_mount_or_migration(self):
        value = plan.make_plan({})['restore_rehearsal']
        self.assertIn('--network=none', value['docker_contract'])
        self.assertFalse(value['publish_ports'])
        self.assertFalse(value['mount_production_volumes'])
        self.assertFalse(value['apply_migrations'])
        self.assertIn('migration_ledger', value['comparison_requires'])
        self.assertIn('sequences', value['comparison_requires'])

    def test_all_three_schema_ledgers_simulate_without_external_execution(self):
        with patch('subprocess.run', side_effect=AssertionError('external execution forbidden')):
            for schema in (38, 39, 40):
                result = plan.simulate(schema)
                self.assertTrue(result['complete'])
                self.assertTrue(result['comparison_equal'])
                self.assertFalse(result['real_backup_certified'])
                self.assertFalse(result['production_updates'])

    def test_permission_denial_never_promotes_receipt(self):
        store = plan.FakeVersionedStore(denied=True)
        with self.assertRaisesRegex(ValueError, 'permission_denied'):
            plan.simulate(store=store)
        self.assertEqual(store.objects, {})

    def test_corrupt_readback_never_promotes_receipt(self):
        with self.assertRaisesRegex(ValueError, 'readback_corrupt'):
            plan.simulate(store=plan.FakeVersionedStore(corrupt=True))

    def test_insecure_or_unversioned_fake_storage_is_rejected_before_put(self):
        for options in ({'tls_verified': False}, {'encryption': 'none'}, {'versioning': 'Suspended'}):
            store = plan.FakeVersionedStore(**options)
            with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'storage_security_unverified'):
                plan.simulate(store=store)
            self.assertEqual(store.objects, {})

    def test_restart_resumes_pinned_version_without_another_put(self):
        store = plan.FakeVersionedStore()
        checkpoint = plan.simulate(39, store, fault='interrupt')
        self.assertFalse(checkpoint['complete'])
        serialized = json.dumps(checkpoint)
        restarted = plan.FakeVersionedStore()
        restarted.objects = copy.deepcopy(store.objects)
        with patch.object(restarted, 'put', side_effect=AssertionError('duplicate upload')):
            resumed = plan.simulate(39, restarted, json.loads(serialized))
            repeated = plan.simulate(39, restarted, resumed)
        self.assertTrue(resumed['complete'])
        self.assertEqual(resumed, repeated)
        self.assertEqual(len(restarted.objects), 1)

    def test_restart_identity_mismatch_is_blocked(self):
        with self.assertRaisesRegex(ValueError, 'checkpoint_identity_mismatch'):
            plan.simulate(40, state={'schema': 38, 'sha256': 'a' * 64})

    def test_table_ledger_and_sequence_corruption_are_each_detected(self):
        for fault in ('table', 'ledger', 'sequence'):
            with self.subTest(fault=fault), self.assertRaisesRegex(ValueError, 'restore_mismatch'):
                plan.simulate(40, fault=fault)

    def test_real_provider_cannot_be_injected(self):
        with self.assertRaisesRegex(ValueError, 'synthetic_provider_required'):
            plan.simulate(store=object())

    def test_execute_mode_is_not_available(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            plan.main(['execute'])


if __name__ == '__main__':
    unittest.main()
