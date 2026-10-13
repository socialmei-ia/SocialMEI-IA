import json
import os
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import psycopg
from app import app
from catalog_data import ProdutoCreate, ProdutoOut, ProdutoUpdate
from fastapi.testclient import TestClient
from product_import import ImportItem, snapshot_and_hash
from pydantic import ValidationError
from sales_data import VendaCreate

DB = os.getenv("TEST_DATABASE_URL", "").strip()


class CatalogMoneyValidationTests(unittest.TestCase):
    def test_accepted_catalog_prices_are_accepted_as_unit_sale_prices(self):
        for value in [0, "0.01", "12.34", "12.340", "9999999999999.99"]:
            with self.subTest(value=value):
                product = ProdutoCreate(
                    nome="QA", tipo="Serviço", preco=value, custo=value
                )
                sale = VendaCreate(
                    cliente_id=1,
                    produto_id=1,
                    data="2026-10-13",
                    quantidade=1,
                    preco=product.preco,
                    operation_id=UUID(int=1),
                )
                self.assertEqual(Decimal(str(product.preco)), sale.preco)
                self.assertIsInstance(
                    json.loads(product.model_dump_json())["preco"], (int, float)
                )

    def test_extra_precision_and_magnitude_rejected_before_float_conversion(self):
        for value in [
            "12.345",
            "12.3400000000000000001",
            "10000000000000",
            "1e20",
            -1,
            True,
            "NaN",
            "Infinity",
            "-Infinity",
        ]:
            for field in ["preco", "custo"]:
                with self.subTest(value=value, field=field):
                    with self.assertRaises(ValidationError):
                        ProdutoCreate.model_validate(
                            {"nome": "QA", "preco": 1, field: value}
                        )
                    with self.assertRaises(ValidationError):
                        ProdutoUpdate.model_validate(
                            {"expected_version": 1, field: value}
                        )

    def test_patch_omission_zero_and_null_are_distinct(self):
        self.assertEqual(
            ProdutoUpdate(expected_version=1, nome="Editado").model_dump(
                exclude_unset=True
            ),
            {"expected_version": 1, "nome": "Editado"},
        )
        self.assertEqual(ProdutoUpdate(expected_version=1, custo=0).custo, 0)
        with self.assertRaises(ValidationError):
            ProdutoUpdate(expected_version=1, preco=None)

    def test_legacy_output_keeps_original_values_and_numeric_json(self):
        stamp = datetime.now(UTC)
        product = ProdutoOut(
            id=1,
            versao=1,
            nome="Antigo",
            preco=12.345,
            custo=1e20,
            criado_em=stamp,
            atualizado_em=stamp,
        )
        result = json.loads(product.model_dump_json())
        self.assertEqual(result["preco"], 12.345)
        self.assertEqual(result["custo"], 1e20)

    def test_valid_import_retains_historical_fingerprint(self):
        item = ImportItem(
            local_id=1,
            produto={
                "nome": "Fixture",
                "tipo": "Serviço",
                "preco": "12.340",
                "custo": "7.20",
            },
        )
        snapshot, fingerprint = snapshot_and_hash(item)
        self.assertEqual(snapshot["produto"]["preco"], 12.34)
        self.assertEqual(
            fingerprint,
            "611deae7f9c4947dee5b09ac0210c052f88309d808ae12ff8a76ed4aa6bd79bc",
        )

    def test_invalid_import_and_patch_return_422_without_database(self):
        client = TestClient(app)
        for field in ["preco", "custo"]:
            product = {"nome": "QA", "preco": 1, field: 12.345}
            self.assertEqual(
                client.post("/api/v1/produtos", json=product).status_code, 422
            )
            self.assertEqual(
                client.patch(
                    "/api/v1/produtos/1", json={"expected_version": 1, field: 12.345}
                ).status_code,
                422,
            )
            for operation in ["preview", "confirmar"]:
                response = client.post(
                    "/api/v1/produtos/importacoes/" + operation,
                    json={
                        "origem": str(UUID(int=1)),
                        "itens": [{"local_id": 1, "produto": product}],
                    },
                )
                self.assertEqual(response.status_code, 422)

    def test_valid_unit_price_still_respects_total_limit(self):
        with self.assertRaises(ValidationError):
            VendaCreate(
                cliente_id=1,
                produto_id=1,
                data="2026-10-13",
                quantidade=2,
                preco="9999999999999.99",
                operation_id=UUID(int=1),
            )


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class CatalogMoneyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB, autocommit=True) as conn:
            for migration in sorted(
                (Path(__file__).resolve().parents[1] / "database/migrations").glob(
                    "*.sql"
                )
            ):
                conn.execute(migration.read_text(), prepare=False)
        cls.client = TestClient(app)

    def setUp(self):
        os.environ["DATABASE_URL"] = DB
        os.environ["SOCIALMEI_SHARED_DATA_ENABLED"] = "true"
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-catalog-money"
        with psycopg.connect(DB) as conn:
            conn.execute("TRUNCATE socialmei.workspaces RESTART IDENTITY CASCADE")

    def create(self, **values):
        response = self.client.post(
            "/api/v1/produtos",
            json={
                "nome": "QA",
                "tipo": "Serviço",
                "preco": "12.34",
                "custo": "0.01",
                **values,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_numeric_roundtrip_and_unit_sale_at_money_boundaries(self):
        customer = self.client.post("/api/v1/clientes", json={"nome": "QA"}).json()
        for index, value in enumerate(
            ["0", "0.01", "12.340", "9999999999999.99"], start=1
        ):
            product = self.create(preco=value, custo=value)
            with psycopg.connect(DB) as conn:
                row = conn.execute(
                    "SELECT preco, custo FROM socialmei.crm_produtos WHERE id = %s",
                    (product["id"],),
                ).fetchone()
            self.assertEqual(row, (Decimal(value), Decimal(value)))
            response = self.client.post(
                "/api/v1/vendas",
                json={
                    "cliente_id": customer["id"],
                    "produto_id": product["id"],
                    "data": "2026-10-13",
                    "quantidade": 1,
                    "preco": product["preco"],
                    "operation_id": str(UUID(int=index)),
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(Decimal(str(response.json()["valor"])), Decimal(value))

    def test_old_values_remain_readable_and_untouched_by_partial_edit(self):
        product = self.create()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.crm_produtos SET preco = 12.345, custo = 1e20 WHERE id = %s",
                (product["id"],),
            )
        url = "/api/v1/produtos/" + str(product["id"])
        self.assertEqual(self.client.get(url).json()["preco"], 12.345)
        response = self.client.patch(
            url, json={"nome": "Nome editado", "expected_version": 1}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            (response.json()["preco"], response.json()["custo"]), (12.345, 1e20)
        )
        for field in ["preco", "custo"]:
            response = self.client.patch(
                url, json={field: 12.345, "expected_version": 2}
            )
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(url).json()["versao"], 2)

    def test_import_replay_keeps_one_product_and_receipt(self):
        payload = {
            "origem": str(UUID(int=1)),
            "itens": [
                {
                    "local_id": 1,
                    "produto": {
                        "nome": "Fixture",
                        "tipo": "Serviço",
                        "preco": "12.340",
                        "custo": "7.20",
                    },
                }
            ],
        }
        url = "/api/v1/produtos/importacoes/confirmar"
        first = self.client.post(url, json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        second = self.client.post(url, json=payload)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(
            second.json()["itens"][0]["produto_id"],
            first.json()["itens"][0]["produto_id"],
        )
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM socialmei.crm_produtos").fetchone()[
                    0
                ],
                1,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT fingerprint FROM socialmei.crm_produto_importacoes"
                ).fetchone()[0],
                "611deae7f9c4947dee5b09ac0210c052f88309d808ae12ff8a76ed4aa6bd79bc",
            )
