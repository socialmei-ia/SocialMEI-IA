"""038 requires explicit opt-in; old operators must continue refusing new schemas."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release038_profile', ROOT/'tools/team-release-profile.py')
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class Release038ProfileTests(unittest.TestCase):
    def test_explicit_exact_038_and_legacy_035_are_separate(self):
        read = lambda name: (ROOT/'database/migrations'/name).read_bytes()
        self.assertEqual(len(profile.MIGRATIONS), 35)
        self.assertEqual(profile.verify(list(profile.MIGRATIONS), read)['profile'], '035')
        self.assertEqual(profile.verify038(list(profile.MIGRATIONS038), read)['profile'], '038')
        with self.assertRaises(RuntimeError):
            profile.verify(list(profile.MIGRATIONS038), read)
        for names in (list(profile.MIGRATIONS), list(profile.MIGRATIONS038)[:-1], list(reversed(profile.MIGRATIONS038)), list(profile.MIGRATIONS038)+['039_unknown.sql']):
            with self.subTest(names=names[-2:]), self.assertRaises(RuntimeError):
                profile.verify038(names, read)
        for name in profile.MIGRATIONS038:
            with self.subTest(name=name), self.assertRaises(RuntimeError):
                profile.verify038(list(profile.MIGRATIONS038), lambda n: read(n)+(b'\n' if n==name else b''))

    def test_038_receipt_requires_real_upgrade_restore_contract_and_image_identity(self):
        proof = {
            'profile':'038','baseline':'035','source_sha':'a'*40,'source_dirty':False,
            'source_migrations':profile.MIGRATIONS038,'baseline_migrations':profile.MIGRATIONS,
            'backup_sha256':'b'*64,'upgraded_backup_sha256':'c'*64,
            'api_image_id':'sha256:'+'d'*64,'api_image_revision':'a'*40,
        }
        for key in ('isolated','disposable','restored_backup_verified','existing_data_preserved',
                    'migration_reapply_verified','constraints_verified','schema_contract_verified',
                    'original_migrations_unchanged','incompatible_state_rejected',
                    'backwards_compatible_reads_verified','sequences_preserved',
                    'isolated_cleanup_verified','upgraded_backup_restore_verified'):
            proof[key]=True
        for key in ('production_data_used','production_runtime_changed','provider_messages_sent'):
            proof[key]=False
        self.assertEqual(profile.rehearsal038(proof,'a'*40),proof)
        for key,value in proof.items():
            bad = not value if type(value) is bool else {} if isinstance(value,dict) else 'invalid'
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                profile.rehearsal038({**copy.deepcopy(proof),key:bad},'a'*40)
