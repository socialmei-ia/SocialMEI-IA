import unittest

from app import app
from fastapi.testclient import TestClient


class ClientValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_required_fields_are_rejected_before_database_access(self):
        for payload in [
            {"nome": None},
            {"nome": "   "},
            {"status": None},
            {"tags": None},
            {"tags": ["   "]},
            {"expected_version": None},
            {"expected_version": 0},
            {"expected_version": True},
            {"expected_version": 1.5},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.patch("/api/v1/clientes/1", json=payload).status_code,
                    422,
                )

    def test_unknown_fields_are_not_silently_discarded(self):
        for method, url, payload in [
            (
                self.client.post,
                "/api/v1/clientes",
                {"nome": "Teste", "campo_desconhecido": "preservar"},
            ),
            (self.client.patch, "/api/v1/clientes/1", {"cidade_typo": "Belo Jardim"}),
        ]:
            self.assertEqual(method(url, json=payload).status_code, 422)

    def test_bounded_tags_ids_and_timestamps(self):
        for payload in [
            {"nome": "Teste", "tags": ["x"] * 51},
            {"nome": "Teste", "tags": ["x" * 81]},
            {"nome": "Teste", "legacy_local_id": 9_007_199_254_740_992},
            {"nome": "Teste", "legacy_local_id": True},
            {"nome": "Teste", "criadoEm": "2026-10-11T12:00:00"},
            {"nome": "Teste", "pendente": -1},
        ]:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.client.post("/api/v1/clientes", json=payload).status_code, 422
                )

    def test_import_rejects_invalid_batches_before_database_access(self):
        valid = {"local_id": 1, "cliente": {"nome": "Maria"}}
        for payload in [
            {"origem": "invalid", "itens": [valid]},
            {"origem": "11111111-1111-4111-8111-111111111111", "itens": []},
            {"origem": "11111111-1111-4111-8111-111111111111", "itens": [valid, valid]},
            {
                "origem": "11111111-1111-4111-8111-111111111111",
                "itens": [{"local_id": True, "cliente": {"nome": "Maria"}}],
            },
            {
                "origem": "11111111-1111-4111-8111-111111111111",
                "itens": [
                    {"local_id": 1, "cliente": {"nome": "Maria", "legacy_local_id": 1}}
                ],
            },
            {
                "origem": "11111111-1111-4111-8111-111111111111",
                "itens": [{**valid, "extras": {"large": "x" * 2_000_001}}],
            },
        ]:
            with self.subTest(payload=str(payload)[:100]):
                self.assertEqual(
                    self.client.post(
                        "/api/v1/clientes/importacoes/confirmar", json=payload
                    ).status_code,
                    422,
                )


if __name__ == "__main__":
    unittest.main()
