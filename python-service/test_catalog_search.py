"""Catalog search uses real sessions and disposable PostgreSQL only."""

import unittest
from unittest.mock import patch

import test_account_auth as accounts
from app import app
from fastapi.testclient import TestClient


class CatalogFilterValidationTests(unittest.TestCase):
    def test_invalid_filters_rejected_without_reading_database(self):
        with patch(
            "catalog_data.connect", side_effect=AssertionError("unexpected database")
        ):
            client = TestClient(app)
            for params in (
                {"q": "x" * 161},
                {"q": "\x00"},
                {"tipo": "Invalid"},
                {"status": ""},
                {"status": "x" * 31},
                {"estoque_baixo": "invalid"},
            ):
                with self.subTest(params=list(params)):
                    self.assertEqual(
                        client.get("/api/v1/produtos", params=params).status_code, 422
                    )


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL not configured")
class CatalogSearchTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def seed(self):
        self.owner = self.register("catalog-owner@example.test")
        self.other = self.register("catalog-other@example.test")
        items = [
            {
                "nome": "Perfume 100%",
                "tipo": "Produto",
                "preco": 30,
                "estoque": 2,
                "minimo": 3,
                "status": "Ativo",
            },
            {
                "nome": "Perfume premium",
                "tipo": "Produto",
                "preco": 50,
                "estoque": 10,
                "minimo": 2,
                "status": "Ativo",
            },
            {
                "nome": "Corte de cabelo",
                "tipo": "Serviço",
                "preco": 40,
                "status": "Ativo",
            },
            {
                "nome": "Item arquivado",
                "tipo": "Produto",
                "preco": 10,
                "estoque": 0,
                "minimo": 0,
                "status": "Inativo",
            },
        ]
        for item in items:
            response = self.owner.post("/api/v1/produtos", json=item)
            self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(
            self.other.post(
                "/api/v1/produtos", json={"nome": "Perfume privado", "preco": 9}
            ).status_code,
            201,
        )

    def names(self, params):
        response = self.owner.get("/api/v1/produtos", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return [row["nome"] for row in response.json()]

    def test_search_is_literal_case_insensitive_and_preserves_default_contract(self):
        self.seed()
        self.assertEqual(len(self.names({})), 4)
        self.assertEqual(
            self.names({"q": "PERFUME"}), ["Perfume 100%", "Perfume premium"]
        )
        self.assertEqual(self.names({"q": "%"}), ["Perfume 100%"])
        self.assertEqual(self.names({"q": "' OR 1=1--"}), [])

    def test_combined_filters_and_low_inventory_do_not_treat_services_as_stock(self):
        self.seed()
        self.assertEqual(self.names({"tipo": "Serviço"}), ["Corte de cabelo"])
        self.assertEqual(
            self.names({"estoque_baixo": "true", "status": "Ativo"}), ["Perfume 100%"]
        )
        self.assertEqual(self.names({"estoque_baixo": "true", "tipo": "Serviço"}), [])
        self.assertEqual(self.names({"status": "Inativo"}), ["Item arquivado"])

    def test_filters_cannot_read_other_business_or_mutate_catalog(self):
        self.seed()
        self.assertEqual(
            self.names(
                {"q": "privado", "workspace_id": self.other.identity["negocio"]["id"]}
            ),
            [],
        )
        response = self.other.get("/api/v1/produtos", params={"q": "perfume"})
        self.assertEqual([r["nome"] for r in response.json()], ["Perfume privado"])
        self.assertEqual(self.names({"q": "not found"}), [])
        self.assertEqual(len(self.names({})), 4)
        self.assertEqual(
            TestClient(app, base_url=accounts.ORIGIN)
            .get("/api/v1/produtos", params={"q": "perfume"})
            .status_code,
            401,
        )
