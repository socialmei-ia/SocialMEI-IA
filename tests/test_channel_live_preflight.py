"""No AWS, Docker, database, WhatsApp or Meta access in these tests."""
import importlib.util
import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools" / "channel-live-preflight.py"
SPEC = importlib.util.spec_from_file_location("channel_live_preflight", FILE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def container(name, env=None, *, health="healthy"):
    env = env or {}
    return {
        "Name": "/" + name,
        "Image": "sha256:" + "a" * 64,
        "State": {"Running": True, "Health": {"Status": health}},
        "Config": {
            "Env": [k + "=" + v for k, v in env.items()],
            "Labels": {
                "com.docker.compose.project": "socialmei-team",
                "org.opencontainers.image.revision": "f" * 40,
                "com.docker.compose.project.config_files":
                    "/home/ubuntu/socialmei-team/compose.team.yaml,"
                    "/var/lib/socialmei-prisma-cutover/"
                    "gows-dual-live-20261109/compose.gows-dual.yaml",
            },
        },
    }


class ChannelPreflightTests(unittest.TestCase):
    def test_never_disclose_raw_environment_or_names(self):
        secret = "SECRET-NOT-FOR-OUTPUT-abcdefg"
        api = container(audit.CONTAINERS["api"], {
            "SOCIALMEI_WAHA_WEBHOOK_ENGINE": "WEBJS,GOWS",
            "SOCIALMEI_WAHA_INGRESS_MODE": "team-pilot",
            "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED": "false",
            "SOCIALMEI_INSTAGRAM_CLIENT_SECRET": secret,
        })
        summary = audit.allowlisted_state(api)
        summary["flags"] = audit.api_flags(api)
        rendered = json.dumps(summary)
        self.assertNotIn(secret, rendered)
        self.assertNotIn("/var/lib", rendered)
        self.assertTrue(summary["flags"]["receptor_dual_webjs_gows"])
        self.assertTrue(summary["flags"]["overlay_dual_no_compose"])

    def test_worker_destination_must_match_exactly(self):
        for target, expected in (
            ("http://socialmei-waha:3000", True),
            ("http://socialmei-waha-gows-piloto:3000", False),
            ("https://socialmei-waha:3000", False),
            ("http://socialmei-waha:3001", False),
            ("http://socialmei-waha:NOT-PORT/private", False),
            ("http://someone:secret@socialmei-waha:3000", False),
        ):
            with self.subTest(target=target):
                value = audit.worker_flags(container(
                    audit.CONTAINERS["worker"], {"SOCIALMEI_MENU_WAHA_URL": target}
                ))
                self.assertEqual(value, {"destino_webjs": expected})

    def test_session_summary_never_exposes_private_fields(self):
        raw = [{
            "state": "WORKING", "hooks": 1,
            "name": "secret-session", "phone": "sensitive-phone",
            "config": {"key": "SECRET"},
        }]
        answer = audit.session_summary(raw)
        self.assertEqual(answer["working_count"], 1)
        self.assertNotIn("secret-session", repr(answer))
        self.assertNotIn("sensitive-phone", repr(answer))
        self.assertNotIn("SECRET", repr(answer))
        self.assertEqual(
            audit.session_summary([{"state": "FAILED", "hooks": 0}])["states"],
            ["FAILED"],
        )

    def test_commands_hide_stdout_and_stderr_on_failure(self):
        failed = subprocess.CompletedProcess(
            ["docker"], 1, stdout="private-api-key", stderr="phone secret"
        )
        with patch.object(audit.subprocess, "run", return_value=failed):
            with self.assertRaises(audit.ProbeUnavailable) as err:
                audit.command("docker", "inspect", "secret", timeout=3)
        self.assertNotIn("private", repr(err.exception))
        self.assertNotIn("phone", repr(err.exception))

    def test_main_is_read_only_and_fails_closed_when_webjs_missing(self):
        def fake_inspect(name):
            if name == audit.CONTAINERS["webjs"]:
                raise audit.ProbeUnavailable()
            env = {}
            if name == audit.CONTAINERS["api"]:
                env = {"SOCIALMEI_WAHA_WEBHOOK_ENGINE": "WEBJS,GOWS"}
            elif name == audit.CONTAINERS["worker"]:
                env = {"SOCIALMEI_MENU_WAHA_URL": "http://socialmei-waha:3000"}
            return container(name, env)

        output = io.StringIO()
        with patch.object(audit, "docker_inspect", side_effect=fake_inspect), \
             patch.object(audit, "schema_count", return_value=38), \
             patch.object(audit, "get_sessions", return_value={
                 "count": 1, "states": ["FAILED"], "webhook_counts": [0],
                 "working_count": 0,
             }), \
             patch.object(audit.Path, "is_dir", return_value=False), \
             patch.object(audit.Path, "is_file", return_value=False), \
             redirect_stdout(output):
            self.assertEqual(audit.main(), 2)

        summary = json.loads(output.getvalue())
        self.assertFalse(summary["whatsapp_preservado"])
        self.assertFalse(summary["instagram_real_homologado"])
        self.assertFalse(summary["gows_real_homologado"])
        self.assertIn("container_webjs", summary["probes_indisponiveis"])
        self.assertEqual(summary["resultado"], "PARCIAL")

    def test_main_reports_preserved_webjs_without_promoting_gows_or_instagram(self):
        def fake_inspect(name):
            env = {}
            if name == audit.CONTAINERS["api"]:
                env = {
                    "SOCIALMEI_WAHA_WEBHOOK_ENGINE": "WEBJS,GOWS",
                    "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED": "false",
                }
            elif name == audit.CONTAINERS["worker"]:
                env = {"SOCIALMEI_MENU_WAHA_URL": "http://socialmei-waha:3000"}
            return container(name, env)

        def fake_sessions(name):
            if name == audit.CONTAINERS["webjs"]:
                return {"count": 1, "states": ["WORKING"],
                        "webhook_counts": [1], "working_count": 1}
            return {"count": 1, "states": ["FAILED"],
                    "webhook_counts": [0], "working_count": 0}

        output = io.StringIO()
        with patch.object(audit, "docker_inspect", side_effect=fake_inspect), \
             patch.object(audit, "schema_count", return_value=38), \
             patch.object(audit, "get_sessions", side_effect=fake_sessions), \
             patch.object(audit.Path, "is_dir", return_value=True), \
             patch.object(audit.Path, "glob", return_value=[audit.Path("/tmp/sample.tar.gz")]), \
             patch.object(audit.Path, "is_file", return_value=True), \
             redirect_stdout(output):
            self.assertEqual(audit.main(), 0)
        summary = json.loads(output.getvalue())
        self.assertTrue(summary["whatsapp_preservado"])
        self.assertEqual(summary["migrations_team"], 38)
        self.assertEqual(summary["resultado"], "BASELINE_COLETADO")
        self.assertFalse(summary["instagram_real_homologado"])
        self.assertFalse(summary["gows_real_homologado"])

    def test_probe_does_not_contain_mutating_provider_calls(self):
        self.assertIn('await fetch("http://127.0.0.1:3000/api/sessions?all=true"',
                      audit.SESSION_QUERY)
        self.assertNotIn('method: "POST"', audit.SESSION_QUERY)
        self.assertNotIn("/auth/qr", audit.SESSION_QUERY)
        self.assertNotIn("UPDATE ", audit.SCHEMA_QUERY.upper())
        self.assertIn("SET TRANSACTION READ ONLY", audit.SCHEMA_QUERY)


if __name__ == "__main__":
    unittest.main()
