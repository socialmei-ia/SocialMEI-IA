import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import psycopg
from app import app
from fastapi.testclient import TestClient

DB = os.getenv("TEST_DATABASE_URL", "").strip()


def valid_sale(**changes):
    return {
        "cliente_id": 1,
        "produto_id": 1,
        "data": "2026-10-11",
        "quantidade": 2,
        "preco": 10.25,
        "desconto": 0.5,
        "pagamento": "Pix",
        "operation_id": str(uuid4()),
        **changes,
    }


class SaleValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_sales_rejected_before_database(self):
        for changes in [
            {"operation_id": "invalid"},
            {"cliente_id": True},
            {"produto_id": 0},
            {"quantidade": 0},
            {"quantidade": 1.5},
            {"preco": -1},
            {"preco": 1.001},
            {"preco": 99999999999999},
            {"desconto": 30},
            {"data": "2026-02-30"},
            {"status": "Pago"},
            {"campo": "não descartar"},
        ]:
            data = valid_sale(**changes)
            self.assertEqual(
                self.client.post("/api/v1/vendas", json=data).status_code, 422
            )
        self.assertEqual(
            self.client.post(
                "/api/v1/vendas/1/cancelar",
                json={"operation_id": str(uuid4()), "expected_version": True},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch("/api/v1/vendas/1", json=valid_sale()).status_code, 422
        )

    def test_invalid_import_batch(self):
        item = {
            "local_id": 1,
            "venda": {
                "cliente": "Maria",
                "data": "2026-10-11",
                "valor": 10,
                "status": "Pago",
            },
        }
        for items in [
            [],
            [item, item],
            [{**item, "local_id": True}],
            [{**item, "extras": {"large": "x" * 2_000_001}}],
        ]:
            self.assertEqual(
                self.client.post(
                    "/api/v1/vendas/importacoes/confirmar",
                    json={"origem": str(uuid4()), "itens": items},
                ).status_code,
                422,
            )


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class SaleIntegrationTests(unittest.TestCase):
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
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-sales"
        with psycopg.connect(DB) as conn:
            conn.execute("TRUNCATE socialmei.workspaces RESTART IDENTITY CASCADE")
        self.customer = self.client.post(
            "/api/v1/clientes", json={"nome": "Maria"}
        ).json()
        response = self.client.post(
            "/api/v1/produtos",
            json={
                "nome": "Camiseta",
                "preco": 10.25,
                "custo": 4,
                "estoque": 5,
                "minimo": 1,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.product = response.json()

    def data(self, **changes):
        return valid_sale(
            cliente_id=self.customer["id"], produto_id=self.product["id"], **changes
        )

    def sale(self, **changes):
        payload = self.data(**changes)
        response = self.client.post("/api/v1/vendas", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), payload

    def stock(self, product=None):
        return self.client.get(
            f"/api/v1/produtos/{(product or self.product)['id']}"
        ).json()["estoque"]

    def action(self, sale, kind, **changes):
        payload = {
            "operation_id": str(uuid4()),
            "expected_version": sale["versao"],
            **changes,
        }
        response = self.client.post(f"/api/v1/vendas/{sale['id']}/{kind}", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), payload

    def test_create_retry_money_and_cancel_retry_are_atomic(self):
        sale, payload = self.sale()
        self.assertEqual(sale["valor"], 20)
        self.assertEqual(self.stock(), 3)
        replay = self.client.post("/api/v1/vendas", json=payload)
        self.assertEqual(replay.status_code, 201)
        self.assertEqual(replay.json()["id"], sale["id"])
        self.assertEqual(self.stock(), 3)
        changed = {**payload, "quantidade": 1}
        self.assertEqual(
            self.client.post("/api/v1/vendas", json=changed).status_code, 409
        )
        cancelled, operation = self.action(sale, "cancelar")
        self.assertEqual(self.stock(), 5)
        retry = self.client.post(
            f"/api/v1/vendas/{sale['id']}/cancelar", json=operation
        )
        self.assertEqual(retry.status_code, 200)
        self.assertEqual(self.stock(), 5)
        excluded, _ = self.action(cancelled, "excluir")
        self.assertTrue(excluded["excluida"])
        self.assertEqual(self.stock(), 5)
        self.assertEqual(self.client.get("/api/v1/vendas").json(), [])

    def test_insufficient_stock_and_concurrent_creates_cannot_oversell(self):
        bad = self.client.post("/api/v1/vendas", json=self.data(quantidade=6))
        self.assertEqual(bad.status_code, 409, bad.text)
        self.assertEqual(self.stock(), 5)
        self.assertEqual(self.client.get("/api/v1/vendas").json(), [])
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.client.post(
                        "/api/v1/vendas", json=self.data(quantidade=4)
                    ),
                    range(2),
                )
            )
        self.assertEqual(sorted(r.status_code for r in responses), [201, 409])
        self.assertEqual(self.stock(), 1)
        self.assertEqual(len(self.client.get("/api/v1/vendas").json()), 1)

    def test_concurrent_identical_creation_and_cancel_apply_once(self):
        payload = self.data()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.client.post("/api/v1/vendas", json=payload), range(2)
                )
            )
        self.assertEqual([r.status_code for r in responses], [201, 201])
        self.assertEqual(responses[0].json()["id"], responses[1].json()["id"])
        self.assertEqual(self.stock(), 3)
        sale = responses[0].json()
        action = {"operation_id": str(uuid4()), "expected_version": 1}
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.client.post(
                        f"/api/v1/vendas/{sale['id']}/cancelar", json=action
                    ),
                    range(2),
                )
            )
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(self.stock(), 5)

    def test_draft_register_pay_cancel_and_service_do_not_double_move_stock(self):
        draft, _ = self.sale(status="Rascunho")
        self.assertEqual(self.stock(), 5)
        registered, register = self.action(draft, "registrar")
        self.assertEqual(self.stock(), 3)
        self.assertEqual(
            self.client.post(
                f"/api/v1/vendas/{draft['id']}/registrar", json=register
            ).status_code,
            200,
        )
        paid, _ = self.action(registered, "pagar")
        self.assertEqual(self.stock(), 3)
        self.action(paid, "cancelar")
        self.assertEqual(self.stock(), 5)
        service = self.client.post(
            "/api/v1/produtos", json={"nome": "Serviço", "tipo": "Serviço", "preco": 50}
        ).json()
        payload = valid_sale(
            cliente_id=self.customer["id"], produto_id=service["id"], status="Pendente"
        )
        response = self.client.post("/api/v1/vendas", json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertFalse(response.json()["estoque_aplicado"])
        # Deleting a service keeps historical names and can still mark payment.
        self.assertEqual(
            self.client.delete(
                f"/api/v1/produtos/{service['id']}", params={"expected_version": 1}
            ).status_code,
            204,
        )
        self.action(response.json(), "pagar")
        self.assertEqual(self.stock(), 5)

    def test_edit_adjusts_net_stock_and_stale_or_failed_edits_roll_back(self):
        sale, _ = self.sale()
        changes = {**self.data(quantidade=3), "expected_version": 1}
        changes.pop("status", None)
        changed = self.client.patch(f"/api/v1/vendas/{sale['id']}", json=changes)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.stock(), 2)
        self.assertEqual(
            self.client.patch(f"/api/v1/vendas/{sale['id']}", json=changes).status_code,
            200,
        )
        self.assertEqual(self.stock(), 2)
        stale = {**changes, "operation_id": str(uuid4()), "quantidade": 1}
        self.assertEqual(
            self.client.patch(f"/api/v1/vendas/{sale['id']}", json=stale).status_code,
            409,
        )
        self.assertEqual(self.stock(), 2)
        insufficient = {
            **changes,
            "operation_id": str(uuid4()),
            "expected_version": 2,
            "quantidade": 6,
        }
        self.assertEqual(
            self.client.patch(
                f"/api/v1/vendas/{sale['id']}", json=insufficient
            ).status_code,
            409,
        )
        self.assertEqual(self.stock(), 2)
        self.assertEqual(
            self.client.get(f"/api/v1/vendas/{sale['id']}").json()["quantidade"], 3
        )

    def test_product_switch_restores_original_and_paid_sale_is_immutable(self):
        sale, _ = self.sale()
        other = self.client.post(
            "/api/v1/produtos", json={"nome": "Outro", "preco": 20, "estoque": 8}
        ).json()
        data = valid_sale(
            cliente_id=self.customer["id"],
            produto_id=other["id"],
            quantidade=4,
            expected_version=1,
        )
        changed = self.client.patch(f"/api/v1/vendas/{sale['id']}", json=data)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.stock(), 5)
        self.assertEqual(self.stock(other), 4)
        paid, _ = self.action(changed.json(), "pagar")
        data.update(expected_version=paid["versao"], operation_id=str(uuid4()))
        self.assertEqual(
            self.client.patch(f"/api/v1/vendas/{sale['id']}", json=data).status_code,
            409,
        )
        self.action(paid, "excluir")
        self.assertEqual(self.stock(other), 8)

    def test_active_inventory_prevents_delete_or_type_change_of_product(self):
        sale, _ = self.sale()
        product = self.client.get(f"/api/v1/produtos/{self.product['id']}").json()
        self.assertEqual(
            self.client.delete(
                f"/api/v1/produtos/{product['id']}",
                params={"expected_version": product["versao"]},
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/produtos/{product['id']}",
                json={
                    "tipo": "Serviço",
                    "estoque": None,
                    "minimo": None,
                    "expected_version": product["versao"],
                },
            ).status_code,
            409,
        )
        self.action(sale, "cancelar")
        product = self.client.get(f"/api/v1/produtos/{product['id']}").json()
        self.assertEqual(
            self.client.delete(
                f"/api/v1/produtos/{product['id']}",
                params={"expected_version": product["versao"]},
            ).status_code,
            204,
        )

    def test_workspace_isolation_and_foreign_links(self):
        sale, _ = self.sale()
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-other-sales"
        self.assertEqual(self.client.get("/api/v1/vendas").json(), [])
        self.assertEqual(
            self.client.get(f"/api/v1/vendas/{sale['id']}").status_code, 404
        )
        self.assertEqual(
            self.client.post("/api/v1/vendas", json=self.data()).status_code, 422
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/vendas/{sale['id']}/cancelar",
                json={"operation_id": str(uuid4()), "expected_version": 1},
            ).status_code,
            404,
        )

    def test_historical_import_retry_cancel_exclude_never_moves_stock(self):
        item = {
            "local_id": 1001,
            "venda": {
                "cliente": "Maria antiga",
                "item": "Camiseta antiga",
                "cliente_id": self.customer["id"],
                "produto_id": self.product["id"],
                "data": "2026-10-10",
                "quantidade": 2,
                "valor": 25,
                "status": "Pendente",
            },
            "extras": {"original": "preservado"},
        }
        batch = {"origem": str(uuid4()), "itens": [item]}
        preview = self.client.post("/api/v1/vendas/importacoes/preview", json=batch)
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertFalse(preview.json()["estoque_movimentado"])
        self.assertEqual(self.stock(), 5)
        first = self.client.post("/api/v1/vendas/importacoes/confirmar", json=batch)
        self.assertEqual(first.status_code, 200, first.text)
        sid = first.json()["itens"][0]["venda_id"]
        self.assertEqual(
            self.client.post("/api/v1/vendas/importacoes/confirmar", json=batch).json()[
                "itens"
            ][0]["venda_id"],
            sid,
        )
        sale = self.client.get(f"/api/v1/vendas/{sid}").json()
        self.assertEqual(
            (
                sale["valor"],
                sale["cliente"],
                sale["item"],
                sale["importada"],
                sale["preco"],
            ),
            (25, "Maria antiga", "Camiseta antiga", True, None),
        )
        self.assertEqual(self.stock(), 5)
        paid, _ = self.action(sale, "pagar")
        cancelled, _ = self.action(paid, "cancelar")
        self.action(cancelled, "excluir")
        self.assertEqual(self.stock(), 5)
        self.assertEqual(
            self.client.post(
                "/api/v1/vendas/importacoes/confirmar", json=batch
            ).status_code,
            409,
        )
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT snapshot FROM socialmei.crm_venda_importacoes"
                ).fetchone()[0]["extras"],
                {"original": "preservado"},
            )

    def test_import_conflicts_origins_and_same_local_ids_are_isolated(self):
        batch = {
            "origem": str(uuid4()),
            "itens": [
                {
                    "local_id": 1,
                    "venda": {
                        "cliente": "Histórico",
                        "data": "2026-10-10",
                        "valor": 40,
                        "status": "Pago",
                    },
                }
            ],
        }
        first = self.client.post("/api/v1/vendas/importacoes/confirmar", json=batch)
        self.assertEqual(first.status_code, 200, first.text)
        batch["itens"][0]["venda"]["valor"] = 50
        batch["itens"].insert(
            0,
            {
                "local_id": 99,
                "venda": {
                    "cliente": "Novo",
                    "data": "2026-10-10",
                    "valor": 15,
                    "status": "Pago",
                },
            },
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/vendas/importacoes/confirmar", json=batch
            ).status_code,
            409,
        )
        self.assertEqual(len(self.client.get("/api/v1/vendas").json()), 1)
        batch["origem"] = str(uuid4())
        self.assertEqual(
            self.client.post(
                "/api/v1/vendas/importacoes/confirmar", json=batch
            ).status_code,
            200,
        )
        self.assertEqual(len(self.client.get("/api/v1/vendas").json()), 3)
        self.assertEqual(self.stock(), 5)
