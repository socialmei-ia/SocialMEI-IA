import os
import unittest
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL não configurado")
class SharedDataIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        os.environ["SOCIALMEI_SHARED_DATA_ENABLED"] = "true"
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-shared-data"
        os.environ["SOCIALMEI_WORKSPACE_NAME"] = "CI Shared Data"

        migrations = Path(__file__).resolve().parents[1] / "database" / "migrations"
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            for migration in sorted(migrations.glob("*.sql")):
                conn.execute(migration.read_text(encoding="utf-8"), prepare=False)
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS socialmei.schema_migrations "
                    "(version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"
                )
                conn.execute(
                    "INSERT INTO socialmei.schema_migrations (version) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (migration.name,)
                )
                if migration.name.startswith("002_"):
                    workspace_id = conn.execute(
                        "INSERT INTO socialmei.workspaces (slug, nome) "
                        "VALUES ('ci-upgrade-contract', 'Upgrade') "
                        "ON CONFLICT (slug) DO UPDATE SET nome = EXCLUDED.nome RETURNING id"
                    ).fetchone()[0]
                    upgrade_id = conn.execute(
                        "INSERT INTO socialmei.crm_clientes (workspace_id, nome, tags) "
                        "VALUES (%s, 'Cliente anterior à migration 003', '[\"Recorrente\"]'::jsonb) RETURNING id",
                        (workspace_id,),
                    ).fetchone()[0]

            cls.upgraded_row = conn.execute(
                "SELECT nome, tags, versao, cidade, total FROM socialmei.crm_clientes WHERE id = %s",
                (upgrade_id,),
            ).fetchone()

            conn.execute(
                """
                TRUNCATE socialmei.crm_cliente_importacoes, socialmei.crm_clientes,
                         socialmei.workspace_members,
                         socialmei.users,
                         socialmei.workspaces
                RESTART IDENTITY CASCADE
                """
            )

        from app import app

        cls.client = TestClient(app)

    def setUp(self):
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-shared-data"
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            conn.execute(
                "TRUNCATE socialmei.crm_cliente_importacoes, socialmei.crm_clientes, socialmei.workspaces RESTART IDENTITY CASCADE"
            )

    def create(self, **fields):
        response = self.client.post(
            "/api/v1/clientes", json={"nome": "Cliente de teste", **fields}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_migration_preserves_preexisting_client(self):
        self.assertEqual(
            self.upgraded_row,
            ("Cliente anterior à migration 003", ["Recorrente"], 1, None, None),
        )

    def test_complete_profile_round_trips_and_partial_updates_preserve_it(self):
        original = {
            "cidade": "Belo Jardim",
            "desde": "Cliente desde 2024",
            "categoria": "Recorrente",
            "criadoEm": "2024-05-01T12:00:00Z",
            "observacaoAtualizada": "2026-10-11T15:00:00Z",
            "avatarUrl": "https://example.com/avatar.jpg",
            "foto": "https://example.com/foto.jpg",
            "ultima": "Hoje",
            "total": 1840.25,
            "pendente": 220.5,
        }
        created = self.create(**original)
        for key, value in original.items():
            self.assertEqual(created[key], value)
        updated = self.client.patch(
            f"/api/v1/clientes/{created['id']}",
            json={"nome": "Nome atualizado", "expected_version": created["versao"]},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["versao"], 2)
        listed = self.client.get("/api/v1/clientes").json()[0]
        for key, value in original.items():
            self.assertEqual(listed[key], value)

    def test_stale_edit_delete_and_empty_patch_do_not_overwrite(self):
        created = self.create()
        url = f"/api/v1/clientes/{created['id']}"
        updated = self.client.patch(
            url, json={"nome": "Sessão B", "expected_version": 1}
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["versao"], 2)
        for payload in [
            {"nome": "Sessão A", "expected_version": 1},
            {"expected_version": 1},
        ]:
            self.assertEqual(self.client.patch(url, json=payload).status_code, 409)
        self.assertEqual(
            self.client.delete(url, params={"expected_version": 1}).status_code, 409
        )
        empty = self.client.patch(url, json={"expected_version": 2})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["versao"], 2)
        self.assertEqual(empty.json()["nome"], "Sessão B")
        self.assertEqual(
            self.client.delete(url, params={"expected_version": 2}).status_code, 204
        )

    def test_nullable_contact_can_be_cleared_without_losing_other_fields(self):
        created = self.create(telefone="(81) 99999-0000", cidade="Belo Jardim")
        url = f"/api/v1/clientes/{created['id']}"
        response = self.client.patch(url, json={"telefone": None})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["telefone"])
        self.assertEqual(response.json()["cidade"], "Belo Jardim")

    def test_legacy_id_collision_returns_conflict_without_overwriting(self):
        created = self.create(legacy_local_id=42)
        duplicate = self.client.post(
            "/api/v1/clientes", json={"nome": "Outro PC", "legacy_local_id": 42}
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(
            self.client.get(f"/api/v1/clientes/{created['id']}").json()["nome"],
            "Cliente de teste",
        )
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)

    def test_workspace_isolation_applies_to_reads_edits_and_deletes(self):
        created = self.create(legacy_local_id=42)
        url = f"/api/v1/clientes/{created['id']}"
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-other-workspace"
        try:
            self.assertEqual(self.client.get("/api/v1/clientes").json(), [])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(
                self.client.patch(url, json={"nome": "Outro"}).status_code, 404
            )
            self.assertEqual(self.client.delete(url).status_code, 404)
            self.create(legacy_local_id=42)
        finally:
            os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-shared-data"
        self.assertEqual(self.client.get(url).json()["nome"], "Cliente de teste")

    def import_payload(
        self, origem="11111111-1111-4111-8111-111111111111", nome="Maria"
    ):
        return {
            "origem": origem,
            "itens": [
                {
                    "local_id": 42,
                    "cliente": {"nome": nome, "cidade": "Belo Jardim"},
                    "extras": {"campoLegado": "preservado"},
                }
            ],
        }

    def import_clients(self, payload, action="confirmar"):
        return self.client.post(f"/api/v1/clientes/importacoes/{action}", json=payload)

    def test_import_preview_is_read_only_and_retry_preserves_remote_edits(self):
        payload = self.import_payload()
        preview = self.import_clients(payload, "preview")
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertTrue(preview.json()["pode_importar"])
        self.assertEqual(preview.json()["itens"][0]["acao"], "criar")
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            self.assertEqual(
                conn.execute("SELECT count(*) FROM socialmei.workspaces").fetchone()[0],
                0,
            )
        first = self.import_clients(payload)
        self.assertEqual(first.status_code, 200, first.text)
        client_id = first.json()["itens"][0]["cliente_id"]
        self.client.patch(
            f"/api/v1/clientes/{client_id}", json={"nome": "Editado remotamente"}
        )
        retry = self.import_clients(payload)
        self.assertEqual(retry.status_code, 200, retry.text)
        self.assertEqual(
            retry.json()["itens"][0],
            {"local_id": 42, "cliente_id": client_id, "acao": "existente"},
        )
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)
        self.assertEqual(
            self.client.get(f"/api/v1/clientes/{client_id}").json()["nome"],
            "Editado remotamente",
        )
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            snapshot = conn.execute(
                "SELECT snapshot FROM socialmei.crm_cliente_importacoes"
            ).fetchone()[0]
        self.assertEqual(snapshot["extras"], {"campoLegado": "preservado"})

    def test_import_conflicts_are_atomic_and_deleted_clients_are_not_recreated(self):
        payload = self.import_payload()
        first = self.import_clients(payload)
        client_id = first.json()["itens"][0]["cliente_id"]
        changed = self.import_payload(nome="Outra Maria")
        changed["itens"].insert(0, {"local_id": 99, "cliente": {"nome": "Novo"}})
        preview = self.import_clients(changed, "preview")
        self.assertFalse(preview.json()["pode_importar"])
        self.assertEqual(self.import_clients(changed).status_code, 409)
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)
        self.client.delete(f"/api/v1/clientes/{client_id}")
        deleted = self.import_clients(payload)
        self.assertEqual(deleted.status_code, 409, deleted.text)
        self.assertEqual(deleted.json()["detail"]["itens"][0]["acao"], "excluido")
        self.assertEqual(self.client.get("/api/v1/clientes").json(), [])

    def test_import_origin_and_workspace_separate_equal_local_ids(self):
        old = self.create(legacy_local_id=42)
        first = self.import_clients(self.import_payload()).json()["itens"][0][
            "cliente_id"
        ]
        second_response = self.import_clients(
            self.import_payload(
                origem="22222222-2222-4222-8222-222222222222", nome="Outro PC"
            )
        )
        self.assertEqual(second_response.status_code, 200, second_response.text)
        second = second_response.json()["itens"][0]["cliente_id"]
        self.assertEqual(len({old["id"], first, second}), 3)
        os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-import-other"
        try:
            other = self.import_clients(self.import_payload())
            self.assertEqual(other.status_code, 200, other.text)
            self.assertNotEqual(other.json()["itens"][0]["cliente_id"], first)
            self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)
        finally:
            os.environ["SOCIALMEI_WORKSPACE_SLUG"] = "ci-shared-data"

    def test_concurrent_imports_produce_one_mapping(self):
        from concurrent.futures import ThreadPoolExecutor

        payload = self.import_payload()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.import_clients(payload), range(2)))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        self.assertEqual(
            responses[0].json()["itens"][0]["cliente_id"],
            responses[1].json()["itens"][0]["cliente_id"],
        )
        self.assertEqual(len(self.client.get("/api/v1/clientes").json()), 1)

    def test_database_health(self):
        response = self.client.get("/health/db")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "healthy",
                "shared_data": True,
                "workspace": "ci-shared-data",
            },
        )

    def test_client_crud_is_shared_in_postgres(self):
        created = self.client.post(
            "/api/v1/clientes",
            json={
                "nome": "Maria Silva",
                "telefone": "(81) 99999-0000",
                "instagram": "@maria",
                "status": "Ativo",
                "observacao": "Cliente de teste",
                "tags": ["Recorrente"],
                "legacy_local_id": 42,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        client_id = created.json()["id"]

        listed = self.client.get("/api/v1/clientes")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["nome"], "Maria Silva")
        self.assertEqual(listed.json()[0]["legacy_local_id"], 42)

        fetched = self.client.get(f"/api/v1/clientes/{client_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["tags"], ["Recorrente"])

        updated = self.client.patch(
            f"/api/v1/clientes/{client_id}",
            json={"nome": "Maria Silva Atualizada", "tags": ["VIP", "Recorrente"]},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["nome"], "Maria Silva Atualizada")
        self.assertEqual(updated.json()["tags"], ["VIP", "Recorrente"])

        deleted = self.client.delete(f"/api/v1/clientes/{client_id}")
        self.assertEqual(deleted.status_code, 204)

        missing = self.client.get(f"/api/v1/clientes/{client_id}")
        self.assertEqual(missing.status_code, 404)

    def test_shared_routes_can_be_disabled(self):
        previous = os.environ.get("SOCIALMEI_SHARED_DATA_ENABLED")
        os.environ["SOCIALMEI_SHARED_DATA_ENABLED"] = "false"
        try:
            response = self.client.get("/api/v1/clientes")
            self.assertEqual(response.status_code, 503)
        finally:
            if previous is None:
                os.environ.pop("SOCIALMEI_SHARED_DATA_ENABLED", None)
            else:
                os.environ["SOCIALMEI_SHARED_DATA_ENABLED"] = previous


if __name__ == "__main__":
    unittest.main()
