"""Offline tests for the SHA-pinned Team v33 image import handoff."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MODULE = Path(__file__).resolve().parents[1] / "tools/team-v33-import-images.py"
spec = importlib.util.spec_from_file_location("team_image_import", MODULE)
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class ImportImagesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        patcher = patch.object(importer, "BACKUPS", self.folder)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.path = self.folder / "team-v33-ci-bundle.zip"
        self.receipt = {
            "source_sha": importer.EXPECTED_SHA,
            "images": {
                service: {
                    "tag": f"socialmei-v33/{service}:{importer.EXPECTED_SHA}",
                    "image_id": "sha256:" + char * 64,
                }
                for service, char in (
                    ("team-api", "a"), ("team-gateway", "b")
                )
            },
        }
        self.write_bundle()

    def write_bundle(self, *, replace=None, inject=None):
        payload = {
            "images.tar.gz": b"fake image archive payload" * 400,
            "image-receipt.json": json.dumps(self.receipt).encode(),
        }
        if replace:
            payload.update(replace)
        sums = "\n".join(
            f"{hashlib.sha256(content).hexdigest()}  {name}"
            for name, content in payload.items()
        ).encode() + b"\n"
        payload["SHA256SUMS"] = sums
        if inject:
            payload.update(inject)
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_STORED) as zip_file:
            for name, value in payload.items():
                zip_file.writestr(name, value)

    def test_inspection_verifies_sha_source_and_avoids_docker_load(self):
        with patch.object(importer, "valid_stage"):
            with patch.object(importer, "local_image_status",
                              return_value={"team-api": False,
                                            "team-gateway": False}):
                with patch.object(importer, "docker",
                                  side_effect=AssertionError("docker touched")):
                    result = importer.execute(self.path, apply=False)
        self.assertEqual(result["action"], "inspection_passed")
        self.assertTrue(result["bundle_sha256_verified"])
        self.assertFalse(result["production_container_changed"])
        self.assertFalse(result["provider_messages_sent"])

    def test_inspection_accepts_exact_sha_from_new_candidate_receipt(self):
        candidate_sha = "8b60410ba0709a7bff5892c93988eb7af878516c"
        self.receipt = {
            "source_sha": candidate_sha,
            "images": {
                service: {
                    "tag": f"socialmei-v33/{service}:{candidate_sha}",
                    "image_id": "sha256:" + char * 64,
                }
                for service, char in (("team-api", "a"), ("team-gateway", "b"))
            },
        }
        self.write_bundle()
        with patch.object(importer, "valid_stage"):
            with patch.object(importer, "local_image_status",
                              return_value={"team-api": False, "team-gateway": False}):
                with patch.object(importer, "docker",
                                  side_effect=AssertionError("docker touched")):
                    result = importer.execute(
                        self.path, apply=False, expected_sha=candidate_sha
                    )
        self.assertEqual(result["candidate_sha"], candidate_sha)
        self.assertEqual(result["action"], "inspection_passed")
        self.assertTrue(result["bundle_sha256_verified"])

    def test_import_only_uses_docker_load_and_preserves_containers(self):
        commands = []
        with patch.object(importer, "valid_stage"):
            with patch.object(importer, "local_image_status",
                              side_effect=[
                                  {"team-api": False, "team-gateway": False},
                                  {"team-api": True, "team-gateway": True},
                              ]):
                with patch.object(importer, "docker",
                                  side_effect=lambda *args, **kw:
                                  commands.append(args) or ""):
                    result = importer.execute(self.path, apply=True)
        self.assertEqual(result["action"],
                         "images_loaded_without_container_recreation")
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0][:2], ("load", "-i"))
        self.assertFalse(result["production_container_changed"])
        self.assertFalse(result["database_changed"])

    def test_mismatched_archive_digest_rejected(self):
        self.write_bundle(replace={
            "SHA256SUMS": b"tampered"  # overwritten when building below
        })
        # Corrupt the ZIP after checksums were committed.
        with zipfile.ZipFile(self.path, "a", zipfile.ZIP_STORED) as zip_file:
            zip_file.writestr("unexpected", "evil")
        with self.assertRaisesRegex(RuntimeError,
                                    "pacote_com_entradas_inesperadas"):
            importer.read_bundle(self.path)

    def test_wrong_label_or_source_rejected(self):
        self.receipt["source_sha"] = "0" * 40
        self.write_bundle()
        with self.assertRaisesRegex(RuntimeError, "origem_das_imagens_divergente"):
            importer.read_bundle(self.path)
        self.receipt["source_sha"] = importer.EXPECTED_SHA
        self.receipt["images"]["team-api"]["tag"] = "other:latest"
        self.write_bundle()
        with self.assertRaisesRegex(RuntimeError, "imagem_de_recibo_invalida"):
            importer.read_bundle(self.path)

    def test_archive_symlink_rejected(self):
        alias = self.folder / "alias.zip"
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(RuntimeError, "pacote_simbolico_proibido"):
            importer.read_bundle(alias)

    def test_existing_tag_with_different_image_id_rejected(self):
        container_info = [{
            "Id": "sha256:" + "0" * 64,
            "Config": {"Labels": {
                "org.opencontainers.image.revision": importer.EXPECTED_SHA
            }},
        }]
        with patch.object(importer, "docker",
                          return_value=json.dumps(container_info)):
            with self.assertRaisesRegex(RuntimeError, "tag_de_imagem_ja_existe"):
                importer.local_image_status(self.receipt)

    def test_no_overwrite_when_both_images_already_present(self):
        with patch.object(importer, "valid_stage"):
            with patch.object(importer, "local_image_status",
                              return_value={"team-api": True,
                                            "team-gateway": True}):
                with patch.object(importer, "docker",
                                  side_effect=AssertionError("docker changed")):
                    result = importer.execute(self.path, apply=True)
        self.assertEqual(result["action"], "images_already_verified")


if __name__ == "__main__":
    unittest.main()
