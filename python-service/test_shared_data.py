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
                """
                TRUNCATE socialmei.crm_clientes,
                         socialmei.workspace_members,
                         socialmei.users,
                         socialmei.workspaces
                RESTART IDENTITY CASCADE
                """
            )

        from app import app

        cls.client = TestClient(app)

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
