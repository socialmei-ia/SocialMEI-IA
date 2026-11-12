"""Strict opt-in 039 migration identity and offline receipt validation."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release039_profile", ROOT / "tools/team-release-profile.py")
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


class Release039ProfileTests(unittest.TestCase):
    def test_exact_migration_identity_and_old_profile_isolation(self):
        read = lambda name: (ROOT / "database/migrations" / name).read_bytes()
        self.assertEqual(len(profile.MIGRATIONS039), 39)
        self.assertEqual(profile.verify039(list(profile.MIGRATIONS039), read)["profile"], "039")
        with self.assertRaises(RuntimeError):
            profile.verify038(list(profile.MIGRATIONS039), read)
        with self.assertRaises(RuntimeError):
            profile.verify(list(profile.MIGRATIONS039), read)
        for names in (list(profile.MIGRATIONS039)[:-1],
                      list(reversed(profile.MIGRATIONS039)),
                      list(profile.MIGRATIONS039) + ["040_unreviewed.sql"]):
            with self.subTest(names=names[-2:]), self.assertRaises(RuntimeError):
                profile.verify039(names, read)
        for name in profile.MIGRATIONS039:
            with self.subTest(file=name), self.assertRaises(RuntimeError):
                profile.verify039(list(profile.MIGRATIONS039),
                                  lambda file: read(file) + (b"\n" if file == name else b""))

    def test_rehearsal_requires_restored_backup_and_original_image_id(self):
        proof = {
            "profile": "039", "baseline": "035", "source_sha": "a"*40, "source_dirty": False,
            "source_migrations": profile.MIGRATIONS039, "baseline_migrations": profile.MIGRATIONS,
            "backup_sha256": "b"*64, "upgraded_backup_sha256": "c"*64,
            "api_image_id": "sha256:"+"d"*64, "api_image_revision": "a"*40,
        }
        for key in ("isolated", "disposable", "restored_backup_verified",
                    "existing_data_preserved", "migration_reapply_verified",
                    "constraints_verified", "schema_contract_verified",
                    "original_migrations_unchanged", "incompatible_state_rejected",
                    "backwards_compatible_reads_verified", "sequences_preserved",
                    "isolated_cleanup_verified", "upgraded_backup_restore_verified"):
            proof[key] = True
        for key in ("production_data_used", "production_runtime_changed", "provider_messages_sent"):
            proof[key] = False
        self.assertEqual(profile.rehearsal039(proof, "a"*40), proof)
        for key, value in proof.items():
            bad = not value if type(value) is bool else {} if isinstance(value, dict) else "invalid"
            with self.subTest(field=key), self.assertRaises(RuntimeError):
                profile.rehearsal039({**copy.deepcopy(proof), key: bad}, "a"*40)


if __name__ == "__main__":
    unittest.main()
