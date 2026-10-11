import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from app import app
from fastapi.testclient import TestClient

DB = os.getenv("TEST_DATABASE_URL", "").strip()


def fields(**changes):
    return {
        "descricao": "Mensalidade",
        "pessoa": "Cliente",
        "tipo": "receita",
        "valor": 12.35,
        "vencimento": "2026-10-11",
        **changes,
    }


class FinanceValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_fields_and_actions(self):
        for change in [
            {"descricao": " "},
            {"valor": -1},
            {"valor": 1.001},
            {"valor": 99999999999999},
            {"tipo": "outro"},
            {"vencimento": "2026-02-30"},
            {"cliente_id": True},
            {"status": "atrasado"},
            {"campo": 1},
            {"operation_id": "bad"},
        ]:
            response = self.client.post(
                "/api/v1/financeiro",
                json=fields(**{"operation_id": str(uuid4()), **change}),
            )
            self.assertEqual(response.status_code, 422, response.text)
        for kind in ["pagar", "excluir"]:
            response = self.client.post(
                f"/api/v1/financeiro/1/{kind}",
                json={"operation_id": str(uuid4()), "expected_version": True},
            )
            self.assertEqual(response.status_code, 422)

    def test_import_validation(self):
        item = {"local_id": 1, "lancamento": fields(status="pago")}
        for items in [
            [],
            [item, item],
            [{**item, "local_id": True}],
            [{**item, "extras": {"large": "x" * 2_000_001}}],
            [
                {
                    "local_id": 1,
                    "lancamento": fields(status="aberto", data_pagamento="2026-10-11"),
                }
            ],
        ]:
            response = self.client.post(
                "/api/v1/financeiro/importacoes/confirmar",
                json={"origem": str(uuid4()), "itens": items},
            )
            self.assertEqual(response.status_code, 422)


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class FinanceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = DB
        os.environ["SOCIALMEI_SHARED_DATA_ENABLED"] = "true"
        with psycopg.connect(DB, autocommit=True) as conn:
            for migration in sorted(
                (Path(__file__).resolve().parents[1] / "database/migrations").glob(
                    "*.sql"
                )
            ):
                conn.execute(migration.read_text(), prepare=False)
        cls.client = TestClient(app)

    def setUp(self):
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-finance"
        with psycopg.connect(DB) as conn:
            conn.execute("TRUNCATE socialmei.workspaces RESTART IDENTITY CASCADE")
        self.customer = self.client.post(
            "/api/v1/clientes", json={"nome": "Maria"}
        ).json()

    def create(self, **changes):
        payload = fields(operation_id=str(uuid4()), **changes)
        response = self.client.post("/api/v1/financeiro", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), payload

    def action(self, entry, kind, **changes):
        payload = {
            "operation_id": str(uuid4()),
            "expected_version": entry["versao"],
            **changes,
        }
        return self.client.post(
            f"/api/v1/financeiro/{entry['id']}/{kind}", json=payload
        ), payload

    def test_lifecycle_exact_money_snapshots_and_logical_delete(self):
        entry, _ = self.create(cliente_id=self.customer["id"])
        self.assertEqual(entry["pessoa"], "Maria")
        self.assertEqual(entry["valor"], 12.35)
        edit = fields(
            cliente_id=self.customer["id"],
            valor=14.25,
            expected_version=entry["versao"],
            operation_id=str(uuid4()),
        )
        response = self.client.patch(f"/api/v1/financeiro/{entry['id']}", json=edit)
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        paid, payload = self.action(updated, "pagar")
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(paid.json()["status"], "pago")
        self.assertIsNotNone(paid.json()["data_pagamento"])
        self.assertEqual(
            self.client.post(
                f"/api/v1/financeiro/{entry['id']}/pagar", json=payload
            ).json(),
            paid.json(),
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/financeiro/{entry['id']}",
                json={
                    **edit,
                    "expected_version": paid.json()["versao"],
                    "operation_id": str(uuid4()),
                },
            ).status_code,
            409,
        )
        removed, _ = self.action(paid.json(), "excluir")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/financeiro").json(), [])
        with psycopg.connect(DB) as conn:
            row = conn.execute(
                "SELECT valor, status, excluida FROM socialmei.crm_financeiro WHERE id=%s",
                (entry["id"],),
            ).fetchone()
            self.assertEqual(str(row[0]), "14.25")
            self.assertEqual(row[1:], ("pago", True))

    def test_duplicate_create_uuid_and_changed_identity(self):
        entry, payload = self.create()
        self.assertEqual(
            self.client.post("/api/v1/financeiro", json=payload).json(), entry
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/financeiro", json={**payload, "valor": 20}
            ).status_code,
            409,
        )
        self.assertEqual(len(self.client.get("/api/v1/financeiro").json()), 1)

    def test_concurrent_create_replay_and_stale_settlement(self):
        payload = fields(operation_id=str(uuid4()))
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.client.post("/api/v1/financeiro", json=payload),
                    range(2),
                )
            )
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(responses[0].json(), responses[1].json())
        entry = responses[0].json()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: self.action(entry, "pagar")[0], range(2))
            )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        paid = self.client.get(f"/api/v1/financeiro/{entry['id']}").json()
        no_change, _ = self.action(paid, "pagar")
        self.assertEqual(no_change.json()["versao"], paid["versao"])

    def test_workspace_isolation_and_invalid_client_rolls_back(self):
        entry, _ = self.create()
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "other-finance"
        self.assertEqual(self.client.get("/api/v1/financeiro").json(), [])
        self.assertEqual(
            self.client.get(f"/api/v1/financeiro/{entry['id']}").status_code, 404
        )
        self.assertEqual(self.action(entry, "pagar")[0].status_code, 404)
        response = self.client.post(
            "/api/v1/financeiro",
            json=fields(cliente_id=self.customer["id"], operation_id=str(uuid4())),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/v1/financeiro").json(), [])

    def test_client_deleted_keeps_historical_person_and_can_settle(self):
        entry, _ = self.create(cliente_id=self.customer["id"])
        response = self.client.delete(
            f"/api/v1/clientes/{self.customer['id']}?expected_version={self.customer['versao']}"
        )
        self.assertEqual(response.status_code, 204, response.text)
        row = self.client.get(f"/api/v1/financeiro/{entry['id']}").json()
        self.assertIsNone(row["cliente_id"])
        self.assertEqual(row["pessoa"], "Maria")
        self.assertEqual(self.action(row, "pagar")[0].status_code, 200)

    def test_import_atomic_replay_conflict_tombstone_and_dates(self):
        payload = {
            "origem": str(uuid4()),
            "itens": [
                {
                    "local_id": 1,
                    "lancamento": fields(status="pago"),
                    "extras": {"legacy": "keep"},
                },
                {
                    "local_id": 2,
                    "lancamento": fields(status="atrasado", tipo="despesa"),
                },
            ],
        }
        url = "/api/v1/financeiro/importacoes"
        preview = self.client.post(url + "/preview", json=payload)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["pode_importar"])
        self.assertEqual(self.client.get("/api/v1/financeiro").json(), [])
        result = self.client.post(url + "/confirmar", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        replay = self.client.post(url + "/confirmar", json=payload)
        self.assertEqual(
            [x["acao"] for x in replay.json()["itens"]], ["existente", "existente"]
        )
        rows = self.client.get("/api/v1/financeiro").json()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(x["importada"] for x in rows))
        self.assertIsNone(
            next(x for x in rows if x["status"] == "pago")["data_pagamento"]
        )
        changed = {
            **payload,
            "itens": [
                {**payload["itens"][0], "lancamento": fields(status="pago", valor=99)},
                {"local_id": 3, "lancamento": fields(status="aberto")},
            ],
        }
        self.assertEqual(
            self.client.post(url + "/confirmar", json=changed).status_code, 409
        )
        self.assertEqual(len(self.client.get("/api/v1/financeiro").json()), 2)
        self.assertEqual(self.action(rows[0], "excluir")[0].status_code, 200)
        self.assertEqual(
            self.client.post(url + "/confirmar", json=payload).status_code, 409
        )
        self.assertEqual(len(self.client.get("/api/v1/financeiro").json()), 1)

    def test_finance_actions_do_not_change_sales_or_inventory(self):
        product = self.client.post(
            "/api/v1/produtos",
            json={"nome": "Item", "preco": 10, "custo": 1, "estoque": 7, "minimo": 1},
        ).json()
        sale = self.client.post(
            "/api/v1/vendas",
            json={
                "cliente_id": self.customer["id"],
                "produto_id": product["id"],
                "data": "2026-10-11",
                "quantidade": 1,
                "preco": 10,
                "operation_id": str(uuid4()),
            },
        ).json()
        entry, _ = self.create(descricao=f"Venda #{sale['id']}")
        paid, _ = self.action(entry, "pagar")
        self.assertEqual(paid.status_code, 200)
        self.assertEqual(self.action(paid.json(), "excluir")[0].status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/vendas/{sale['id']}").json(), sale)
        self.assertEqual(
            self.client.get(f"/api/v1/produtos/{product['id']}").json()["estoque"], 6
        )
