import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
from app import app
from fastapi.testclient import TestClient

DB = os.getenv("TEST_DATABASE_URL", "").strip()


class CatalogValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_catalog_and_inventory_are_rejected_without_database(self):
        for data in [
            {"nome": " ", "preco": 10},
            {"nome": "P", "preco": -1},
            {"nome": "P", "preco": 10, "estoque": -1},
            {"nome": "P", "preco": 10, "estoque": 1.5},
            {"nome": "P", "preco": 10, "estoque": True},
            {"nome": "P", "preco": 10, "estoque": None},
            {"nome": "S", "tipo": "Serviço", "preco": 10, "estoque": 0},
            {"nome": "P", "preco": 10, "campo": "não descartar"},
        ]:
            with self.subTest(data=data):
                self.assertEqual(
                    self.client.post("/api/v1/produtos", json=data).status_code, 422
                )
        for data in [
            {"nome": "Outra"},
            {"expected_version": True},
            {"expected_version": 1, "preco": None},
        ]:
            self.assertEqual(
                self.client.patch("/api/v1/produtos/1", json=data).status_code, 422
            )
        for data in [
            {"delta": 0, "expected_version": 1},
            {"delta": 1.5, "expected_version": 1},
            {"delta": 1},
        ]:
            self.assertEqual(
                self.client.post("/api/v1/produtos/1/estoque", json=data).status_code,
                422,
            )
        self.assertEqual(self.client.delete("/api/v1/produtos/1").status_code, 422)

    def test_import_batch_validation(self):
        item = {"local_id": 1, "produto": {"nome": "P", "preco": 10}}
        for items in [
            [],
            [item, item],
            [{**item, "local_id": True}],
            [{**item, "extras": {"large": "x" * 2_000_001}}],
        ]:
            response = self.client.post(
                "/api/v1/produtos/importacoes/confirmar",
                json={"origem": "11111111-1111-4111-8111-111111111111", "itens": items},
            )
            self.assertEqual(response.status_code, 422)


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class CatalogIntegrationTests(unittest.TestCase):
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
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-catalog"
        with psycopg.connect(DB) as conn:
            conn.execute("TRUNCATE socialmei.workspaces RESTART IDENTITY CASCADE")

    def create(self, **fields):
        r = self.client.post(
            "/api/v1/produtos",
            json={
                "nome": "Produto teste",
                "preco": 19.9,
                "custo": 7.25,
                "estoque": 4,
                "minimo": 2,
                **fields,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def batch(self, origem="11111111-1111-4111-8111-111111111111"):
        return {
            "origem": origem,
            "itens": [
                {
                    "local_id": 1,
                    "produto": {
                        "nome": "Importado",
                        "preco": 10,
                        "estoque": 2,
                        "minimo": 1,
                    },
                    "extras": {"codigoLegado": "ABC"},
                }
            ],
        }

    def test_profile_type_transitions_and_stale_edits_deletes(self):
        p = self.create()
        url = f"/api/v1/produtos/{p['id']}"
        r = self.client.patch(url, json={"nome": "Editado", "expected_version": 1})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            (
                r.json()["preco"],
                r.json()["custo"],
                r.json()["estoque"],
                r.json()["versao"],
            ),
            (19.9, 7.25, 4, 2),
        )
        self.assertEqual(
            self.client.patch(
                url, json={"nome": "Antigo", "expected_version": 1}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.delete(url, params={"expected_version": 1}).status_code, 409
        )
        self.assertEqual(
            self.client.patch(
                url, json={"tipo": "Serviço", "expected_version": 2}
            ).status_code,
            422,
        )
        service = self.client.patch(
            url,
            json={
                "tipo": "Serviço",
                "estoque": None,
                "minimo": None,
                "expected_version": 2,
            },
        )
        self.assertEqual(service.status_code, 200, service.text)
        self.assertIsNone(service.json()["estoque"])
        self.assertEqual(
            self.client.post(
                url + "/estoque", json={"delta": 1, "expected_version": 3}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch(
                url, json={"tipo": "Produto", "expected_version": 3}
            ).status_code,
            422,
        )
        product = self.client.patch(
            url,
            json={"tipo": "Produto", "estoque": 8, "minimo": 1, "expected_version": 3},
        )
        self.assertEqual(product.status_code, 200, product.text)
        self.assertEqual(
            self.client.delete(url, params={"expected_version": 4}).status_code, 204
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_atomic_stock_rejects_negative_and_repeated_or_concurrent_requests(self):
        p = self.create()
        url = f"/api/v1/produtos/{p['id']}"
        self.assertEqual(
            self.client.post(
                url + "/estoque", json={"delta": -5, "expected_version": 1}
            ).status_code,
            409,
        )
        self.assertEqual(self.client.get(url).json()["versao"], 1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda _: self.client.post(
                        url + "/estoque", json={"delta": -1, "expected_version": 1}
                    ),
                    range(2),
                )
            )
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.client.get(url).json()["estoque"], 3)

    def test_import_preview_retry_extras_conflicts_and_tombstone(self):
        endpoint = "/api/v1/produtos/importacoes/"
        batch = self.batch()
        preview = self.client.post(endpoint + "preview", json=batch)
        self.assertEqual(preview.status_code, 200, preview.text)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT count(*) FROM socialmei.workspaces").fetchone()[0],
                0,
            )
        first = self.client.post(endpoint + "confirmar", json=batch)
        self.assertEqual(first.status_code, 200, first.text)
        pid = first.json()["itens"][0]["produto_id"]
        self.client.patch(
            f"/api/v1/produtos/{pid}", json={"preco": 25, "expected_version": 1}
        )
        retry = self.client.post(endpoint + "confirmar", json=batch)
        self.assertEqual(retry.json()["itens"][0]["produto_id"], pid)
        self.assertEqual(retry.json()["itens"][0]["acao"], "existente")
        self.assertEqual(self.client.get(f"/api/v1/produtos/{pid}").json()["preco"], 25)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT snapshot FROM socialmei.crm_produto_importacoes"
                ).fetchone()[0]["extras"],
                {"codigoLegado": "ABC"},
            )
        changed = self.batch()
        changed["itens"][0]["produto"]["preco"] = 12
        changed["itens"].insert(
            0, {"local_id": 99, "produto": {"nome": "Novo", "preco": 8}}
        )
        self.assertEqual(
            self.client.post(endpoint + "confirmar", json=changed).status_code, 409
        )
        self.assertEqual(len(self.client.get("/api/v1/produtos").json()), 1)
        self.client.delete(f"/api/v1/produtos/{pid}", params={"expected_version": 2})
        deleted = self.client.post(endpoint + "confirmar", json=batch)
        self.assertEqual(deleted.status_code, 409)
        self.assertEqual(deleted.json()["detail"]["itens"][0]["acao"], "excluido")

    def test_origins_workspaces_and_concurrent_imports(self):
        endpoint = "/api/v1/produtos/importacoes/confirmar"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda _: self.client.post(endpoint, json=self.batch()), range(2)
                )
            )
        self.assertEqual([r.status_code for r in results], [200, 200])
        pid = results[0].json()["itens"][0]["produto_id"]
        self.assertEqual(results[1].json()["itens"][0]["produto_id"], pid)
        other = self.client.post(
            endpoint, json=self.batch("22222222-2222-4222-8222-222222222222")
        )
        self.assertEqual(other.status_code, 200, other.text)
        self.assertNotEqual(other.json()["itens"][0]["produto_id"], pid)
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-catalog-other"
        self.assertEqual(self.client.get("/api/v1/produtos").json(), [])
        self.assertEqual(self.client.get(f"/api/v1/produtos/{pid}").status_code, 404)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/produtos/{pid}", json={"nome": "Outro", "expected_version": 1}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/produtos/{pid}", params={"expected_version": 1}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/produtos/{pid}/estoque",
                json={"delta": 1, "expected_version": 1},
            ).status_code,
            404,
        )
        self.assertEqual(self.client.post(endpoint, json=self.batch()).status_code, 200)
