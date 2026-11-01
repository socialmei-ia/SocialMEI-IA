"""Identity and evidence gates, without Docker or production data."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release_profile', ROOT / 'tools/team-release-profile.py')
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


def valid_proof(sha='b' * 40):
    proof = {
        'profile': '035', 'baseline': '033', 'source_sha': sha, 'source_dirty': False,
        'source_migrations': dict(profile.MIGRATIONS),
        'baseline_migrations': dict(list(profile.MIGRATIONS.items())[:33]),
        'backup_sha256': 'c' * 64, 'api_image_id': 'sha256:' + 'd' * 64,
        'api_image_revision': sha,
    }
    for key in ('isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
                'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
                'original_migrations_unchanged', 'incompatible_state_rejected',
                'backwards_compatible_reads_verified', 'sequences_preserved', 'isolated_cleanup_verified'):
        proof[key] = True
    for key in ('production_data_used', 'production_runtime_changed', 'provider_messages_sent'):
        proof[key] = False
    return proof


class ReleaseProfileTests(unittest.TestCase):
    def test_exact_035_sql_bytes_and_historical_prefix_are_reviewed(self):
        names = list(profile.MIGRATIONS)
        read = lambda name: (ROOT / 'database/migrations' / name).read_bytes()
        self.assertEqual(profile.verify(names, read)['profile'], '035')
        self.assertEqual(profile.verify(names[:33], read)['profile'], '033')
        self.assertEqual(profile.verify(names, lambda name: read(name).replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))['profile'], '035')

    def test_mutated_old_new_unknown_partial_and_reordered_migrations_stop(self):
        names = list(profile.MIGRATIONS)
        read = lambda name: (ROOT / 'database/migrations' / name).read_bytes()
        for target in (names[0], names[32], names[33], names[34]):
            with self.subTest(target=target), self.assertRaisesRegex(RuntimeError, 'conteudo_de_migration_divergente'):
                profile.verify(names, lambda name: read(name) + (b'\n' if name == target else b''))
        for bad in (names[:34], names + ['036_unreviewed.sql'], names[:-1] + ['035_other.sql'], list(reversed(names))):
            with self.subTest(names=bad[-2:]), self.assertRaises(RuntimeError):
                profile.profile(bad)

    def test_035_requires_clean_exact_sha_and_real_restore_contract(self):
        proof = valid_proof()
        self.assertEqual(profile.rehearsal(proof, 'b' * 40), proof)
        changes = [
            {'source_sha': 'a' * 40}, {'source_dirty': True}, {'baseline': '031'},
            {'profile': '033'}, {'backup_sha256': 'not-a-checksum'},
            {'source_migrations': dict(list(profile.MIGRATIONS.items())[:33])},
            {'baseline_migrations': {}},
        ]
        for key, value in proof.items():
            if type(value) is bool:
                changes.append({key: not value})
        for update in changes:
            with self.subTest(update=update), self.assertRaises(RuntimeError):
                profile.rehearsal({**copy.deepcopy(proof), **update}, 'b' * 40)
        with self.assertRaises(RuntimeError):
            profile.rehearsal(None, 'b' * 40)


if __name__ == '__main__':
    unittest.main()
