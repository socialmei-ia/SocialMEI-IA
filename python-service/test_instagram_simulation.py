"""Focused Instagram simulation contract/tenant tests, no external network."""
import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient

from account_auth import COOKIE, csrf
from app import app
from instagram_simulation import PublicationInput

ORIGIN = "https://app.example.com"
TOKEN = "a" * 64
ENV = {
    "SOCIALMEI_AUTH_ENABLED": "true",
    "SOCIALMEI_SHARED_DATA_ENABLED": "true",
    "SOCIALMEI_AUTH_ORIGIN": ORIGIN,
    "SOCIALMEI_INSTAGRAM_MODE": "simulation",
}
DB = os.getenv("TEST_DATABASE_URL", "").strip()
MEDIA = [{"name": "teste.png", "mime": "image/png", "size": 2048}]


class ContractTests(unittest.TestCase):
    def test_media_and_schedule_rejections(self):
        base = {
            "account_id": str(uuid4()), "idempotency_key": str(uuid4()),
            "format": "feed", "caption": "Teste", "media": MEDIA,
        }
        self.assertEqual(PublicationInput.model_validate(base).format, "feed")
        for change in [
            {"format": "reel"},
            {"format": "story", "media": MEDIA * 2},
            {"format": "feed", "media": [{"name": "inseguro.mp4", "mime": "video/mp4", "size": 2048}]},
            {"format": "feed", "media": [{"name": "a.png", "mime": "image/png", "size": 11 * 1024 * 1024}]},
            {"scheduled_for": datetime.now(timezone.utc) - timedelta(minutes=1)},
            {"scheduled_for": datetime.now().replace(tzinfo=None) + timedelta(hours=1)},
        ]:
            with self.subTest(change=str(change)), self.assertRaises(ValueError):
                PublicationInput.model_validate({**base, **change})

    def test_invalid_payload_never_echoes_caption_or_asset_metadata(self):
        marker = "confidencial-nao-exibir-123"
        with patch.dict(os.environ, ENV):
            client = TestClient(app, base_url=ORIGIN)
            client.cookies.set(COOKIE, TOKEN)
            with patch("account_auth.session_identity", return_value={
                "id": 1, "workspace_id": 1, "role": "owner",
                "administrador_plataforma": False,
            }):
                response = client.post(
                    "/api/v1/instagram/simulation/publications",
                    headers={"Origin": ORIGIN, "X-SocialMEI-CSRF": csrf(TOKEN)},
                    json={"caption": marker, "media": [{"name": marker}]},
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn(marker, response.text)
                self.assertEqual(response.json()["detail"], "Confira os campos informados.")

    def test_feature_flag_fails_closed_without_db(self):
        with patch.dict(os.environ, {**ENV, "SOCIALMEI_INSTAGRAM_MODE": "disabled"}):
            client = TestClient(app, base_url=ORIGIN)
            with patch("account_auth.session_identity", return_value={
                "id": 1, "workspace_id": 1, "role": "owner",
                "administrador_plataforma": False,
            }), patch("instagram_simulation.connect", side_effect=AssertionError("database accessed")):
                client.cookies.set(COOKIE, TOKEN)
                self.assertEqual(client.get("/api/v1/instagram/simulation/status").status_code, 503)


@unittest.skipUnless(DB, "Postgres test database not configured")
class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(DB, autocommit=True) as conn:
            for migration in sorted(
                (Path(__file__).resolve().parents[1] / "database/migrations").glob("*.sql")
            ):
                conn.execute(migration.read_text(), prepare=False)

    def setUp(self):
        self.env = patch.dict(os.environ, {**ENV, "DATABASE_URL": DB})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identities = []
        with psycopg.connect(DB) as conn:
            for index in (1, 2):
                uid = uuid4().hex
                workspace = conn.execute(
                    "INSERT INTO socialmei.workspaces(slug,nome) VALUES (%s,%s) RETURNING id",
                    ("ig-sim-" + uid, "Sandbox " + str(index)),
                ).fetchone()[0]
                user = conn.execute(
                    "INSERT INTO socialmei.users(email,nome) VALUES (%s,%s) RETURNING id",
                    (uid + "@example.test", "Sandbox User"),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) "
                    "VALUES (%s,%s,'owner')",
                    (workspace, user),
                )
                self.identities.append({
                    "id": user, "workspace_id": workspace,
                    "role": "owner", "administrador_plataforma": False,
                })
        self.identity = self.identities[0]
        self.mock_auth = patch("account_auth.session_identity", side_effect=lambda _: self.identity)
        self.mock_auth.start()
        self.addCleanup(self.mock_auth.stop)
        self.client = TestClient(app, base_url=ORIGIN)
        self.client.cookies.set(COOKIE, TOKEN)
        self.headers = {"Origin": ORIGIN, "X-SocialMEI-CSRF": csrf(TOKEN)}

    def tearDown(self):
        with psycopg.connect(DB) as conn:
            for user in self.identities:
                conn.execute("DELETE FROM socialmei.workspaces WHERE id=%s", (user["workspace_id"],))
                conn.execute("DELETE FROM socialmei.users WHERE id=%s", (user["id"],))

    def post(self, path, payload):
        return self.client.post(path, json=payload, headers=self.headers)

    def test_end_to_end_scopes_idempotency_and_no_publish(self):
        prefix = "/api/v1/instagram/simulation"
        self.assertEqual(self.client.get(prefix + "/status").json()["transport"], "none")
        self.assertEqual(self.post(prefix + "/accounts", {"label": "Loja de teste"}).status_code, 201)
        a = self.client.get(prefix + "/accounts").json()["items"][0]
        payload = {
            "account_id": a["id"], "idempotency_key": str(uuid4()),
            "format": "feed", "caption": "Legenda sem envio #teste", "media": MEDIA,
        }
        first = self.post(prefix + "/publications", payload)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(first.json()["status"], "simulated")
        self.assertFalse(first.json()["published"])
        second = self.post(prefix + "/publications", payload)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        wrong = self.post(prefix + "/publications", {**payload, "caption": "Texto modificado"})
        self.assertEqual(wrong.status_code, 409, wrong.text)
        self.assertEqual(len(self.client.get(prefix + "/publications").json()["items"]), 1)
        self.identity = self.identities[1]
        self.assertEqual(self.client.get(prefix + "/accounts").json()["items"], [])
        self.assertEqual(self.client.get(prefix + "/publications").json()["items"], [])
        self.assertEqual(self.client.get(prefix + "/publications/" + first.json()["id"]).status_code, 404)
        self.assertEqual(self.post(prefix + "/publications", payload).status_code, 404)

    def test_permissions_csrf_and_schedule(self):
        prefix = "/api/v1/instagram/simulation"
        self.assertEqual(
            self.client.post(prefix + "/accounts", json={"label": "bad-origin"}).status_code, 403
        )
        account = self.post(prefix + "/accounts", {"label": "Conta fictícia"}).json()["id"]
        self.identity = {**self.identities[0], "role": "viewer"}
        self.assertEqual(self.post(prefix + "/accounts", {"label": "No"}).status_code, 403)
        self.assertEqual(self.post(prefix + "/publications", {
            "account_id": account, "idempotency_key": str(uuid4()),
            "format": "story", "caption": "", "media": MEDIA,
        }).status_code, 403)
        self.identity = self.identities[0]
        when = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        response = self.post(prefix + "/publications", {
            "account_id": account, "idempotency_key": str(uuid4()),
            "format": "story", "caption": "", "media": MEDIA,
            "scheduled_for": when,
        })
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNotNone(response.json()["scheduled_for"])
        self.assertEqual(response.json()["status"], "simulated")
