"""An explicit 038 bundle path must not relax the historical operator gates."""
import copy
import unittest
import test_team_v33_import_images as fixtures


class Import038Tests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.ImportImagesTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.importer = fixtures.importer
        self.sha = 'a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510'
        self.f.set_receipt_source(self.sha)
        profile = self.importer.release_profile()
        proof = {
            'profile': '038', 'baseline': '035', 'source_sha': self.sha,
            'source_dirty': False, 'source_migrations': profile.MIGRATIONS038,
            'baseline_migrations': profile.MIGRATIONS,
            'backup_sha256': 'a' * 64, 'upgraded_backup_sha256': 'b' * 64,
            'api_image_id': self.f.receipt['images']['team-api']['image_id'],
            'api_image_revision': self.sha,
        }
        for field in ('isolated', 'disposable', 'restored_backup_verified',
                      'existing_data_preserved', 'migration_reapply_verified',
                      'constraints_verified', 'schema_contract_verified',
                      'original_migrations_unchanged', 'incompatible_state_rejected',
                      'backwards_compatible_reads_verified', 'sequences_preserved',
                      'isolated_cleanup_verified', 'upgraded_backup_restore_verified'):
            proof[field] = True
        for field in ('production_data_used', 'production_runtime_changed', 'provider_messages_sent'):
            proof[field] = False
        self.f.receipt.update(release_profile='038', migration_sha256=profile.MIGRATIONS038,
                              migration_rehearsal=proof)
        self.original = copy.deepcopy(self.f.receipt)
        self.f.write_bundle()

    def test_explicit_profile_accepts_exact_bundle_and_legacy_still_refuses(self):
        result = self.importer.read_bundle038(self.f.path, self.sha)
        self.assertEqual(result, self.f.receipt)
        with self.assertRaisesRegex(RuntimeError, 'perfil_de_imagem_nao_revisado'):
            self.importer.read_bundle(self.f.path, expected_sha=self.sha)

    def test_rehearsal_migrations_image_and_source_cannot_be_swapped(self):
        changes = (
            ('release_profile', '035'),
            ('source_sha', 'b' * 40),
            ('migration_sha256', self.importer.release_profile().MIGRATIONS),
            ('migration_rehearsal', {**self.original['migration_rehearsal'], 'restored_backup_verified': False}),
            ('migration_rehearsal', {**self.original['migration_rehearsal'], 'api_image_id': 'sha256:' + 'f' * 64}),
        )
        for field, value in changes:
            with self.subTest(field=field, value=str(value)[:20]):
                self.f.receipt = {**copy.deepcopy(self.original), field: value}
                self.f.write_bundle()
                with self.assertRaises(RuntimeError):
                    self.importer.read_bundle038(self.f.path, self.sha)

    def test_internal_archive_integrity_remains_mandatory(self):
        self.f.write_bundle(replace={'images.tar.gz': b'not a valid image archive' * 100})
        with self.assertRaises(Exception):
            self.importer.read_bundle038(self.f.path, self.sha)


if __name__ == '__main__':
    unittest.main()
