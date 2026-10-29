"""Teste sem rede da inspeção de contratos n8n (dados sintéticos)."""
import importlib.util
import json
import subprocess
from pathlib import Path
import shutil
import unittest

spec = importlib.util.spec_from_file_location(
    "contracts", Path(__file__).resolve().parents[1] / "tools/n8n-integration-contracts.py"
)
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)


@unittest.skipUnless(shutil.which("node"), "Node.js nao disponivel")
class ContractInspectionTests(unittest.TestCase):
    def test_only_get_and_output_has_no_secret_or_raw_request(self):
        fixture = {
            "name": "[PROD] Instagram",
            "active": True,
            "activeVersionId": "published",
            "versionId": "draft",
            "nodes": [
                {
                    "name": "Webhook",
                    "type": "n8n-nodes-base.webhook",
                    "parameters": {"httpMethod": "POST", "path": "SECRET_WEBHOOK_PATH"},
                },
                {
                    "name": "SecretNode",
                    "type": "n8n-nodes-base.httpRequest",
                    "parameters": {
                        "method": "POST",
                        "url": "https://graph.instagram.com/v26.0/SECRET_ACCOUNT/messages",
                        "authentication": "genericCredentialType",
                        "genericAuthType": "httpTemplatedCustomAuth",
                        "sendBody": True,
                        "headerParameters": {
                            "parameters": [
                                {"name": "Authorization", "value": "Bearer IGAG_SECRET_TOKEN"}
                            ]
                        },
                        "bodyParameters": {
                            "parameters": [{"name": "message.text", "value": "SECRET_MESSAGE"}]
                        },
                    },
                    "credentials": {
                        "httpTemplatedCustomAuth": {"id": "SECRET_ID", "name": "SECRET_CREDENTIAL"}
                    },
                },
            ],
            "connections": {
                "Webhook": {"main": [[{"node": "SecretNode", "type": "main", "index": 0}]]}
            },
            "pinData": {"Webhook": [{"json": {"message": "SECRET_PINNED"}}]},
        }
        published = {**fixture, "nodes": fixture["nodes"][:1]}
        harness = """
        const fixture = %s;
        const published = %s;
        global.fetch = async (url, options) => {
          if (options.method && options.method !== "GET")
            throw Error("unexpected_write");
          const content = url.endsWith("/workflows/LHlqroY2xzvpYAmD?excludePinnedData=true")
            ? fixture
            : url.endsWith("/workflows/LHlqroY2xzvpYAmD/versions/published")
            ? published
            : null;
          return {ok: !!content, json: async () => content};
        };
        %s
        """ % (json.dumps(fixture), json.dumps(published), contracts.SCRIPT)
        run = subprocess.run(
            ["node", "-e", harness], input="fakekey", text=True, capture_output=True, timeout=12, check=False
        )
        self.assertEqual(run.returncode, 0, run.stderr[:500])
        report = json.loads(run.stdout)
        self.assertTrue(report["ok"])
        entry = next(r for r in report["results"] if r["id"] == "LHlqroY2xzvpYAmD")
        self.assertEqual(len(entry["saved"]["nodes"]), 2)
        self.assertEqual(len(entry["published"]["nodes"]), 1)
        self.assertEqual(entry["saved"]["nodes"][1]["destination"], "meta_instagram")
        self.assertTrue(entry["saved"]["nodes"][1]["bearer_literal"])
        self.assertEqual(entry["saved"]["edges"][0]["from"], 0)
        self.assertEqual(entry["saved"]["edges"][0]["to"], 1)
        output = json.dumps(report)
        for secret in ["SECRET_ACCOUNT", "SECRET_WEBHOOK_PATH", "SECRET_MESSAGE",
                       "SECRET_CREDENTIAL", "SECRET_ID", "IGAG_SECRET_TOKEN", "SECRET_PINNED"]:
            self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
