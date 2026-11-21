"""Pure preflight delta regression tests; no Docker or production requests."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("crm_preflight", Path(__file__).with_name("prepare-crm233-release.py"))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

publish_spec = importlib.util.spec_from_file_location("crm_publish", Path(__file__).with_name("publish-crm233.py"))
publisher = importlib.util.module_from_spec(publish_spec)
publish_spec.loader.exec_module(publisher)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.before = {"services": {"team-api": {"image": release.OLD_API, "environment": {"FLAG": "keep"}},
            "team-gateway": {"image": release.PREMIUM, "volumes": [{"type": "bind", "source": "/old/config",
                "target": "/srv/frontend/config.js", "read_only": True}]}}, "networks": {"private": {}}}

    def test_api_image_is_the_only_allowed_delta(self):
        after = copy.deepcopy(self.before)
        after["services"]["team-api"]["image"] = release.NEW_API
        release.validate_change(self.before, after, "team-api")
        after["services"]["team-api"]["environment"]["FLAG"] = "changed"
        with self.assertRaisesRegex(RuntimeError, "CHANGE_EXCEEDS"):
            release.validate_change(self.before, after, "team-api")

    def test_premium_accepts_one_readonly_js_and_preserves_other_services(self):
        after = copy.deepcopy(self.before)
        after["services"]["team-gateway"]["volumes"].append({"type": "bind", "source": "/package/file.js",
            "target": release.ASSET, "read_only": True})
        release.validate_change(self.before, after, "team-gateway", asset_source="/package/file.js")
        after["services"]["team-gateway"]["image"] = "generic"
        with self.assertRaisesRegex(RuntimeError, "CHANGE_EXCEEDS"):
            release.validate_change(self.before, after, "team-gateway", asset_source="/package/file.js")

    def test_writable_asset_or_extra_mount_fails(self):
        for writable in (True, False):
            after = copy.deepcopy(self.before)
            volumes = after["services"]["team-gateway"]["volumes"]
            volumes.append({"type": "bind", "source": "/package/file.js", "target": release.ASSET,
                            "read_only": not writable})
            if not writable:
                volumes.append({"target": "/extra", "source": "/extra", "type": "bind"})
            with self.assertRaises(RuntimeError):
                release.validate_change(self.before, after, "team-gateway", asset_source="/package/file.js")

    def test_compose_null_command_means_image_default_and_env_drift_fails(self):
        image = {"Config": {"Env": ["BASE=1"], "Cmd": ["uvicorn"], "Entrypoint": None}}
        container = {"Image": "sha256:test", "Config": {"Env": ["BASE=1", "FLAG=keep"],
            "Cmd": ["uvicorn"], "Entrypoint": None}, "Mounts": []}
        service = {"environment": {"FLAG": "keep"}, "command": None}
        import json
        with patch.object(release, "run", return_value=json.dumps([image])):
            release.validate_runtime(service, container)
            service["environment"]["FLAG"] = "drift"
            with self.assertRaisesRegex(RuntimeError, "RUNNING_ENVIRONMENT"):
                release.validate_runtime(service, container)

    def test_manual_network_attachment_blocks_recreation(self):
        image = {"Config": {"Env": [], "Cmd": ["uvicorn"], "Entrypoint": None}}
        service = {"networks": {"private": None}}
        document = {"networks": {"private": {"name": "existing-private-network"}}}
        container = {"Image": "sha256:test", "Config": image["Config"], "Mounts": [],
                     "NetworkSettings": {"Networks": {"existing-private-network": {}, "manual-gows-network": {}}},
                     "HostConfig": {"RestartPolicy": {"Name": "no"}, "PortBindings": {}}}
        with patch.object(release, "run", return_value=json.dumps([image])):
            with self.assertRaisesRegex(RuntimeError, "RUNNING_NETWORKS"):
                release.validate_runtime(service, container, document)
            del container["NetworkSettings"]["Networks"]["manual-gows-network"]
            release.validate_runtime(service, container, document)

    def test_old_api_tag_must_still_identify_the_running_image(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            asset = package / "v22-inbox-customer.js"
            asset.write_bytes(b"fixture JavaScript")
            api = {"Config": {"Image": release.OLD_API}, "Image": "sha256:running-original"}
            with patch.object(release, "JS_HASH", hashlib.sha256(asset.read_bytes()).hexdigest()), \
                    patch.object(release, "inspect", side_effect=[api, {}]), \
                    patch.object(release, "run", return_value=json.dumps([{"Id": "sha256:retagged"}])):
                with self.assertRaisesRegex(RuntimeError, "OLD_API_TAG_DRIFT"):
                    release.prepare(package)

    def test_resource_capability_and_user_drift_block_recreation(self):
        image = {"Config": {"Env": [], "Cmd": ["uvicorn"], "Entrypoint": None, "User": "1000"}}
        service = {"networks": {"private": None}, "mem_limit": "128m", "cap_drop": ["ALL"]}
        document = {"networks": {"private": {"name": "existing-private-network"}}}
        container = {"Image": "sha256:test", "Config": image["Config"], "Mounts": [],
                     "NetworkSettings": {"Networks": {"existing-private-network": {}}},
                     "HostConfig": {"RestartPolicy": {"Name": "no"}, "PortBindings": {},
                                    "Memory": 128 * 1024**2, "CapDrop": ["ALL"]}}
        with patch.object(release, "run", return_value=json.dumps([image])):
            release.validate_runtime(service, container, document)
            for section, field, value, reason in (("HostConfig", "Memory", 256 * 1024**2, "RESOURCE_LIMITS"),
                    ("HostConfig", "PidsLimit", 100, "RESOURCE_LIMITS"),
                    ("HostConfig", "CapAdd", ["SYS_ADMIN"], "SECURITY_OPTIONS"),
                    ("Config", "User", "root", "RUNNING_USER")):
                changed = copy.deepcopy(container)
                changed[section][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(RuntimeError, reason):
                    release.validate_runtime(service, changed, document)

    def test_changed_original_compose_uses_frozen_immutable_rollback(self):
        self.check_source_drift_rollback(fail_rollback=False)

    def test_failed_frozen_rollback_requires_operator_and_never_reports_success(self):
        self.check_source_drift_rollback(fail_rollback=True)

    def check_source_drift_rollback(self, *, fail_rollback):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder).resolve()
            sources = {}
            documents = {}
            containers = {}
            for service, name, tag in (("team-api", release.API, release.OLD_API),
                                       ("team-gateway", release.GATEWAY, release.PREMIUM)):
                source = package / (service + ".original.json")
                document = {"services": {service: {"image": tag, "environment": {"FLAG": "original"}}}}
                source.write_text(json.dumps(document), encoding="utf-8")
                sources[service] = source
                documents[service] = document
                containers[name] = {"Image": "sha256:original-" + service, "service": service}
            plan = {"release_plan_sha256": "approved", "api_new_image_id": "sha256:candidate",
                    "premium_image_id_preserved": containers[release.GATEWAY]["Image"], "services": {}}
            for service, document in documents.items():
                after = copy.deepcopy(document)
                if service == "team-api":
                    after["services"][service]["image"] = release.NEW_API
                else:
                    after["services"][service]["volumes"] = [{"type": "bind",
                        "source": str(package / "v22-inbox-customer.js"), "target": release.ASSET, "read_only": True}]
                plan["services"][service] = {"baseline_config_sha256": release.digest(document),
                                            "candidate_config_sha256": release.digest(after)}

            def chain(container, service):
                return ["docker", "compose", "-f", str(sources[service])], str(package), [str(sources[service])]

            def render(command, **kwargs):
                source = Path(command[command.index("-f") + 1])
                document = json.loads(source.read_text(encoding="utf-8"))
                if command.count("-f") > 1:
                    overlay = json.loads(Path(command[-4]).read_text(encoding="utf-8"))
                    for service, changes in overlay["services"].items():
                        document["services"][service].update(changes)
                return json.dumps(document)

            deployments = []

            def deploy(command, service, cwd):
                deployments.append((command, service))
                if len(deployments) == 1:
                    self.assertEqual(service, "team-api")
                    for source in sources.values():
                        source.write_text('{"services":{"unrelated":{"image":"changed"}}}', encoding="utf-8")
                    return
                self.assertEqual(service, "team-api")
                self.assertEqual(command.count("-f"), 1)
                frozen = Path(command[-1])
                self.assertTrue(frozen.name.endswith(".rollback.private.json"))
                self.assertNotIn(str(sources[service]), command)
                saved = json.loads(frozen.read_text(encoding="utf-8"))
                self.assertEqual(saved["services"][service]["image"], containers[release.API]["Image"])
                self.assertEqual(saved["services"][service]["environment"], {"FLAG": "original"})
                if fail_rollback:
                    raise RuntimeError("simulated rollback failure")

            old_umask = os.umask(0o077)
            try:
                with patch.object(publisher.preflight, "prepare", return_value=plan), \
                        patch.object(publisher.preflight, "inspect", side_effect=lambda name: containers[name]), \
                        patch.object(publisher.preflight, "chain", side_effect=chain), \
                        patch.object(publisher.preflight, "run", side_effect=render), \
                        patch.object(publisher, "deploy", side_effect=deploy), \
                        patch.object(publisher, "wait"):
                    expected = "ROLLBACK_REQUIRES_OPERATOR" if fail_rollback else "PUBLICATION_FAILED_ROLLED_BACK"
                    with self.assertRaisesRegex(RuntimeError, expected):
                        publisher.apply(package, "approved")
            finally:
                os.umask(old_umask)
            self.assertEqual(len(deployments), 2)
            result_path = next(package.glob("approved-release-*/result.json"))
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "rollback_failed" if fail_rollback else "rolled_back")
            self.assertEqual(result["failed_rollback_services"], ["team-api"] if fail_rollback else [])


if __name__ == "__main__":
    unittest.main()
