import unittest

from pydantic import ValidationError

from app import TextInput, app, health, process_text, root


class ApiContractTests(unittest.TestCase):
    def test_existing_route_contracts(self):
        routes = {route.path: route for route in app.routes if hasattr(route, "path")}
        self.assertIn("POST", routes["/processar"].methods)
        self.assertIn("GET", routes["/health"].methods)
        self.assertIn("GET", routes["/health/db"].methods)
        self.assertIn("GET", routes["/api/v1/clientes"].methods)
        self.assertIn("POST", routes["/api/v1/clientes"].methods)
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
