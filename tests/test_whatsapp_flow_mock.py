"""Offline contract checks for the actual menu worker; HTTP calls are all mocked."""
import importlib.util
from pathlib import Path
import sys
import unittest

import httpx

spec = importlib.util.spec_from_file_location(
    "whatsapp_worker_flow",
    Path(__file__).resolve().parents[1] / "tools/whatsapp-menu-worker.py",
)
worker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)

OPERATION = "00000000-0000-4000-8000-000000000001"
RECEIPT_PATH = "/internal/whatsapp/bot/decisions/" + OPERATION + "/receipt"


class WorkerFlowContractTests(unittest.TestCase):
    def run_flow(self, *, fail_send=False):
        calls = []

        def handler(request):
            key = (request.method, request.url.path)
            calls.append(key)
            if key == ("POST", "/api/sendText") and fail_send:
                raise httpx.ConnectError("synthetic provider failure", request=request)
            responses = {
                ("GET", "/internal/whatsapp/bot/sources"): {
                    "sources": [{"instance": "pilot", "external_message_id": "external-id"}]
                },
                ("POST", "/internal/whatsapp/bot/decisions"): {
                    "operation_id": OPERATION, "status": "planned"
                },
                ("GET", "/api/sessions/01"): {
                    "name": "01", "status": "WORKING", "me": {"id": "111@c.us"}
                },
                ("POST", "/internal/whatsapp/bot/decisions/" + OPERATION + "/claim"): {
                    "dispatch_allowed": True,
                    "delivery": {
                        "path": "/api/sendText",
                        "body": {"session": "01", "chatId": "222@c.us", "text": "Menu de teste"}
                    },
                },
                ("POST", "/api/sendText"): {"id": "synthetic-provider-receipt"},
                ("POST", RECEIPT_PATH): {"status": "uncertain" if fail_send else "confirmed"},
            }
            if key not in responses:
                raise AssertionError("Unexpected HTTP operation: " + str(key))
            if key == ("POST", RECEIPT_PATH):
                import json
                payload = json.loads(request.content)
                expected = "uncertain" if fail_send else "confirmed"
                if payload["status"] != expected:
                    raise AssertionError("Incorrect receipt state")
            return httpx.Response(200, json=responses[key])

        def factory(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)

        cfg = worker.Config(
            "pilot", "01", "111@c.us",
            "secret-token-for-test", "secret-key-for-test"
        )
        result = worker.run_once(cfg, client_factory=factory)
        return result, calls

    def test_source_to_waha_send_and_receipt(self):
        result, calls = self.run_flow()
        self.assertEqual(result, "ENVIO_CONFIRMADO")
        self.assertEqual(calls.count(("POST", "/api/sendText")), 1)
        self.assertEqual(calls[-1], ("POST", RECEIPT_PATH))
        self.assertEqual(len(calls), 7)

    def test_provider_transport_failure_marks_uncertain_without_resend(self):
        result, calls = self.run_flow(fail_send=True)
        self.assertEqual(result, "RESULTADO_INCERTO_NAO_REENVIAR")
        self.assertEqual(calls.count(("POST", "/api/sendText")), 1)
        self.assertEqual(calls[-1], ("POST", RECEIPT_PATH))


if __name__ == "__main__":
    unittest.main()
