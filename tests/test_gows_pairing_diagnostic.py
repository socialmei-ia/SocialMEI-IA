"""Offline tests for the read-only WAHA GOWS pairing diagnostics."""
import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools" / "gows_pairing_diagnostic.py"
SPEC = importlib.util.spec_from_file_location("gows_pairing_diagnostic", FILE)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


class GowsPairingDiagnosticTests(unittest.TestCase):
    def test_known_statuses_and_unknown_values_are_sanitized(self):
        for status in ("WORKING", "FAILED", "SCAN_QR_CODE",
                       "PASSKEY_REQUIRED", "PASSKEY_CONFIRMATION_REQUIRED"):
            self.assertEqual(diagnostic.safe_state(status), status)
        for unexpected in (None, [], {}, "secret-phone-number"):
            self.assertEqual(diagnostic.safe_state(unexpected), "DESCONHECIDO")
            self.assertEqual(diagnostic.safe_reason(unexpected), "NAO_INFORMADO")
        self.assertEqual(diagnostic.safe_reason("ClientOutdated"), "ClientOutdated")

    def test_private_logs_are_classified_without_exposing_raw_content(self):
        secret = "token-private-123 and phone 5511999999999"
        content = secret + " ClientOutdated PASSKEY_REQUIRED deadline exceeded"
        flags = diagnostic.signals_from_logs(content)
        self.assertTrue(flags["CLIENTE_DESATUALIZADO"])
        self.assertTrue(flags["PASSKEY"])
        self.assertTrue(flags["TIMEOUT"])
        self.assertNotIn(secret, repr(flags))
        self.assertFalse(diagnostic.signals_from_logs(None)["PASSKEY"])

    def test_docker_operations_fail_closed_before_running_any_command(self):
        with patch.object(diagnostic, "cmd", side_effect=AssertionError("called")) as invoke:
            with self.assertRaises(ValueError):
                diagnostic.docker("restart", diagnostic.GOWS)
            with self.assertRaises(ValueError):
                diagnostic.docker("exec", diagnostic.GOWS, "sh", "-c", "env")
            with self.assertRaises(ValueError):
                diagnostic.docker("exec", diagnostic.GOWS, "node", "-e", "console.log(process.env)")
            invoke.assert_not_called()

    def test_docker_logs_may_arrive_on_stderr_but_never_are_printed(self):
        result = subprocess.CompletedProcess([], 0, stdout="", stderr="PASSKEY_REQUIRED")
        with patch.object(diagnostic.subprocess, "run", return_value=result):
            data = diagnostic.cmd(["docker", "logs", "--tail", "10", diagnostic.GOWS])
            self.assertEqual(data, "\nPASSKEY_REQUIRED")
            self.assertTrue(diagnostic.signals_from_logs(data)["PASSKEY"])
            self.assertEqual(diagnostic.cmd(["docker", "inspect", diagnostic.GOWS]), "")

    def test_main_blocks_if_webjs_has_no_single_working_session(self):
        import io
        from contextlib import redirect_stdout

        def state(variables):
            return {
                "State": {"Running": True, "Health": {"Status": "healthy"}},
                "Config": {"Env": [k + "=" + v for k, v in variables.items()]},
            }

        containers = {
            diagnostic.API: state({"SOCIALMEI_WAHA_WEBHOOK_ENGINE": "WEBJS,GOWS"}),
            diagnostic.WORKER: state({"SOCIALMEI_MENU_WAHA_URL": "http://socialmei-waha:3000"}),
            diagnostic.WEBJS: state({}),
            diagnostic.GOWS: state({"WHATSAPP_DEFAULT_ENGINE": "GOWS"}),
        }

        for working_count in (0, 2):
            with self.subTest(working_count=working_count):
                old = [{"status": "WORKING"} for _ in range(working_count)]
                new = [{"status": "FAILED", "hookCount": 0}]
                output = io.StringIO()
                with patch.object(diagnostic, "inspect", side_effect=lambda name: containers[name]), \
                     patch.object(diagnostic, "inspect_backup", return_value=True), \
                     patch.object(diagnostic, "sessions",
                                  side_effect=lambda name: old if name == diagnostic.WEBJS else new), \
                     patch.object(diagnostic, "docker",
                                  side_effect=AssertionError("logs should not be queried")), \
                     redirect_stdout(output):
                    self.assertEqual(diagnostic.main(), 2)
                self.assertIn("RESULTADO = WEBJS_NAO_SAUDAVEL", output.getvalue())

    def test_worker_check_requires_exact_webjs_destination(self):
        from urllib.parse import urlparse
        self.assertEqual(urlparse("http://socialmei-waha:3000").hostname, diagnostic.WEBJS)
        self.assertNotEqual(urlparse("http://socialmei-waha-gows-piloto:3000").hostname,
                            diagnostic.WEBJS)


if __name__ == "__main__":
    unittest.main()
