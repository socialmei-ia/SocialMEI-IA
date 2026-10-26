"""Inspector output must not disclose private runtime configuration."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("inspector", Path(__file__).resolve().parents[1] / "tools/instagram-pilot-inspect.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstagramInspectionTests(unittest.TestCase):
    def test_api_only_emits_presence_for_credentials(self):
        result = module.api_summary({"SOCIALMEI_INSTAGRAM_CLIENT_SECRET": "private-value", "SOCIALMEI_INSTAGRAM_TOKEN_KEYRING": "private-key", "UNRELATED_SECRET": "never-output"})
        self.assertTrue(result["app_secret_presente"])
        for secret in ("private-value", "private-key", "never-output"):
            self.assertNotIn(secret, json.dumps(result))

    def test_unknown_version_is_not_echoed(self):
        self.assertEqual(module.api_summary({"SOCIALMEI_INSTAGRAM_GRAPH_VERSION": "secret-value"})["graph_version"], "nao_configurada")
        self.assertEqual(module.api_summary({"SOCIALMEI_INSTAGRAM_GRAPH_VERSION": "v24.0"})["graph_version"], "v24.0")

    def test_default_logging_is_not_claimed_redacted(self):
        result = module.proxy_summary({}, "arquivo_ativo_nao_confirmado")
        self.assertFalse(result["logging_explicito"])
        self.assertEqual(result["encoders"], [])

    def test_only_whitelisted_redaction_metadata_is_output(self):
        config = {"secret": "never-output", "logging": {"logs": {"private-name": {"encoder": {"format": "filter", "fields": {"request>uri": {"filter": "delete"}, "request>headers": {"filter": "delete"}, "private-key": {"value": "never-output"}}}}}}}
        result = module.proxy_summary(config, "configuracao_ativa")
        self.assertTrue(result["encoders"][0]["remove_uri_completa"])
        self.assertTrue(result["encoders"][0]["remove_headers_request"])
        self.assertNotIn("private", json.dumps(result))
