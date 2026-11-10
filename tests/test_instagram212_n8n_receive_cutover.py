"""Offline safety contracts for controlled IG212 receive-only publication."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "instagram212-n8n-receive-cutover.py"
SPEC = importlib.util.spec_from_file_location("ig212_receive_cutover", SCRIPT)
cut = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cut)


class ReceiveCutoverTests(unittest.TestCase):
    def test_no_automatic_execution(self):
        self.assertIn('if __name__ == "__main__":', SCRIPT.read_text())
        self.assertIn("explicit_receive_only_authorization_required", SCRIPT.read_text())

    def test_private_journal_write_atomic_and_private(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(cut, "B", Path(d)):
                file = Path(d) / "journal.json"
                cut.atomic(file, {"phase": "preparing"})
                self.assertEqual(file.stat().st_mode & 0o777, 0o600)
                cut.atomic(file, {"phase": "receive_only_published"})
                self.assertEqual(json.loads(file.read_text())["phase"], "receive_only_published")

    def test_receiver_flag_scope_only(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "relay.env"
            path.write_text("\n".join([
                "SOCIALMEI_INSTAGRAM_N8N_INGRESS_ENABLED='true'",
                "SOCIALMEI_INSTAGRAM_N8N_AUTH_MODE='header'",
                "SOCIALMEI_INSTAGRAM_N8N_INGRESS_KEY='" + "k"*48 + "'",
                "SOCIALMEI_INSTAGRAM_N8N_META_APP_SECRET='" + "s"*40 + "'",
                "SOCIALMEI_INSTAGRAM_N8N_ACCOUNT_BINDINGS='{\"123\":{\"workspace_id\":2,\"connection_account_id\":\"123\"}}'",
            ]) + "\n")
            path.chmod(0o600)
            with patch.object(cut, "STAGED", path), patch.object(
                cut, "private", side_effect=lambda x: x
            ):
                a = cut.private_environment()
                self.assertEqual(len(a), 5)
                self.assertNotIn("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED", a)
                self.assertNotIn("SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED", a)

    def test_reject_unexpected_staged_keys(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "relay.env"
            path.write_text("SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED='true'\n")
            with patch.object(cut, "STAGED", path), patch.object(
                cut, "private", side_effect=lambda x: x
            ):
                with self.assertRaises(cut.Block):
                    cut.private_environment()

    def test_reject_old_ai_reachable_graph(self):
        graph = {
            "ingresso": {"main": [[{"node": cut.NAMES["prepare"]}]]},
            cut.NAMES["prepare"]: {"main": [[{"node": cut.NAMES["ack"]}]]},
            cut.NAMES["ack"]: {"main": [[{"node": "legacy_ai"}]]}
        }
        self.assertIn("legacy_ai", cut.graph_reachable(graph, "ingresso"))

    def test_public_api_allowlist(self):
        self.assertIn("'POST /credentials'", cut.API_JS)
        self.assertIn("'PUT /workflows/'", cut.API_JS)
        self.assertIn("'POST /workflows/'", cut.API_JS)
        self.assertNotIn("DELETE /workflows/", cut.API_JS)

    def test_security_profile_rejects_privilege_and_mount_changes(self):
        old = {"HostConfig": {"Privileged": False}, "Mounts": []}
        changed = copy.deepcopy(old)
        changed["HostConfig"]["Privileged"] = True
        with self.assertRaises(cut.Block):
            cut.same_security(old, changed)
        changed = {"HostConfig": {"Privileged": False}, "Mounts": [{
            "Type": "bind", "Source": "/host", "Destination": "/app", "RW": True
        }]}
        with self.assertRaises(cut.Block):
            cut.same_security(old, changed)

    def test_draft_patch_requires_exact_placeholder(self):
        after = {"name": "socialmei", "settings": {}, "connections": {},
                 "nodes": [{"name": cut.NAMES["persist"],
                            "type": "n8n-nodes-base.httpRequest",
                            "credentials": {"httpBearerAuth": {
                                "id": "SOCIALMEI212_PENDING_NATIVE_CREDENTIAL"}},
                            "parameters": {"headerParameters": {"parameters": []}}}]}
        output = cut.patch_candidate(after, "native123")
        self.assertEqual(output["nodes"][0]["credentials"]["httpBearerAuth"]["id"],
                         "native123")
        self.assertIn({"name": "Content-Type", "value": "application/json"},
                      output["nodes"][0]["parameters"]["headerParameters"]["parameters"])
        self.assertEqual(after["nodes"][0]["credentials"]["httpBearerAuth"]["id"],
                         "SOCIALMEI212_PENDING_NATIVE_CREDENTIAL")

    def test_duplicate_header_is_blocked(self):
        x = {"name": "w", "connections": {}, "settings": {}, "nodes":[{
            "name": cut.NAMES["persist"], "type": "n8n-nodes-base.httpRequest",
            "credentials": {"httpBearerAuth": {"id":"SOCIALMEI212_PENDING_NATIVE_CREDENTIAL"}},
            "parameters": {"headerParameters": {
                "parameters": [{"name": "Content-Type", "value": "text/plain"}]}}
        }]}
        with self.assertRaises(cut.Block):
            cut.patch_candidate(x, "native123")

    def test_api_rollback_uses_only_team_api(self):
        before = {
            "Id": "old", "Image": "sha256:old", "RestartCount": 0,
            "State": {"StartedAt": "time", "Running": True}}
        current = copy.deepcopy(before)
        current["Id"] = "new"
        base = {"Config": {"Env": ["A=1"], "Image": "api:old"},
                "HostConfig": {}, "Mounts": []}
        recreated = copy.deepcopy(base)
        recreated["State"] = {"Health": {"Status": "healthy"}, "Running": True}
        with patch.object(cut, "inspect", return_value=current), patch.object(
            cut, "call"
        ) as execute, patch.object(cut, "wait_api", return_value=recreated), patch.object(
            cut, "same_security"
        ):
            before.update(base)
            cut.rollback_api(before, ["docker", "compose"])
        args = execute.call_args.args[0]
        self.assertEqual(args[-1], "team-api")
        self.assertIn("--no-deps", args)
        self.assertIn("--no-build", args)
        self.assertIn("--force-recreate", args)

    def test_sanitized_error_keeps_secret_out(self):
        with patch.object(cut, "activate", side_effect=Exception("PASSWORD=secret-value")
        ), patch.object(cut, "LOCK", Path("/tmp/non-existing-operator-lock")), patch(
            "os.geteuid", return_value=0
        ), patch("os.open", return_value=9), patch("fcntl.flock"), patch("os.close"), patch.object(
            cut, "getpass", return_value="some-key"
        ), patch("sys.argv", ["cutover", "--authorization", cut.AUTH]), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as out:
            self.assertEqual(cut.main(), 2)
            self.assertNotIn("secret-value", out.getvalue())

    def test_no_whatsapp_or_n8n_recreate(self):
        s = SCRIPT.read_text()
        self.assertIn('PROTECT = (', s)
        self.assertIn('"socialmei-n8n"', s)
        self.assertIn('"socialmei-waha"', s)
        self.assertNotIn("docker rm", s)
        self.assertNotIn("n8n import:workflow", s)


if __name__ == "__main__":
    unittest.main()
