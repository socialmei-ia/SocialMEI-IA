"""Offline gate tests for Instagram #212 psycopg 3.3.7 guarded hotfix."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

FILE = Path(__file__).resolve().parents[1] / "tools" / "instagram212-psycopg337-hotfix.py"
SPEC = importlib.util.spec_from_file_location("hotfix212", FILE)
hotfix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hotfix)


class Hotfix337Tests(unittest.TestCase):
    def test_default_cannot_deploy(self):
        with mock.patch.object(sys, "argv", ["test"]), mock.patch.object(
            hotfix, "release", side_effect=AssertionError("no release")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(hotfix.main(), 0)
            self.assertEqual(json.loads(out.getvalue())["resultado"], "PREPARE_ONLY")

    def test_apply_without_explicit_authorization_is_blocked(self):
        with mock.patch.object(sys, "argv", ["test", "--apply"]), mock.patch.object(
            hotfix, "release", side_effect=AssertionError("not authorized")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(hotfix.main(), 2)
            self.assertEqual(json.loads(out.getvalue())["motivo"],
                             "hotfix_explicit_authorization_required")

    def test_rollback_requires_separate_authorization(self):
        with mock.patch.object(sys, "argv", ["test", "--rollback"]), mock.patch.object(
            hotfix, "recover", side_effect=AssertionError("not authorized")
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(hotfix.main(), 2)
            self.assertEqual(json.loads(out.getvalue())["motivo"],
                             "rollback_authorization_required")

    def test_source_and_derived_tag_are_distinct(self):
        self.assertNotEqual(hotfix.OFFICIAL_API, hotfix.HOTFIX)
        self.assertIn(hotfix.SHA, hotfix.HOTFIX)
        self.assertIn("337", hotfix.HOTFIX)

    def test_source_image_ids_are_pinned(self):
        self.assertTrue(hotfix.OFFICIAL_API_ID.startswith("sha256:"))
        self.assertTrue(hotfix.OFFICIAL_GW_ID.startswith("sha256:"))
        self.assertNotEqual(hotfix.OFFICIAL_API_ID, hotfix.BASE_API_ID)

    def test_overlay_only_changes_image_and_release(self):
        self.assertEqual(set(hotfix.overlay("team-api")["services"]["team-api"]),
                         {"image", "environment"})
        self.assertEqual(set(hotfix.overlay("team-gateway")["services"]["team-gateway"]),
                         {"image"})
        self.assertEqual(hotfix.overlay("team-api")["services"]["team-api"]["environment"],
                         {"SOCIALMEI_RELEASE_SHA": hotfix.SHA})

    def test_same_security_rejects_privilege_change(self):
        before = {"HostConfig": {"Privileged": False}, "Mounts": []}
        after = {"HostConfig": {"Privileged": True}, "Mounts": []}
        with self.assertRaises(hotfix.Stop):
            hotfix.same_security(before, after)

    def test_same_security_rejects_mount_mutation(self):
        before = {"HostConfig": {},
                  "Mounts": [{"Type": "bind", "Source": "/one",
                              "Destination": "/config", "RW": False}]}
        after = json.loads(json.dumps(before))
        after["Mounts"][0]["RW"] = True
        with self.assertRaises(hotfix.Stop):
            hotfix.same_security(before, after)

    def test_stable_detects_recreation_and_restarts(self):
        before = {"Id": "old", "Image": "sha256:old", "RestartCount": 0,
                  "State": {"StartedAt": "t", "Running": True}}
        self.assertTrue(hotfix.stable(before, json.loads(json.dumps(before))))
        after = json.loads(json.dumps(before))
        after["Id"] = "recreated"
        self.assertFalse(hotfix.stable(before, after))
        after = json.loads(json.dumps(before))
        after["RestartCount"] = 1
        self.assertFalse(hotfix.stable(before, after))

    def test_compose_up_only_one_service_with_no_deps_or_pull(self):
        with mock.patch.object(hotfix, "run") as run:
            hotfix.compose_up(["docker", "compose", "-p", "socialmei-team"],
                              overlay_file=Path("/test/hotfix.json"),
                              service="team-api")
        args = run.call_args.args[0]
        self.assertEqual(args[-1], "team-api")
        self.assertIn("--no-deps", args)
        self.assertIn("--no-build", args)
        self.assertEqual(args[args.index("--pull") + 1], "never")

    def test_journal_atomic_private_replace(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "private.json"
            with mock.patch.object(hotfix, "JOURNAL", dest), mock.patch.object(
                hotfix, "BACKUP", Path(d)
            ):
                hotfix.write_journal({"phase": "ready"})
                self.assertEqual(json.loads(dest.read_text())["phase"], "ready")
                self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
                hotfix.write_journal({"phase": "published_api_gateway_only"})
                self.assertEqual(json.loads(dest.read_text())["phase"],
                                 "published_api_gateway_only")

    def test_rollback_refuses_unexpected_image_before_recreation(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(hotfix, "JOURNAL", Path(d) / "journal"), mock.patch.object(
                hotfix, "BACKUP", Path(d)
            ), mock.patch.object(hotfix, "docker", return_value={
                "Image": "sha256:unexpected", "State": {"Running": True}
            }), mock.patch.object(hotfix, "run",
                                 side_effect=AssertionError("must never mutate")):
                state = {"phase": "recovery_required", "attempted": ["team-api"],
                         "restored": [], "image_id": "sha256:hotfix"}
                with self.assertRaises(hotfix.Stop):
                    hotfix.rollback({hotfix.API: {"Image": hotfix.BASE_API_ID}},
                                    {"team-api": {"args": []}}, state)

    def test_rollback_completed_no_unnecessary_recreation(self):
        with tempfile.TemporaryDirectory() as d:
            current = {"Id": "old", "Image": hotfix.BASE_API_ID,
                       "State": {"Running": True, "StartedAt": "t"},
                       "RestartCount": 0}
            state = {"phase": "recovery_required", "attempted": ["team-api"],
                     "restored": [], "image_id": "sha256:hotfix"}
            with mock.patch.object(hotfix, "JOURNAL", Path(d) / "journal"), mock.patch.object(
                hotfix, "BACKUP", Path(d)
            ), mock.patch.object(hotfix, "docker", return_value=current), mock.patch.object(
                hotfix, "protected_unchanged"
            ), mock.patch.object(hotfix, "run", side_effect=AssertionError("no recreation")):
                hotfix.rollback({hotfix.API: current}, {"team-api": {"args": []}}, state)
            self.assertEqual(state["phase"], "restored_previous_images")

    def test_build_script_pins_driver_not_disable_ssl(self):
        s = FILE.read_text()
        self.assertIn("'psycopg[binary]==3.3.7'", s)
        self.assertNotIn("PGSSLMODE=disable", s)
        self.assertNotIn("sslmode=disable", s)
        self.assertIn('"--network", "container:" + API', s)
        self.assertIn('"--no-deps"', s)

    def test_runtime_failures_are_sanitized(self):
        with mock.patch.object(sys, "argv", [
            "hotfix", "--apply", "--authorization", hotfix.ALLOW
        ]), mock.patch.object(hotfix, "release", side_effect=RuntimeError(
            "POSTGRES_PASSWORD=secret-private-very-sensitive"
        )), mock.patch("os.geteuid", return_value=0), mock.patch(
            "os.open", return_value=10
        ), mock.patch("fcntl.flock"), mock.patch(
            "os.close"
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as out, mock.patch.object(
            hotfix, "JOURNAL", Path("/definitely/no/private/journal")
        ):
            self.assertEqual(hotfix.main(), 2)
            self.assertNotIn("secret-private", out.getvalue())
            self.assertEqual(json.loads(out.getvalue())["motivo"],
                             "operation_failed_details_redacted")


if __name__ == "__main__":
    unittest.main()
