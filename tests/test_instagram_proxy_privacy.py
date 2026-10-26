"""Safe Caddy logging preparation tests. Optional real Caddy runs in Docker only."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("instagram_privacy", ROOT / "tools/instagram-proxy-privacy.py")
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class LoggingPatchTests(unittest.TestCase):
    def test_new_global_block_keeps_original_sites(self):
        original = "# site\n:8080 {\n respond ok\n}\n"
        patched = privacy.with_logging(original)
        self.assertTrue(patched.endswith(original))
        self.assertEqual(patched.count("log default"), 1)

    def test_site_address_env_placeholder_is_not_global_options(self):
        original = "# live n8n host\\n{$N8N_HOST} {\\n reverse_proxy n8n:5678\\n}\\n"
        patched = privacy.with_logging(original)
        self.assertTrue(patched.startswith("{\\n"))
        self.assertTrue(patched.endswith(original))
        self.assertEqual(patched.count("log default"), 1)
        self.assertEqual(privacy._global_block(original), None)
        self.assertIsNotNone(privacy._global_block(patched))

    def test_standalone_global_open_with_comment_is_recognized(self):
        original = "{ # options\\n email admin@example.test\\n}\\n:80 { respond ok }\\n"
        patched = privacy.with_logging(original)
        self.assertEqual(patched.count("log default"), 1)
        self.assertIn("email admin@example.test", patched)

    def test_existing_global_preserves_braces_in_comments_and_strings(self):
        original = '# start\n{\n # }\n email "admin{example}@example.test"\n}\n:8080 { respond ok }'
        patched = privacy.with_logging(original)
        self.assertIn('email "admin{example}@example.test"', patched)
        self.assertLess(patched.index("log default"), patched.index(":8080"))
        self.assertTrue(patched.endswith(":8080 { respond ok }"))

    def test_unterminated_global_is_rejected(self):
        with self.assertRaises(RuntimeError):
            privacy.with_logging("{\n email example.com")

    def test_existing_global_default_logger_is_rejected(self):
        with self.assertRaises(RuntimeError):
            privacy.with_logging("{\n log default { format json }\n}\n:8080 { respond ok }")

    def test_only_logging_change_is_accepted(self):
        before = {"apps": {"http": {"route": "same"}}, "admin": {"listen": "localhost:2019"}}
        after = copy.deepcopy(before)
        after["logging"] = {"logs": {"default": {"encoder": copy.deepcopy(privacy.ENCODER)}}}
        self.assertTrue(privacy.logging_only(before, after))
        after["apps"]["http"]["route"] = "changed"
        self.assertFalse(privacy.logging_only(before, after))
        after["apps"]["http"]["route"] = "same"
        after["admin"]["listen"] = "0.0.0.0:2019"
        self.assertFalse(privacy.logging_only(before, after))

    def test_unknown_logger_is_not_overwritten(self):
        before = {"logging": {"logs": {"private": {"encoder": {"format": "console"}}}}}
        after = {"logging": {"logs": {"private": {"encoder": {"format": "console"}}, "default": {"encoder": privacy.ENCODER}}}}
        self.assertFalse(privacy.logging_only(before, after))

    def test_existing_default_logger_must_be_manually_reviewed(self):
        before = {"logging": {"logs": {"default": {"encoder": {"format": "console"}}}}}
        after = {"logging": {"logs": {"default": {"encoder": copy.deepcopy(privacy.ENCODER)}}}}
        self.assertFalse(privacy.logging_only(before, after))

    def test_idempotent_protection_and_extra_logger(self):
        config = {"logging": {"logs": {"default": {"encoder": copy.deepcopy(privacy.ENCODER)}}}}
        self.assertTrue(privacy.protected(config))
        config["logging"]["logs"]["raw"] = {"encoder": {"format": "json"}}
        self.assertFalse(privacy.protected(config))

    def test_secret_fields_must_all_be_filtered(self):
        config = {"logging": {"logs": {"default": {"encoder": copy.deepcopy(privacy.ENCODER)}}}}
        for field in privacy.ENCODER["fields"]:
            bad = copy.deepcopy(config)
            del bad["logging"]["logs"]["default"]["encoder"]["fields"][field]
            self.assertFalse(privacy.protected(bad))

    def test_write_private_creates_restricted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "new.Caddyfile"
            privacy._write_private(path, "synthetic only")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), "synthetic only")

    def test_prepare_does_not_run_apply_or_reload(self):
        original = ":8080 { respond ok }"
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(privacy, "_candidate", return_value=(original, privacy.with_logging(original))) as mock:
                privacy.prepare(Path(tmp) / "private")
                self.assertEqual(mock.call_count, 2)
            files = sorted(p.name for p in (Path(tmp) / "private").iterdir())
            self.assertEqual(files, [
                "gateway.candidate.Caddyfile", "gateway.original.Caddyfile",
                "public.candidate.Caddyfile", "public.original.Caddyfile", "sha256.json",
            ])

    def test_compose_passes_all_runtime_settings_with_safe_defaults(self):
        compose = (ROOT / "compose.team.yaml").read_text()
        for key in (
            "RUNTIME_MODE", "CLIENT_ID", "CLIENT_SECRET", "GRAPH_VERSION",
            "SCOPES", "AUTHORIZATION_EMBED", "TOKEN_KEYRING", "TOKEN_ACTIVE_KEY_ID",
            "WEBHOOK_VERIFY_TOKEN", "RUNTIME_INGRESS_ENABLED", "RUNTIME_SEND_ENABLED",
            "PROXY_PRIVACY_REVIEWED",
        ):
            name = "SOCIALMEI_INSTAGRAM_" + key
            self.assertIn(name + ": ${" + name + ":-", compose)
        for key in ("RUNTIME_MODE", "RUNTIME_SEND_ENABLED", "RUNTIME_INGRESS_ENABLED", "PROXY_PRIVACY_REVIEWED"):
            name = "SOCIALMEI_INSTAGRAM_" + key
            safe = "disabled" if key == "RUNTIME_MODE" else "false"
            self.assertIn(name + ": ${" + name + ":-" + safe + "}", compose)


@unittest.skipUnless(os.getenv("SOCIALMEI_INSTAGRAM_PROXY_TEST") == "true", "Disposable Caddy opt-in")
class RealCaddyPrivacyTests(unittest.TestCase):
    def test_candidate_matches_live_disposable_caddy(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "Caddyfile"
            config.write_text(":8080 {\n respond ok\n}\n")
            name = "socialmei-ig-candidate-" + uuid4().hex[:10]
            try:
                subprocess.run(
                    ["docker", "run", "-d", "--name", name, "--network", "none",
                     "--mount", f"type=bind,src={config},dst=/etc/caddy/Caddyfile,readonly",
                     "caddy:2-alpine"],
                    capture_output=True, check=True, timeout=45,
                )
                for _ in range(35):
                    probe = subprocess.run(
                        ["docker", "exec", name, "wget", "-qO-",
                         "http://127.0.0.1:2019/config/"],
                        capture_output=True, timeout=10,
                    )
                    if probe.returncode == 0:
                        break
                    time.sleep(.2)
                else:
                    self.fail("Disposable Caddy admin API unavailable")
                original, candidate = privacy._candidate(name)
                self.assertIn("respond ok", original)
                self.assertIn("log default", candidate)
                self.assertNotIn("log default", original)
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)

    def test_502_keeps_error_without_oauth_uri_or_headers(self):
        original = "{\n admin off\n auto_https off\n}\n:8080 {\n reverse_proxy 127.0.0.1:1\n}\n"
        marker = "synthetic-oauth-canary-" + uuid4().hex
        with tempfile.TemporaryDirectory() as tmp:
            for label, source in (("original", original), ("filtered", privacy.with_logging(original))):
                config = Path(tmp) / (label + ".Caddyfile")
                config.write_text(source)
                name = "socialmei-ig-privacy-" + uuid4().hex[:10]
                try:
                    subprocess.run(
                        ["docker", "run", "-d", "--name", name, "--network", "none",
                         "--mount", f"type=bind,src={config},dst=/etc/caddy/Caddyfile,readonly",
                         "caddy:2-alpine"],
                        capture_output=True, check=True, timeout=45,
                    )
                    request = ["docker", "exec", name, "wget", "-T", "2", "-S", "-O",
                               "/dev/null", "--header=X-Test-Secret: " + marker,
                               "http://127.0.0.1:8080/api/v1/instagram/meta/oauth/return?code="
                               + marker + "&state=" + marker]
                    for _ in range(35):
                        response = subprocess.run(request, capture_output=True, text=True, timeout=10)
                        if "502" in response.stderr:
                            break
                        time.sleep(.2)
                    else:
                        self.fail("Disposable Caddy did not return the fixture 502")
                    result = subprocess.run(["docker", "logs", name], check=True, capture_output=True, text=True, timeout=15)
                    output = result.stdout + result.stderr
                    errors = []
                    for line in output.splitlines():
                        try:
                            data = json.loads(line)
                        except ValueError:
                            continue
                        if data.get("level") == "error":
                            errors.append(data)
                    self.assertTrue(errors, "Caddy must retain diagnostics")
                    self.assertEqual(marker in output, label == "original")
                    for error in errors:
                        self.assertIn("msg", error)
                        if label == "filtered":
                            request = error.get("request") or {}
                            self.assertNotIn("uri", request)
                            self.assertNotIn("headers", request)
                            self.assertNotIn("resp_headers", error)
                finally:
                    subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
