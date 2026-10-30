"""Offline tests for the SHA-pinned Team v33 image import handoff."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import tarfile
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
        self.set_receipt_source(importer.EXPECTED_SHA)
        self.write_bundle()

    def set_receipt_source(self, source_sha):
        self.receipt = {
            "source_sha": source_sha,
            "images": {},
        }
        self.image_configs = {}
        for service in importer.SERVICES:
            config = json.dumps({
                "config": {"Labels": {
                    "org.opencontainers.image.revision": source_sha
                }},
                "architecture": "amd64",
                "os": "linux",
                "service_fixture": service,
                "rootfs": {"type": "layers", "diff_ids": []},
            }, separators=(",", ":")).encode()
            digest = hashlib.sha256(config).hexdigest()
            self.image_configs[service] = config
            self.receipt["images"][service] = {
                "tag": f"socialmei-v33/{service}:{source_sha}",
                "image_id": "sha256:" + digest,
            }

    def image_archive(self, config_overrides=None):
        config_overrides = config_overrides or {}
        output = io.BytesIO()
        rows = []
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for service, details in self.receipt["images"].items():
                digest = details["image_id"].removeprefix("sha256:")
                config_name = f"blobs/sha256/{digest}"
                config = config_overrides.get(service, self.image_configs[service])
                rows.append({"Config": config_name, "RepoTags": [details["tag"]],
                             "Layers": []})
                info = tarfile.TarInfo(config_name)
                info.size = len(config)
                archive.addfile(info, io.BytesIO(config))
            manifest = json.dumps(rows).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(manifest)
            archive.addfile(info, io.BytesIO(manifest))
        return output.getvalue()

    def write_bundle(self, *, replace=None, inject=None):
        payload = {
            "images.tar.gz": self.image_archive(),
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
        self.set_receipt_source(candidate_sha)
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

    def test_bundle_manifest_must_bind_receipt_to_exact_config_bytes(self):
        tampered = json.dumps({
            "config": {"Labels": {
                "org.opencontainers.image.revision": importer.EXPECTED_SHA
            }},
            "architecture": "amd64",
            "os": "linux",
            "rootfs": {"type": "layers", "diff_ids": []},
            "tampered": True,
        }, separators=(",", ":")).encode()
        self.write_bundle(replace={
            "images.tar.gz": self.image_archive({"team-api": tampered})
        })
        with patch.object(importer, "valid_stage"):
            with self.assertRaisesRegex(RuntimeError,
                                        "bundle_config_digest_diverge"):
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

    def test_existing_tag_without_exact_repository_tag_is_rejected(self):
        container_info = [{
            "Id": "sha256:" + "0" * 64,
            "RepoTags": [],
            "Config": {"Labels": {
                "org.opencontainers.image.revision": importer.EXPECTED_SHA
            }},
        }]
        with patch.object(importer, "docker",
                          return_value=json.dumps(container_info)):
            with self.assertRaisesRegex(RuntimeError, "tag_de_imagem_ja_existe"):
                importer.local_image_status(self.receipt)

    def test_local_tag_proves_receipt_config_digest_through_docker_archive(self):
        service = "team-api"
        tag = self.receipt["images"][service]["tag"]
        config = json.dumps({
            "config": {"Labels": {
                "org.opencontainers.image.revision": importer.EXPECTED_SHA
            }},
            "architecture": "amd64",
            "os": "linux",
            "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "c" * 64]},
        }, separators=(",", ":")).encode()
        config_sha = hashlib.sha256(config).hexdigest()
        self.receipt["images"][service]["image_id"] = "sha256:" + config_sha
        inspector = [{
            "Id": "sha256:" + "d" * 64,
            "RepoTags": [tag],
            "Config": {"Labels": {
                "org.opencontainers.image.revision": importer.EXPECTED_SHA
            }},
        }]

        def fake_docker(*args, **kwargs):
            if args[:2] == ("image", "inspect"):
                return json.dumps(inspector)
            if args[:2] == ("image", "save"):
                archive_path = Path(args[3])
                with tarfile.open(archive_path, "w") as archive:
                    manifest = json.dumps([{
                        "Config": config_sha + ".json",
                        "RepoTags": [tag],
                        "Layers": [],
                    }]).encode()
                    for name, value in (("manifest.json", manifest),
                                        (config_sha + ".json", config)):
                        info = tarfile.TarInfo(name)
                        info.size = len(value)
                        archive.addfile(info, io.BytesIO(value))
                return ""
            raise AssertionError(args)

        with patch.object(importer, "SERVICES", (service,)), \
                patch.object(importer, "docker", side_effect=fake_docker):
            result = importer.local_image_status(
                {"images": {service: self.receipt["images"][service]}},
                expected_sha=importer.EXPECTED_SHA,
            )
        self.assertTrue(result[service])

    def test_local_tag_rejects_config_digest_not_matching_receipt(self):
        service = "team-api"
        self.receipt["images"][service]["image_id"] = "sha256:" + "e" * 64
        tag = self.receipt["images"][service]["tag"]
        config = json.dumps({"config": {"Labels": {
            "org.opencontainers.image.revision": importer.EXPECTED_SHA
        }}}, separators=(",", ":")).encode()

        def fake_docker(*args, **kwargs):
            if args[:2] == ("image", "inspect"):
                return json.dumps([{
                    "Id": "sha256:" + "d" * 64,
                    "RepoTags": [tag],
                    "Config": {"Labels": {
                        "org.opencontainers.image.revision": importer.EXPECTED_SHA
                    }},
                }])
            archive_path = Path(args[3])
            with tarfile.open(archive_path, "w") as archive:
                manifest = json.dumps([{
                    "Config": "actual-config.json", "RepoTags": [tag], "Layers": []
                }]).encode()
                for name, value in (("manifest.json", manifest),
                                    ("actual-config.json", config)):
                    info = tarfile.TarInfo(name)
                    info.size = len(value)
                    archive.addfile(info, io.BytesIO(value))
            return ""

        with patch.object(importer, "SERVICES", (service,)), \
                patch.object(importer, "docker", side_effect=fake_docker):
            with self.assertRaisesRegex(RuntimeError,
                                        "tag_de_imagem_config_digest_diverge"):
                importer.local_image_status(
                    {"images": {service: self.receipt["images"][service]}},
                    expected_sha=importer.EXPECTED_SHA,
                )

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
