"""Offline metadata planning cannot provision channels or disclose private input."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "whatsapp_workspace_plan", Path(__file__).resolve().parents[1] / "tools/whatsapp-workspace-plan.py"
)
plan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plan)


def packet():
    return {"version": 1, "bindings": [{
        "workspace_id": 17, "channel_id": 27, "instance": "approved-business",
        "session": "approved-session", "account_id": "551199998888@c.us", "revision": 3,
    }]}


class WorkspacePlanTests(unittest.TestCase):
    def test_valid_plan_is_redacted_inert_and_has_no_assumed_persona(self):
        result = plan.inspect_plan(packet())
        self.assertTrue(result["plan_valid"])
        self.assertFalse(result["deployment_ready"])
        self.assertFalse(result["production_changed"])
        self.assertFalse(result["sending_available"])
        self.assertFalse(result["bot_available"])
        self.assertEqual(result["messages_sent"], 0)
        text = json.dumps(result)
        for private in ("551199998888", "approved-session", "approved-business", "Sorria", "She Style"):
            self.assertNotIn(private, text)

    def test_private_secrets_and_conflicting_bindings_are_refused(self):
        cases = []
        secret = packet(); secret["bindings"][0]["hmac_key"] = "private-never-print"
        cases.append(secret)
        for key in ("account_id", "instance", "channel_id", "session"):
            value = packet()
            second = {"workspace_id": 18, "channel_id": 28, "instance": "another-business", "session": "other-session", "account_id": "551199997777@c.us", "revision": 1}
            second[key] = value["bindings"][0][key]
            value["bindings"].append(second); cases.append(value)
        for value in cases:
            with self.subTest(), self.assertRaises(ValueError):
                plan.inspect_plan(value)

    def test_invalid_identity_types_and_unknown_fields_fail_closed(self):
        for key, value in (("workspace_id", True), ("channel_id", 0), ("revision", 1.5), ("instance", "fixture-test"), ("session", "bad\nname"), ("account_id", "group@g.us")):
            candidate = packet(); candidate["bindings"][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                plan.inspect_plan(candidate)

    def test_cli_reads_only_metadata_file_and_prints_no_secret(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "metadata.json"
            source.write_text(json.dumps(packet()))
            output = io.StringIO()
            with patch("sys.argv", ["plan", "--bindings-file", str(source)]), patch.object(plan.subprocess, "check_output", return_value="a" * 40), contextlib.redirect_stdout(output):
                plan.main()
            self.assertTrue(json.loads(output.getvalue())["plan_valid"])
            self.assertEqual(list(Path(temporary).iterdir()), [source])
            source.write_text('{"version":1,"version":1,"bindings":[]}')
            with self.assertRaises(ValueError):
                plan.load_plan(source)
