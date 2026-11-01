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
                for path in ["resumo", "relatorio", "clientes", "produtos", "vendas", "financeiro"]:
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

    def test_invalid_timezone_rejects_report_without_database_access(self):
        with patch.dict(os.environ, {"TZ": "invalid-business-timezone"}), patch(
            "n8n_read.connect", side_effect=AssertionError("Database must not open")
        ):
            result = self.client.get(
                "/api/v1/integracoes/relatorio",
                headers={"Authorization": "Bearer " + TOKEN},
            )
        self.assertEqual(result.status_code, 503)

    def test_report_period_validation_is_bounded(self):
        with patch("n8n_read.connect", side_effect=AssertionError("Invalid request")):
            for value in ("0", "367", "abc", "-1"):
                result = self.client.get(
                    "/api/v1/integracoes/relatorio?days=" + value,
                    headers={"Authorization": "Bearer " + TOKEN},
                )
                self.assertEqual(result.status_code, 422)

    def test_no_write_routes_exist(self):
        for method in ["POST", "PATCH", "DELETE", "PUT"]:
            for path in ["relatorio", "clientes", "produtos", "vendas", "financeiro"]:
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
        self.assertEqual(self.read("relatorio")["totals"]["clientes"], 0)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM socialmei.workspaces").fetchone()[0],
                0,
            )

    def test_report_uses_team_only_and_never_returns_customer_rows(self):
        self.assertEqual(
            self.client.post("/api/v1/clientes", json={"nome": "Equipe Privada"}).status_code,
            201,
        )
        with patch.dict(os.environ, {"SOCIALMEI_WORKSPACE_SLUG": "development"}):
            self.assertEqual(
                self.client.post("/api/v1/clientes", json={"nome": "Cliente Outra Empresa"}).status_code,
                201,
            )
        with psycopg.connect(DB) as conn:
            conn.execute("SELECT set_config('TimeZone', %s, true)", ("America/Recife",))
            team = conn.execute(
                "SELECT id FROM socialmei.workspaces WHERE slug=%s", ("team",),
            ).fetchone()[0]
            other = conn.execute(
                "SELECT id FROM socialmei.workspaces WHERE slug=%s", ("development",),
            ).fetchone()[0]
            for workspace, amount in ((team, 12), (other, 900)):
                conn.execute(
                    "INSERT INTO socialmei.crm_vendas("
                    "workspace_id,cliente,item,data,quantidade,preco,valor,pagamento,status"
                    ") VALUES(%s,'Cliente privado','Item privado',CURRENT_DATE,1,%s,%s,'Pix','Pago')",
                    (workspace, amount, amount),
                )
                conn.execute(
                    "INSERT INTO socialmei.crm_financeiro("
                    "workspace_id,descricao,tipo,valor,vencimento,status"
                    ") VALUES(%s,'Descrição privada','receita',%s,CURRENT_DATE,'pago')",
                    (workspace, amount),
                )
        response = self.client.get(
            "/api/v1/integracoes/relatorio?days=30", headers=self.headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        report = response.json()
        self.assertEqual(report["workspace"], "team")
        self.assertEqual(report["acesso"], "leitura")
        self.assertEqual(report["totals"]["clientes"], 1)
        self.assertEqual(report["sales_by_status"]["Pago"], {
            "quantidade": 1, "valor": "12.00",
        })
        self.assertEqual(report["finance_by_type_and_status"][0]["valor"], "12.00")
        self.assertNotIn("Cliente privado", response.text)
        self.assertNotIn("Descrição privada", response.text)
        self.assertNotIn("900.00", response.text)

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
