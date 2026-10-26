"""Read-only preflight uses allowlisted output and never changes runtime state."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "release_preflight", Path(__file__).resolve().parents[1] / "tools/instagram-release-preflight.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def proxy_fixture():
    return {"apps": {"http": {"servers": {"srv0": {"routes": [{
        "match": [{"path": ["/media/instagram/*"]}],
        "handle": [{"handler": "subroute", "routes": [{
            "match": [{"method": ["GET"]}],
            "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "team-api:8000"}],
                        "headers": {"request": {"delete": ["Authorization", "Cookie"]}}}],
        }]}],
    }, {
        "match": [{"path": ["/webhooks/instagram"]}],
        "handle": [{"handler": "reverse_proxy", "upstreams": [{"dial": "team-api:8000"}]}],
    }]}}}}}


class ReleasePreflightTests(unittest.TestCase):
    def test_default_is_prepare_only_and_cannot_run_commands(self):
        with patch.object(module.pilot, "run", side_effect=AssertionError("runtime accessed")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(module.main(["--target", "team"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["mode"], "prepare_only")
        self.assertFalse(result["mutations"])
        self.assertFalse(result["calls_meta"])

    def test_ambiguous_or_production_target_rejected_before_inspection(self):
        with patch.object(module, "inspect_team", side_effect=AssertionError("runtime accessed")):
            for args in [[], ["--target", "production", "--inspect"]]:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    module.main(args)

    def test_container_output_omits_private_configuration(self):
        result = module.container_summary({
            "Image": "sha256:" + "a" * 64,
            "Config": {"Env": [
                "SOCIALMEI_INSTAGRAM_CLIENT_SECRET=private-secret",
                "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED=true",
                "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED=false",
                "SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect",
            ], "Labels": {"org.opencontainers.image.revision": "b" * 40,
                           "secret": "private-label"}},
            "State": {"Running": True, "Health": {"Status": "healthy", "Log": [{"Output": "private-health-log"}]}},
        })
        self.assertTrue(result["flags"]["SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED"])
        self.assertFalse(result["flags"]["SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED"])
        self.assertEqual(result["revision"], "b" * 40)
        self.assertEqual(result["health"], "healthy")
        self.assertNotIn("private", json.dumps(result))
        bad = module.container_summary({"Image": "private-value", "Config": {
            "Labels": {"org.opencontainers.image.revision": "private-value"}},
            "State": {"Health": {"Status": "private-value"}}})
        self.assertIsNone(bad["image_sha256"])
        self.assertIsNone(bad["revision"])
        self.assertEqual(bad["health"], "unknown")

    def test_gateway_reports_get_only_media_and_both_webhook_methods(self):
        result = module.proxy_routes(proxy_fixture())
        self.assertTrue(all(result.values()))
        self.assertEqual(module.proxy_routes({}), {key: False for key in result})

    def test_media_missing_cookie_or_ungated_method_is_not_safe(self):
        fixture = proxy_fixture()
        route = fixture["apps"]["http"]["servers"]["srv0"]["routes"][0]["handle"][0]["routes"][0]
        route["handle"][0]["headers"]["request"]["delete"] = ["Authorization"]
        self.assertFalse(module.proxy_routes(fixture)["media_strips_authorization_cookie"])
        del route["match"]
        self.assertFalse(module.proxy_routes(fixture)["media_proxy_get_only"])
        self.assertFalse(module.proxy_routes(fixture)["media_get_to_api"])

    def test_negated_route_does_not_count_as_exposed_media(self):
        fixture = proxy_fixture()
        route = fixture["apps"]["http"]["servers"]["srv0"]["routes"][0]
        route["match"] = [{"not": [{"path": ["/media/instagram/*"]}]}]
        self.assertFalse(module.proxy_routes(fixture)["media_get_to_api"])

    def test_disk_fallback_never_claims_active_configuration(self):
        with patch.object(module.pilot, "run", side_effect=[RuntimeError("private"), json.dumps(proxy_fixture())]):
            result = module.inspect_proxy("synthetic-container")
        self.assertEqual(result["source"], "disk_active_unconfirmed")
        self.assertTrue(result["routes"]["media_get_to_api"])
        self.assertNotIn("private", json.dumps(result))

    def test_sql_is_read_only_and_selects_only_counts(self):
        row = {"migration_count": 28, "migration_max": 28,
               "connected_unexpired_with_ciphertext": 1, "secret": "private"}
        with patch.object(module.pilot, "run", return_value=json.dumps(row)) as run:
            self.assertEqual(module.database_summary(), {key: row[key] for key in row if key != "secret"})
        args, kwargs = run.call_args
        self.assertIn("default_transaction_read_only=on", " ".join(args[0]))
        self.assertTrue(kwargs["input"].startswith("BEGIN READ ONLY;"))
        self.assertTrue(kwargs["input"].endswith("ROLLBACK;\n"))
        self.assertNotIn("SELECT *", kwargs["input"])
        self.assertNotIn("INSERT", kwargs["input"])

    def test_workflow_metadata_has_path_hash_not_path_or_identifiers(self):
        rows = [{"active": True, "saved_equals_active": False, "method": "POST",
                 "response_mode": "responseNode", "raw_body": True, "path_sha256": "c" * 64,
                 "path": "private-path", "id": "private-id", "secret": "private-token"},
                {"method": "private", "response_mode": "private", "path_sha256": "private"}]
        with patch.object(module.pilot, "run", return_value="synthetic_n8n"), patch.object(module, "sql_read", return_value=rows):
            result = module.workflow_summary()
        first, second = result["webhooks"]
        self.assertEqual(first["method"], "POST")
        self.assertTrue(first["raw_body"])
        self.assertFalse(first["saved_equals_active"])
        self.assertEqual(second["method"], "other")
        self.assertIsNone(second["path_sha256"])
        self.assertNotIn("private", json.dumps(result))
        self.assertIn("sha256(convert_to", module.WORKFLOW_SQL)
        self.assertEqual(result["source"], "saved_nodes_active_version_not_read")

    def test_invalid_database_name_is_rejected_without_shell_call(self):
        with patch.object(module.pilot, "run", side_effect=AssertionError("shell accessed")):
            for database in ("", "$(private)", "other; DROP DATABASE sample"):
                with self.assertRaises(RuntimeError):
                    module.sql_read("synthetic", "SELECT 1", database)

    def test_failures_are_generic_and_inspection_uses_only_fixed_read_commands(self):
        calls = []
        def failed(args, **kwargs):
            calls.append(args)
            raise RuntimeError("private-password")
        with patch.object(module.pilot, "run", side_effect=failed):
            result = module.inspect_team()
        self.assertFalse(result["complete"])
        self.assertFalse(result["gateway_requirements_confirmed"])
        self.assertNotIn("private", json.dumps(result))
        for command in calls:
            self.assertEqual(command[0], "docker")
            self.assertIn(command[1], {"inspect", "exec"})
            self.assertFalse({"restart", "compose", "recreate", "up", "cp", "curl", "ssh"} & set(command))
        with patch.object(module, "inspect_team", return_value=result), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(module.main(["--target", "team", "--inspect"]), 1)


if __name__ == "__main__":
    unittest.main()
