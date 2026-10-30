"""Offline safety tests for the Ubuntu WhatsApp pilot operator."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "team_whatsapp_pilot", ROOT / "tools" / "team-whatsapp-pilot.py"
)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class PilotTests(unittest.TestCase):
    def test_account_identity_requires_valid_direct_jid(self):
        self.assertEqual(pilot.account_id({"id": "551199998888@c.us"}),
                         "551199998888@c.us")
        self.assertIsNone(pilot.account_id({"id": "group@g.us"}))
        self.assertIsNone(pilot.account_id({"id": {"user": "5511"}}))

    def test_private_registry_mode_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)
            binding = {
                "instance": "pilot", "session": "default", "account_id": "5511@c.us",
                "workspace_id": 1, "channel_id": 123, "hmac_key": "z" * 32, "revision": 1
            }
            f = pilot.registry_file(path, binding)
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
            data = json.loads(f.read_text())
            self.assertEqual(data["version"], 1)
            self.assertEqual(data["bindings"], [binding])
            with self.assertRaises(pilot.Blocked):
                pilot.registry_file(path, binding)

    def mocked(self, path):
        api = {"NetworkSettings": {"Networks": {"api": {}}}}
        waha = {"NetworkSettings": {"Networks": {"default": {}}}}
        n8n = {"NetworkSettings": {"Networks": {"default": {}}}}
        def ins(name):
            return {pilot.API: api, pilot.WAHA: waha, pilot.N8N: n8n}[name]
        session = {"name": "default", "account": "558192475976@c.us",
                   "engine": "WEBJS"}
        def db(op, **data):
            if op == "inspect":
                return {"workspace_exists": True, "channel_count": 0,
                        "manager_count": 1}
            if op == "reserve":
                return {"channel_id": 22, "revision": 1}
            if op == "finalize":
                return {"finalized": True}
            raise AssertionError("Unexpected operation")
        return ins, session, db

    def test_readonly_default_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            ins, sess, db = self.mocked(Path(d))
            with patch.object(pilot, "inspect", side_effect=ins), \
                 patch.object(pilot, "session_info", return_value=sess), \
                 patch.object(pilot, "database", side_effect=db) as dbmock, \
                 patch.object(pilot, "private_dir", return_value=Path(d)), \
                 patch.object(pilot, "registry_file") as writer, \
                 patch.object(sys, "argv", ["script"]), \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                pilot.main()
            self.assertEqual([c.args[0] for c in dbmock.call_args_list], ["inspect"])
            writer.assert_not_called()
            self.assertIn("MODO: LEITURA", stdout.getvalue())
            self.assertNotIn("558192475976@c.us", stdout.getvalue())

    def test_explicit_prepare_creates_registry_and_channel_without_enabling_send(self):
        with tempfile.TemporaryDirectory() as d:
            ins, sess, db = self.mocked(Path(d))
            with patch.object(pilot, "inspect", side_effect=ins), \
                 patch.object(pilot, "session_info", return_value=sess), \
                 patch.object(pilot, "database", side_effect=db) as dbmock, \
                 patch.object(pilot, "private_dir", return_value=Path(d)), \
                 patch.object(sys, "argv", ["script", "--prepare-channel",
                                            "--confirm", "TEAM-1"]), \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                pilot.main()
            self.assertEqual(
                [c.args[0] for c in dbmock.call_args_list],
                ["inspect", "reserve", "finalize"]
            )
            self.assertIn("MENSAGENS_ENVIADAS: 0", stdout.getvalue())
            self.assertNotIn(sess["hmac"], stdout.getvalue())
            registry = json.loads((Path(d) / "waha-registry.json").read_text())
            binding = registry["bindings"][0]
            self.assertEqual(binding["channel_id"], 22)
            self.assertGreaterEqual(len(binding["hmac_key"].encode()), 32)
            self.assertNotIn(binding["hmac_key"], stdout.getvalue())

    def test_prepare_requires_exact_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            ins, sess, db = self.mocked(Path(d))
            with patch.object(pilot, "inspect", side_effect=ins), \
                 patch.object(pilot, "session_info", return_value=sess), \
                 patch.object(pilot, "database", side_effect=db) as dbmock, \
                 patch.object(pilot, "private_dir", return_value=Path(d)), \
                 patch.object(sys, "argv", ["script", "--prepare-channel"]):
                with self.assertRaises(pilot.Blocked):
                    pilot.main()
            self.assertEqual([c.args[0] for c in dbmock.call_args_list], ["inspect"])
            self.assertFalse((Path(d) / "waha-registry.json").exists())


if __name__ == "__main__":
    unittest.main()
