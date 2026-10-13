import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import psycopg
from app import app
from fastapi.testclient import TestClient
from workspace_export import export_packet

DB = os.getenv("TEST_DATABASE_URL", "").strip()
STAMP = datetime.now(UTC).isoformat()
META = {"versao": 1, "criado_em": STAMP, "atualizado_em": STAMP}


def sample():
    return {
        "formato": "socialmei-workspace-transfer",
        "versao_formato": 1,
        "origem": str(uuid4()),
        "workspace_origem": "development",
        "exportado_em": STAMP,
        "clientes": [
            {**META, "id": 11, "nome": "Mesmo nome", "tags": []},
            {**META, "id": 12, "nome": "Mesmo nome", "tags": []},
        ],
        "produtos": [
            {
                **META,
                "id": 21,
                "nome": "Item",
                "tipo": "Produto",
                "preco": "10.25",
                "custo": "1.01",
                "estoque": 8,
                "minimo": 1,
                "status": "Ativo",
            }
        ],
        "vendas": [
            {
                **META,
                "id": 31,
                "cliente_id": 12,
                "produto_id": 21,
                "cliente": "Nome histórico",
                "item": "Item histórico",
                "tipo_item": "Produto",
                "data": "2026-10-11",
                "quantidade": 2,
                "preco": "10.25",
                "desconto": "0.00",
                "valor": "20.50",
                "pagamento": "Pix",
                "observacao": "",
                "status": "Pendente",
                "estoque_aplicado": True,
                "importada": False,
                "excluida": False,
            }
        ],
        "financeiro": [
            {
                **META,
                "id": 41,
                "cliente_id": 11,
                "descricao": "Entrada",
                "pessoa": "Snapshot",
                "tipo": "receita",
                "valor": "20.50",
                "vencimento": "2026-10-11",
                "status": "pago",
                "data_pagamento": None,
                "importada": True,
                "excluida": False,
            }
        ],
    }


class TransferValidationTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_invalid_snapshot_rejected_before_database(self):
        cases = []
        for change in [
            {"workspace_origem": "team"},
            {"versao_formato": True},
            {"versao_formato": 1.0},
            {"origem": "invalid"},
            {"clientes": []},
            {"unexpected": "never discard"},
        ]:
            cases.append({**sample(), **change})
        for area, changes in [
            ("clientes", {"id": True}),
            ("produtos", {"estoque": 1.5}),
            ("vendas", {"cliente_id": 999}),
            ("vendas", {"estoque_aplicado": True, "importada": True}),
            ("vendas", {"valor": "2.00"}),
            ("financeiro", {"cliente_id": 999}),
        ]:
            packet = sample()
            packet[area][0].update(changes)
            cases.append(packet)
        packet = sample()
        packet["clientes"].append(packet["clientes"][0])
        cases.append(packet)
        for packet in cases:
            response = self.client.post("/api/v1/transferencias/preview", json=packet)
            self.assertEqual(response.status_code, 422, response.text)


@unittest.skipUnless(DB, "TEST_DATABASE_URL não configurado")
class TransferIntegrationTests(unittest.TestCase):
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
        os.environ["DATABASE_URL"] = DB
        os.environ["SOCIALMEI_SHARED_DATA_ENABLED"] = "true"
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "team"
        with psycopg.connect(DB) as conn:
            conn.execute("TRUNCATE socialmei.workspaces RESTART IDENTITY CASCADE")
        self.existing = self.client.post(
            "/api/v1/clientes", json={"nome": "Mesmo nome"}
        ).json()
        self.packet = sample()

    def preview(self, packet=None):
        response = self.client.post(
            "/api/v1/transferencias/preview", json=packet or self.packet
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def confirm(self, packet=None, preview=None):
        packet = packet or self.packet
        return self.client.post(
            "/api/v1/transferencias/confirmar",
            json={
                "pacote": packet,
                "preview_token": (preview or self.preview(packet))["preview_token"],
            },
        )

    def test_new_transfer_invalid_catalog_is_rejected_without_writes(self):
        preview = self.preview()
        for field, value in [("preco", "12.345"), ("custo", "10000000000000")]:
            packet = deepcopy(self.packet)
            packet["produtos"][0][field] = value
            response = self.client.post("/api/v1/transferencias/preview", json=packet)
            self.assertEqual(response.status_code, 422, response.text)
            response = self.confirm(packet=packet, preview=preview)
            self.assertEqual(response.status_code, 422, response.text)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM socialmei.crm_produtos").fetchone()[
                    0
                ],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_transferencias"
                ).fetchone()[0],
                0,
            )

    def test_preexisting_transfer_receipt_remains_replayable_without_rounding(self):
        self.packet["produtos"][0]["preco"] = "12.345"
        self.packet["produtos"][0]["custo"] = "100000000000000000000"
        # Simula um recibo criado antes do contrato novo, somente no banco isolado de teste.
        with patch("workspace_transfer.validate_new_transfer_catalog"):
            first = self.confirm()
        self.assertEqual(first.status_code, 200, first.text)
        second = self.confirm()
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()["ja_transferido"])
        with psycopg.connect(DB) as conn:
            row = conn.execute(
                "SELECT preco, custo FROM socialmei.crm_produtos"
            ).fetchone()
            self.assertEqual(str(row[0]), "12.345")
            self.assertEqual(row[1], 10**20)
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_transferencias"
                ).fetchone()[0],
                1,
            )

    def test_atomic_handover_maps_ids_keeps_snapshots_and_stock_behavior(self):
        preview = self.preview()
        self.assertEqual(preview["destino_atual"]["clientes"], 1)
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)
        response = self.confirm(preview=preview)
        self.assertEqual(response.status_code, 200, response.text)
        ids = response.json()["mapa_ids"]
        sale = self.client.get(f"/api/v1/vendas/{ids['vendas']['31']}").json()
        product = self.client.get(f"/api/v1/produtos/{ids['produtos']['21']}").json()
        self.assertEqual(sale["cliente_id"], ids["clientes"]["12"])
        self.assertNotEqual(sale["cliente_id"], self.existing["id"])
        self.assertEqual(sale["cliente"], "Nome histórico")
        self.assertEqual(sale["item"], "Item histórico")
        self.assertTrue(sale["estoque_aplicado"])
        self.assertFalse(sale["importada"])
        self.assertEqual(product["estoque"], 8)
        entry = self.client.get(f"/api/v1/financeiro/{ids['financeiro']['41']}").json()
        self.assertEqual(entry["cliente_id"], ids["clientes"]["11"])
        self.assertEqual(entry["pessoa"], "Snapshot")
        self.assertIsNone(entry["data_pagamento"])
        action = {"operation_id": str(uuid4()), "expected_version": sale["versao"]}
        url = f"/api/v1/vendas/{sale['id']}/cancelar"
        cancel = self.client.post(url, json=action)
        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(self.client.post(url, json=action).json(), cancel.json())
        self.assertEqual(
            self.client.get(f"/api/v1/produtos/{product['id']}").json()["estoque"], 10
        )
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 3)

    def test_replay_concurrent_and_after_target_changes_never_duplicates(self):
        preview = self.preview()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(lambda _: self.confirm(preview=preview), range(2))
            )
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(sum(r.json()["ja_transferido"] for r in responses), 1)
        sale = self.client.get("/api/v1/vendas").json()[0]
        self.client.post(
            f"/api/v1/vendas/{sale['id']}/cancelar",
            json={"operation_id": str(uuid4()), "expected_version": sale["versao"]},
        )
        changed_time = {
            **self.packet,
            "exportado_em": "2026-10-12T10:00:00Z",
            "clientes": list(reversed(self.packet["clientes"])),
        }
        replay = self.confirm(packet=changed_time)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()["ja_transferido"])
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 3)
        self.assertEqual(self.client.get("/api/v1/produtos").json()[0]["estoque"], 10)
        self.assertEqual(
            self.client.get("/api/v1/vendas").json()[0]["status"], "Cancelado"
        )

    def test_changed_source_or_origin_conflicts_after_first_handover(self):
        self.assertEqual(self.confirm().status_code, 200)
        for kind in ["source", "origin"]:
            packet = deepcopy(self.packet)
            if kind == "source":
                packet["clientes"][0]["nome"] = "Changed"
            else:
                packet["origem"] = str(uuid4())
            self.assertEqual(
                self.client.post(
                    "/api/v1/transferencias/preview", json=packet
                ).status_code,
                409,
            )
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 3)

    def test_stale_preview_blocks_entire_handover(self):
        preview = self.preview()
        self.client.post("/api/v1/clientes", json={"nome": "New"})
        self.assertEqual(self.confirm(preview=preview).status_code, 409)
        self.assertEqual(self.client.get("/api/v1/produtos").json(), [])
        self.assertEqual(self.client.get("/api/v1/vendas").json(), [])
        self.assertEqual(self.client.get("/api/v1/financeiro").json(), [])
        self.assertEqual(self.confirm().status_code, 200)

    def test_database_error_rolls_back_every_module_and_receipt(self):
        preview = self.preview()
        with psycopg.connect(DB) as conn:
            conn.execute(
                "ALTER TABLE socialmei.crm_financeiro ADD CONSTRAINT ci_transfer_failure CHECK (descricao <> 'Entrada')"
            )
        try:
            with self.assertRaises(psycopg.errors.CheckViolation):
                self.confirm(preview=preview)
            self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)
            self.assertEqual(self.client.get("/api/v1/produtos").json(), [])
            with psycopg.connect(DB) as conn:
                self.assertEqual(
                    conn.execute(
                        "SELECT COUNT(*) FROM socialmei.crm_transferencias"
                    ).fetchone()[0],
                    0,
                )
        finally:
            with psycopg.connect(DB) as conn:
                conn.execute(
                    "ALTER TABLE socialmei.crm_financeiro DROP CONSTRAINT ci_transfer_failure"
                )

    def test_deleted_history_and_service_keep_their_original_state(self):
        self.packet["vendas"][0].update(
            status="Cancelado", estoque_aplicado=False, excluida=True
        )
        self.packet["financeiro"][0]["excluida"] = True
        self.packet["produtos"].append(
            {
                **META,
                "id": 22,
                "nome": "Serviço",
                "tipo": "Serviço",
                "preco": "4.00",
                "custo": "1.00",
                "estoque": None,
                "minimo": None,
                "status": "Ativo",
            }
        )
        self.packet["vendas"].append(
            {
                **self.packet["vendas"][0],
                "id": 32,
                "produto_id": 22,
                "tipo_item": "Serviço",
                "status": "Pendente",
                "excluida": False,
            }
        )
        response = self.confirm()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(self.client.get("/api/v1/vendas").json()), 1)
        self.assertEqual(self.client.get("/api/v1/financeiro").json(), [])
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_vendas WHERE excluida"
                ).fetchone()[0],
                1,
            )

    def test_export_uses_readonly_development_and_roundtrips_linked_records(self):
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "development"
        customer = self.client.post("/api/v1/clientes", json={"nome": "Fonte"}).json()
        product = self.client.post(
            "/api/v1/produtos",
            json={
                "nome": "Fonte",
                "preco": 10.25,
                "custo": 1.01,
                "estoque": 8,
                "minimo": 1,
            },
        ).json()
        sale = self.client.post(
            "/api/v1/vendas",
            json={
                "cliente_id": customer["id"],
                "produto_id": product["id"],
                "data": "2026-10-11",
                "quantidade": 2,
                "preco": "10.25",
                "operation_id": str(uuid4()),
            },
        ).json()
        origin = uuid4()
        packet = export_packet(origin)
        second = export_packet(origin)
        self.assertEqual(packet.vendas[0].id, sale["id"])
        self.assertEqual(packet.produtos[0].estoque, 6)
        self.assertEqual(packet.vendas[0].cliente_id, customer["id"])
        self.assertEqual(packet.produtos[0].preco, second.produtos[0].preco)
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "team"
        with self.assertRaises(RuntimeError):
            export_packet(origin)
        response = self.confirm(packet=packet.model_dump(mode="json", by_alias=True))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get("/api/v1/produtos").json()[0]["estoque"], 6)

    def test_disabled_in_development_workspace(self):
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "development"
        self.assertEqual(
            self.client.post(
                "/api/v1/transferencias/preview", json=self.packet
            ).status_code,
            503,
        )
