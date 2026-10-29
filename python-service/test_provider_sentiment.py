"""Tests for the opt-in provider analysis bridge without a real provider or database."""
import hashlib
import json
import os
from contextlib import contextmanager
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import provider_sentiment as module


class Cursor:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, *, message=None, claim=None):
        self.message = message
        self.claim = claim
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if "SELECT m.workspace_id" in sql:
            return Cursor(rows=[self.message] if self.message else [])
        if "INSERT INTO socialmei.me_provider_sentiment_jobs" in sql:
            return Cursor(row={"claim_id": params[2], "attempt": 1})
        if "SELECT * FROM socialmei.me_provider_sentiment_jobs" in sql:
            return Cursor(row=self.claim)
        if "UPDATE socialmei.me_provider_sentiment_jobs" in sql:
            self.claim.update({
                "status": "completed",
                "result_fingerprint": params[3],
            })
        return Cursor()


class ProviderSentimentTests(TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(module.router)
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.key = "test-key-" + "x" * 48
        self.environment = patch.dict(
            os.environ, {
                "SOCIALMEI_SHARED_DATA_ENABLED": "true",
                "SOCIALMEI_AUTH_ENABLED": "true",
                "SOCIALMEI_PROVIDER_SENTIMENT_ENABLED": "true",
                "SOCIALMEI_PROVIDER_SENTIMENT_KEY": self.key,
                "SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS": "3",
            }
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def auth(self):
        return {"Authorization": "Bearer " + self.key}

    def test_requires_opt_in_and_does_not_use_normal_n8n_api_key(self):
        with patch.dict(os.environ, {"SOCIALMEI_PROVIDER_SENTIMENT_ENABLED": "false"}):
            response = self.client.get("/internal/message-enrichment/provider/claims", headers=self.auth())
            self.assertEqual(response.status_code, 503)
        response = self.client.get(
            "/internal/message-enrichment/provider/claims",
            headers={"Authorization": "Bearer " + "z" * 48}
        )
        self.assertEqual(response.status_code, 401)

    def test_claim_only_trusted_service_and_never_sends(self):
        fake = FakeConnection(message={
            "workspace_id": 3, "id": 17, "origin": "instagram", "text": "Olá, há um problema"
        })

        @contextmanager
        def database():
            yield fake

        with patch.object(module, "database", database):
            response = self.client.get(
                "/internal/message-enrichment/provider/claims", headers=self.auth()
            )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertFalse(result["send_enabled"])
        self.assertEqual(result["items"][0]["message_id"], 17)
        self.assertEqual(result["items"][0]["origin"], "instagram")
        self.assertNotIn("workspace_id", result["items"][0])
        self.assertTrue(any("m.origin IN ('instagram','waha')" in sql for sql, _ in fake.queries))
        self.assertFalse(any("http" in sql.lower() for sql, _ in fake.queries))
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    def test_result_is_idempotent_and_rejects_changed_replay(self):
        claim_id = "11111111-2222-4333-8444-555555555555"
        fake = FakeConnection(claim={
            "workspace_id": 3, "message_id": 17, "claim_id": claim_id,
            "status": "processing", "result_fingerprint": None,
        })

        @contextmanager
        def database():
            yield fake

        original = {
            "claim_id": claim_id, "sentiment": "negative",
            "confidence": "medium", "explanation": "Cliente relatou problema."
        }
        with patch.object(module, "database", database):
            first = self.client.post(
                "/internal/message-enrichment/provider/results",
                headers=self.auth(), json=original
            )
            replay = self.client.post(
                "/internal/message-enrichment/provider/results",
                headers=self.auth(), json=original
            )
            different = self.client.post(
                "/internal/message-enrichment/provider/results",
                headers=self.auth(),
                json={**original, "sentiment": "positive"}
            )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["replayed"])
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])
        self.assertEqual(different.status_code, 409)
        self.assertEqual(
            sum("UPDATE socialmei.me_provider_sentiment_jobs" in sql for sql, _ in fake.queries),
            1
        )

    def test_invalid_result_is_rejected_before_database(self):
        claim_id = "11111111-2222-4333-8444-555555555555"
        with patch.object(module, "database", side_effect=AssertionError("DB should not open")):
            response = self.client.post(
                "/internal/message-enrichment/provider/results",
                headers=self.auth(),
                json={
                    "claim_id": claim_id,
                    "sentiment": "extremely_bad",
                    "confidence": "high",
                    "explanation": "Texto",
                }
            )
        self.assertEqual(response.status_code, 422)

    def test_hash_ignores_field_order(self):
        first = {"sentiment": "neutral", "confidence": "low", "explanation": "Sem contexto"}
        second = {"explanation": "Sem contexto", "confidence": "low", "sentiment": "neutral"}
        self.assertEqual(module.fingerprint(first), module.fingerprint(second))
        self.assertNotEqual(module.fingerprint(first), module.fingerprint({
            **first, "sentiment": "positive"
        }))
