import unittest
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import TextInput, app, health, process_text, root


class ApiContractTests(unittest.TestCase):
    def test_versioned_n8n_http_example_runs_in_python(self):
        workflow = json.loads(
            (
                Path(__file__).parents[1] / "n8n-workflows/examples/process-text.json"
            ).read_text()
        )
        node = next(
            node
            for node in workflow["nodes"]
            if node["type"] == "n8n-nodes-base.httpRequest"
        )
        payload = json.loads(node["parameters"]["jsonBody"])
        with patch.dict("os.environ", {"SOCIALMEI_AUTH_ENABLED": "false"}):
            response = TestClient(app).post("/processar", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["maiusculo"], payload["texto"].upper())
        self.assertEqual(
            response.json()["quantidade_caracteres"], len(payload["texto"])
        )

    def test_wrong_chat_body_reproduces_required_text_error(self):
        with patch.dict("os.environ", {"SOCIALMEI_AUTH_ENABLED": "false"}):
            response = TestClient(app).post("/processar", json={"chatInput": "Olá"})
        self.assertEqual(response.status_code, 422)
        self.assertIn(
            ["body", "texto"], [error["loc"] for error in response.json()["detail"]]
        )

    def test_existing_route_contracts(self):
        routes = {route.path: route for route in app.routes if hasattr(route, "path")}
        self.assertIn("POST", routes["/processar"].methods)
        self.assertIn("GET", routes["/health"].methods)
        self.assertEqual(root(), {"status": "ok", "service": "socialmei-python"})
        self.assertEqual(health(), {"status": "healthy"})

    def test_portuguese_request_alias_and_response_fields(self):
        for text in ["", "Olá, MEI!", "ação", "🚀", " duas linhas\n "]:
            with self.subTest(text=text):
                payload = TextInput.model_validate({"texto": text})
                self.assertEqual(
                    process_text(payload),
                    {
                        "original": text,
                        "maiusculo": text.upper(),
                        "quantidade_caracteres": len(text),
                    },
                )

    def test_invalid_requests_are_rejected_by_the_model(self):
        for payload in [{}, {"texto": None}, {"texto": []}, {"text": "alias errado"}]:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    TextInput.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
