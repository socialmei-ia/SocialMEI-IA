"""Private Instagram server preparation never enables or exposes tokens."""

import base64
import json
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.parse import urlencode

spec = importlib.util.spec_from_file_location("ig_stage", Path(__file__).resolve().parents[1] / "tools/instagram-private-config.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

HOST = "socialmei-ia.54-94-213-7.sslip.io"
SECRET = "synthetic-test-secret-value-only-0123456789"


def url():
    return "https://www.instagram.com/oauth/authorize?" + urlencode({
        "client_id": module.CLIENT_ID,
        "redirect_uri": "https://" + HOST + module.RETURN_PATH,
        "response_type": "code",
        "scope": "instagram_business_basic,instagram_business_manage_messages",
    })


class InstagramPrivateSetupTests(unittest.TestCase):
    def test_validates_url_and_scope_with_exact_callback(self):
        self.assertEqual(module._check_uri(url(), HOST, module.CLIENT_ID),
                         "instagram_business_basic,instagram_business_manage_messages")
        with self.assertRaises(RuntimeError):
            module._check_uri(url().replace(HOST, "other.example.com"), HOST, module.CLIENT_ID)
        with self.assertRaises(RuntimeError):
            module._check_uri(url() + "&state=hardcoded", HOST, module.CLIENT_ID)

    def test_rejects_activated_configuration(self):
        old = {module.HOST_KEY: HOST, "SOCIALMEI_INSTAGRAM_RUNTIME_MODE": "connect"}
        with self.assertRaises(RuntimeError):
            module.staged_values(old, prompt=lambda _: url(), hidden=lambda _: SECRET)

    def test_does_not_regenerate_existing_vault_keys(self):
        vault = base64.urlsafe_b64encode(b"a" * 32).decode().rstrip("=")
        existing = {module.HOST_KEY: HOST,
                    "SOCIALMEI_INSTAGRAM_TOKEN_KEYRING": json.dumps({"existing": vault}),
                    "SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID": "existing"}
        result = module.staged_values(existing, prompt=lambda label: "v23.0" if "Graph" in label else url(),
                                      hidden=lambda _: SECRET)
        self.assertEqual(result["SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID"], "existing")
        self.assertEqual(result["SOCIALMEI_INSTAGRAM_TOKEN_KEYRING"], json.dumps({"existing": vault}))

    def test_private_file_backup_and_safe_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / ".env.team"
            cfg.write_text("TEAM_AUTH_ENABLED=true\n" + module.HOST_KEY + "=" + HOST + "\n")
            captured = io.StringIO()
            with patch.object(module.Path, "home", return_value=root), redirect_stdout(captured):
                module.prepare(cfg,
                               prompt=lambda label: "v23.0" if "Graph" in label else url(),
                               hidden=lambda _: SECRET)
            current = cfg.read_text()
            values = module.read_environment(current)
            self.assertEqual(values["SOCIALMEI_INSTAGRAM_RUNTIME_MODE"], "disabled")
            self.assertEqual(values["SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED"], "false")
            self.assertEqual(values["SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED"], "false")
            self.assertEqual(values["SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED"], "false")
            self.assertEqual(values["SOCIALMEI_INSTAGRAM_CLIENT_SECRET"], SECRET)
            self.assertEqual(cfg.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(SECRET, captured.getvalue())
            backups = list((root / "socialmei-backups" / "instagram-pilot-inspection").glob("*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            self.assertNotIn(SECRET, backups[0].read_text())

    def test_partial_existing_vault_never_overwritten(self):
        existing = {module.HOST_KEY: HOST, "SOCIALMEI_INSTAGRAM_TOKEN_ACTIVE_KEY_ID": "key"}
        with self.assertRaises(RuntimeError):
            module.staged_values(existing, prompt=lambda _: "v23.0", hidden=lambda _: SECRET)

    def test_no_secret_in_invalid_graph_error(self):
        existing = {module.HOST_KEY: HOST}
        with self.assertRaises(RuntimeError) as context:
            module.staged_values(existing, prompt=lambda _: "latest", hidden=lambda _: SECRET)
        self.assertNotIn(SECRET, str(context.exception))


if __name__ == "__main__":
    unittest.main()
