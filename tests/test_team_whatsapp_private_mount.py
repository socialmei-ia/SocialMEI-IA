"""Offline guards for restoring the Team API's missing private WhatsApp mount."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "team_whatsapp_private_mount", ROOT / "tools" / "team-whatsapp-private-mount.py"
)
mount = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mount)


def fixture():
    model = {
        "name": "socialmei-team",
        "networks": {"api": {"name": "socialmei-team_api"}},
        "services": {
            "team-api": {
                "image": "socialmei/team-api:pin",
                "environment": {"SOCIALMEI_AUTH_ENABLED": "true"},
                "networks": {"api": None},
                "volumes": [],
            },
            "team-gateway": {"image": "socialmei/gateway:pin"}
        }
    }
    api = {
        "Config": {
            "Image": "socialmei/team-api:pin",
            "Env": ["SOCIALMEI_AUTH_ENABLED=true"],
        },
        "HostConfig": {"PortBindings": {}},
        "NetworkSettings": {"Networks": {"socialmei-team_api": {}}},
        "Mounts": [],
        "State": {"Health": {"Status": "healthy"}},
    }
    return model, api


class PilotPrivateMountTests(unittest.TestCase):
    def test_baseline_runtime_must_match_model(self):
        model, api = fixture()
        mount.assert_current(api, model)
        api["Config"]["Image"] = "socialmei/team-api:other"
        with self.assertRaises(mount.Blocked):
            mount.assert_current(api, model)

    def test_only_one_private_readonly_bind_is_allowed(self):
        old, _ = fixture()
        new = copy.deepcopy(old)
        source = Path("/opt/socialmei/private/whatsapp-pilot")
        new["services"]["team-api"]["volumes"] = [{
            "type": "bind", "source": str(source),
            "target": mount.TARGET, "read_only": True,
        }]
        mount.check_candidate(old, new, source)
        new["services"]["team-gateway"]["image"] = "changed"
        with self.assertRaises(mount.Blocked):
            mount.check_candidate(old, new, source)

    def test_readwrite_or_duplicate_bind_is_blocked(self):
        old, _ = fixture()
        source = Path("/opt/socialmei/private/whatsapp-pilot")
        new = copy.deepcopy(old)
        volume = {"type": "bind", "source": str(source), "target": mount.TARGET,
                  "read_only": False}
        new["services"]["team-api"]["volumes"] = [volume]
        with self.assertRaises(mount.Blocked):
            mount.check_candidate(old, new, source)
        new["services"]["team-api"]["volumes"] = [{**volume, "read_only": True},
                                                    {**volume, "read_only": True}]
        with self.assertRaises(mount.Blocked):
            mount.check_candidate(old, new, source)


if __name__ == "__main__":
    unittest.main()
