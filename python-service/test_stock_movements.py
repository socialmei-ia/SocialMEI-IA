import unittest
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import test_account_auth as accounts


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class StockMovementTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)

    def test_adjustments_sale_replay_cancellation_and_tenant_scope(self):
        client = self.admin_client
        response = client.post("/api/v1/produtos", json={"nome": "Produto teste", "preco": 10, "estoque": 4, "minimo": 4})
        self.assertEqual(response.status_code, 201, response.text)
        pid = response.json()["id"]
        base = f"/api/v1/produtos/{pid}"
        delta = {"expected_version": 1, "delta": 2, "motivo": "Reposição", "operation_id": str(uuid4())}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: client.post(base + "/estoque", json=delta), range(2)))
        self.assertTrue(all(row.status_code == 200 for row in results), results[0].text)
        self.assertEqual(client.post(base + "/estoque", json={**delta, "delta": 3}).status_code, 409)
        self.assertEqual(client.post(base + "/estoque", json={**delta, "operation_id": str(uuid4()), "expected_version": 2, "delta": -9}).status_code, 409)
        venda = {"operation_id": str(uuid4()), "produto_id": pid, "quantidade": 3, "preco": "10.00", "data": "2026-11-27"}
        created = client.post("/api/v1/vendas", json=venda)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(client.post("/api/v1/vendas", json=venda).json(), created.json())
        sale = created.json()["id"]
        history = client.get(base + "/movimentacoes?tipo=saida").json()
        self.assertEqual(history["totais"], {"count": 3, "entradas": "6", "saidas": "3"})
        self.assertTrue(history["estoque_baixo"])
        movement, = history["items"]
        self.assertEqual((movement["sale_id"], movement["actor_id"], movement["previous_stock"], movement["current_stock"]), (sale, self.admin_id, 6, 3))
        cancelled = client.post(f"/api/v1/vendas/{sale}/cancelar", json={"operation_id": str(uuid4()), "expected_version": 1})
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        history = client.get(base + "/movimentacoes?limit=1").json()
        self.assertEqual(history["estoque"], 6)
        self.assertEqual(history["items"][0]["sale_id"], sale)
        self.assertEqual(history["items"][0]["current_stock"], 6)
        self.assertEqual(len(client.get(base + f"/movimentacoes?before_id={history['next_before_id']}").json()["items"]), 3)
        other = self.register("stock-movement-other@example.test")
        self.assertEqual(other.get(base + "/movimentacoes").status_code, 404)
