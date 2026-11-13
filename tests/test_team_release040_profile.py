"""Strict 040 identity and receipt validation, without external services."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release040_profile_tests', ROOT / 'tools/team-release-profile.py')
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


def proof():
    value = dict(profile='040', baseline='039', source_sha='a'*40, source_dirty=False,
                 source_migrations=profile.MIGRATIONS040, baseline_migrations=profile.MIGRATIONS039,
                 backup_sha256='b'*64, upgraded_backup_sha256='c'*64,
                 api_image_id='sha256:'+'d'*64, api_image_revision='a'*40)
    for key in ('isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
                'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
                'original_migrations_unchanged', 'incompatible_state_rejected',
                'backwards_compatible_reads_verified', 'sequences_preserved',
                'isolated_cleanup_verified', 'upgraded_backup_restore_verified'):
        value[key] = True
    for key in ('production_data_used', 'production_runtime_changed', 'provider_messages_sent'):
        value[key] = False
    return value


class Release040ProfileTests(unittest.TestCase):
    def test_exact_identity_preserves_all_historical_profiles(self):
        names = list(profile.MIGRATIONS040)
        read = lambda name: (ROOT / 'database/migrations' / name).read_bytes()
        self.assertEqual(len(names), 40)
        self.assertEqual(dict(list(profile.MIGRATIONS040.items())[:39]), profile.MIGRATIONS039)
        self.assertEqual(profile.verify040(names, read)['profile'], '040')
        self.assertEqual(profile.verify039(names[:39], read)['profile'], '039')
        self.assertEqual(profile.verify040(names, lambda name: read(name).replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))['profile'], '040')
        for verifier in (profile.verify, profile.verify038, profile.verify039):
            with self.subTest(verifier=verifier.__name__), self.assertRaises(RuntimeError):
                verifier(names, read)
        for name in names:
            with self.subTest(mutation=name), self.assertRaises(RuntimeError):
                profile.verify040(names, lambda item: read(item) + (b'\n' if item == name else b''))
        for bad in (names[:-1], names[::-1], names+['041_unreviewed.sql']):
            with self.subTest(names=bad[-2:]), self.assertRaises(RuntimeError):
                profile.verify040(bad, read)

    def test_complete_exact_receipt_and_each_missing_or_invalid_field(self):
        valid = proof()
        self.assertEqual(profile.rehearsal040(valid, 'a'*40), valid)
        for key, value in valid.items():
            bad = not value if type(value) is bool else {} if isinstance(value, dict) else 'invalid'
            with self.subTest(field=key), self.assertRaises(RuntimeError):
                profile.rehearsal040({**copy.deepcopy(valid), key: bad}, 'a'*40)
            missing = copy.deepcopy(valid)
            missing.pop(key)
            with self.subTest(missing=key), self.assertRaises(RuntimeError):
                profile.rehearsal040(missing, 'a'*40)
        for verifier in (profile.rehearsal, profile.rehearsal038, profile.rehearsal039):
            with self.subTest(old_verifier=verifier.__name__), self.assertRaises(RuntimeError):
                verifier(valid, 'a'*40)
        for wrong in (None, {}, dict(valid, baseline='035'), dict(valid, source_dirty=True)):
            with self.subTest(proof=wrong), self.assertRaises(RuntimeError):
                profile.rehearsal040(wrong, 'a'*40)


if __name__ == '__main__':
    unittest.main()
