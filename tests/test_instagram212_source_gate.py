"""Offline rejection tests; never accesses GitHub, AWS, Meta or n8n."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools" / "instagram212-source-gate.py"
SPEC = importlib.util.spec_from_file_location("instagram212_source_gate", FILE)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class Instagram212OfflineGateTests(unittest.TestCase):
    def candidate_files(self):
        return {
            "python-service/instagram_n8n_ingress.py": (
                'PATH = "/webhooks/instagram/n8n"\n'
                "def ingress_service():\n"
                " settings.instagram_n8n_ingress_enabled()\n"
                " settings.instagram_n8n_ingress_configuration()\n"
                " parse_message_events(raw, meta_signature, secret)\n"
                " persist_authenticated_events(events, canonical_bindings)\n"
                "@router.post(PATH)\n"
            ),
            "deploy/team/Caddyfile": (
                "@instagram_n8n_ingress {\n"
                " method POST\n path /webhooks/instagram/n8n\n}\n"
                "handle @instagram_n8n_ingress {\n reverse_proxy team-api:8000\n}\n"
            ),
            "python-service/app.py": (
                "from instagram_n8n_ingress import router as instagram_n8n_ingress_router\n"
                "app.include_router(instagram_n8n_ingress_router)\n"
            ),
            "python-service/settings.py": (
                "def instagram_n8n_ingress_enabled():\n pass\n"
                "def instagram_n8n_ingress_configuration():\n pass\n"
            ),
            "tools/prepare-instagram-persistence.mjs": (
                'resumeLegacy = false\n'
                'responseMode = "responseNode"\n'
                "rawBody: true\n"
                'apiOrigin + "/webhooks/instagram/n8n"\n'
                "automatically_publish: false\n"
                "candidate.connections[NAMES.ack] = { main: resumeLegacy ? [[edge(NAMES.resume)]] : [[]] };\n"
                "candidate.connections[NAMES.resume] = resumeLegacy ? old : { main: [[]] };\n"
            ),
        }

    def test_positive_contracts_still_do_not_allow_cutover(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in self.candidate_files().items():
                file = root / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            result = gate.inspect(root, revision=gate.CANDIDATE)
            self.assertTrue(result["contracts_ok"])
            self.assertFalse(result["cutover_approved"])
            self.assertFalse(result["aws_changed"])
            self.assertIn("backup_restore_in_isolated_target", result["pending_manual_gates"])

    def test_mismatch_sha_fails(self):
        with self.assertRaisesRegex(ValueError, "candidate_sha_mismatch"):
            gate.inspect(".", revision=gate.BASELINE)

    def test_missing_source_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "candidate_file_unavailable"):
                gate.inspect(directory, revision=gate.CANDIDATE)

    def test_no_post_gateway_is_not_ready(self):
        data = self.candidate_files()
        data["deploy/team/Caddyfile"] = data["deploy/team/Caddyfile"].replace("method POST", "method GET")
        self.assertFalse(gate.inspect_sources(data)["gateway_post_only_n8n_path"])

    def test_resume_legacy_default_is_not_accepted(self):
        data = self.candidate_files()
        data["tools/prepare-instagram-persistence.mjs"] = data[
            "tools/prepare-instagram-persistence.mjs"
        ].replace("resumeLegacy = false", "resumeLegacy = true")
        self.assertFalse(gate.inspect_sources(data)["workflow_prepared_not_published"])

    def test_missing_authenticated_ingress_fails(self):
        data = self.candidate_files()
        data["python-service/instagram_n8n_ingress.py"] = data[
            "python-service/instagram_n8n_ingress.py"
        ].replace("settings.instagram_n8n_ingress_enabled()", "True")
        self.assertFalse(gate.inspect_sources(data)["n8n_endpoint_protected"])

    def test_missing_api_registration_fails(self):
        data = self.candidate_files()
        data["python-service/app.py"] = ""
        self.assertFalse(gate.inspect_sources(data)["endpoint_registered"])


if __name__ == "__main__":
    unittest.main()
