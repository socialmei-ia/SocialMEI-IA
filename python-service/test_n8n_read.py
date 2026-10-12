import os
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from app import app
from fastapi.testclient import TestClient

TOKEN = "technical-read-test-token-with-48-characters-only"
DB = os.getenv("TEST_DATABASE_URL", "")


class ReadAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "SOCIALMEI_SHARED_DATA_ENABLED": "true",
                "SOCIALMEI_WORKSPACE_SLUG": "team",
                "SOCIALMEI_N8N_READ_TOKEN": TOKEN,
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)

    def test_unauthorized_requests_never_open_database(self):
        with patch("n8n_read.connect", side_effect=AssertionError("must not connect")):
            for value in [None, "Bearer wrong", "Basic " + TOKEN]:
                headers = {} if value is None else {"Authorization": value}
                for path in ["resumo", "clientes", "produtos", "vendas", "financeiro"]:
                    self.assertEqual(
                        self.client.get(
                            "/api/v1/integracoes/" + path, headers=headers
                        ).status_code,
                        401,
                    )

    def test_disabled_key_and_wrong_workspace_fail_closed(self):
        for changes in [
            {"SOCIALMEI_N8N_READ_TOKEN": ""},
            {"SOCIALMEI_WORKSPACE_SLUG": "development"},
            {"SOCIALMEI_SHARED_DATA_ENABLED": "false"},
        ]:
            with (
                patch.dict(os.environ, changes),
                patch(
                    "n8n_read.connect", side_effect=AssertionError("must not connect")
                ),
            ):
                self.assertEqual(
                    self.client.get(
                        "/api/v1/integracoes/resumo",
                        headers={"Authorization": "Bearer " + TOKEN},
                    ).status_code,
                    503,
                )

    def test_no_write_routes_exist(self):
        for method in ["POST", "PATCH", "DELETE", "PUT"]:
            for path in ["clientes", "produtos", "vendas", "financeiro"]:
                self.assertEqual(
                    self.client.request(
                        method,
                        "/api/v1/integracoes/" + path,
                        headers={"Authorization": "Bearer " + TOKEN},
                        json={},
                    ).status_code,
                    405,
                )


@unittest.skipUnless(DB, "PostgreSQL integration opt-in")
class ReadDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB) as conn:
            for path in sorted(
                (Path(__file__).resolve().parents[1] / "database/migrations").glob(
                    "*.sql"
                )
            ):
                conn.execute(path.read_text())

    def setUp(self):
        self.env = patch.dict(
            os.environ,
            {
                "DATABASE_URL": DB,
                "SOCIALMEI_SHARED_DATA_ENABLED": "true",
                "SOCIALMEI_WORKSPACE_SLUG": "team",
                "SOCIALMEI_N8N_READ_TOKEN": TOKEN,
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer " + TOKEN}
        with psycopg.connect(DB) as conn:
            conn.execute("TRUNCATE socialmei.workspaces RESTART IDENTITY CASCADE")

    def read(self, path):
        result = self.client.get("/api/v1/integracoes/" + path, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.headers["cache-control"], "no-store")
        return result.json()

    def test_empty_reads_do_not_create_workspace(self):
        self.assertEqual(
            self.read("resumo")["registros"],
            dict.fromkeys(["clientes", "produtos", "vendas", "financeiro"], 0),
        )
        self.assertEqual(self.read("clientes")["itens"], [])
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM socialmei.workspaces").fetchone()[0],
                0,
            )

    def test_pagination_workspace_isolation_and_no_stock_or_version_changes(self):
        for i in range(3):
            self.assertEqual(
                self.client.post(
                    "/api/v1/clientes", json={"nome": "Equipe " + str(i)}
                ).status_code,
                201,
            )
        product = self.client.post(
            "/api/v1/produtos", json={"nome": "Item", "preco": 10, "estoque": 8}
        ).json()
        with patch.dict(os.environ, {"SOCIALMEI_WORKSPACE_SLUG": "development"}):
            self.client.post("/api/v1/clientes", json={"nome": "Não deve aparecer"})
        with psycopg.connect(DB) as conn:
            before = conn.execute(
                "SELECT id, atualizado_em FROM socialmei.workspaces ORDER BY id"
            ).fetchall()
        first = self.read("clientes?limit=2")
        second = self.read("clientes?limit=2&offset=" + str(first["proximo_offset"]))
        self.assertEqual(len(first["itens"]), 2)
        self.assertEqual(len(second["itens"]), 1)
        self.assertIsNone(second["proximo_offset"])
        self.assertEqual(self.read("resumo")["registros"]["clientes"], 3)
        self.assertEqual(self.read("produtos")["itens"][0]["estoque"], 8)
        self.assertEqual(self.read("produtos")["itens"][0]["versao"], product["versao"])
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT id, atualizado_em FROM socialmei.workspaces ORDER BY id"
                ).fetchall(),
                before,
            )

    def test_logically_deleted_finance_is_not_returned(self):
        item = self.client.post(
            "/api/v1/financeiro",
            json={
                "operation_id": str(uuid4()),
                "descricao": "Entrada",
                "tipo": "receita",
                "valor": 12,
                "vencimento": "2026-10-12",
            },
        ).json()
        self.assertEqual(len(self.read("financeiro")["itens"]), 1)
        self.client.post(
            f"/api/v1/financeiro/{item['id']}/excluir",
            json={"operation_id": str(uuid4()), "expected_version": item["versao"]},
        )
        self.assertEqual(self.read("financeiro")["itens"], [])
        self.assertEqual(self.read("resumo")["registros"]["financeiro"], 0)
