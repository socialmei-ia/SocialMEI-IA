"""Session management uses real sessions and disposable tenant data."""

import unittest
import test_account_auth as accounts
from fastapi.testclient import TestClient
from app import app


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class SessionTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def test_list_revocation_and_tenant_isolation(self):
        owner = self.register("session-owner@example.test")
        second = self.login("session-owner@example.test")
        other = self.register("session-other@example.test")
        response = owner.get("/api/v1/auth/sessions")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        rows = response.json()["sessions"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["current"] for row in rows), 1)
        for row in rows:
            self.assertEqual(set(row), {"id", "created_at", "expires_at", "current"})
        foreign = other.get("/api/v1/auth/sessions").json()["sessions"][0]["id"]
        self.assertEqual(
            owner.post(f"/api/v1/auth/sessions/{foreign}/revoke", json={}).status_code,
            404,
        )
        target = next(row["id"] for row in rows if not row["current"])
        self.assertEqual(
            owner.post(f"/api/v1/auth/sessions/{target}/revoke", json={}).status_code,
            204,
        )
        self.assertIsNone(second.get("/api/v1/auth/session").json())
        self.assertIsNotNone(other.get("/api/v1/auth/session").json())
        self.assertIsNotNone(owner.get("/api/v1/auth/session").json())

    def test_revoke_others_requires_password_and_keeps_current(self):
        owner = self.register("session-owner@example.test")
        second = self.login("session-owner@example.test")
        self.assertEqual(
            owner.post(
                "/api/v1/auth/sessions/revoke-others", json={"atual": "wrong"}
            ).status_code,
            400,
        )
        self.assertIsNotNone(second.get("/api/v1/auth/session").json())
        self.assertEqual(
            owner.post(
                "/api/v1/auth/sessions/revoke-others", json={"atual": accounts.PASSWORD}
            ).status_code,
            204,
        )
        self.assertIsNone(second.get("/api/v1/auth/session").json())
        self.assertIsNotNone(owner.get("/api/v1/auth/session").json())

    def test_current_revocation_and_anonymous_csrf_guards(self):
        owner = self.register("session-owner@example.test")
        current = next(
            row["id"]
            for row in owner.get("/api/v1/auth/sessions").json()["sessions"]
            if row["current"]
        )
        anonymous = TestClient(app, base_url=accounts.ORIGIN, headers=accounts.HEADERS)
        self.assertEqual(anonymous.get("/api/v1/auth/sessions").status_code, 401)
        token = owner.headers.pop("X-SocialMEI-CSRF")
        self.assertEqual(
            owner.post(f"/api/v1/auth/sessions/{current}/revoke", json={}).status_code,
            403,
        )
        owner.headers["X-SocialMEI-CSRF"] = token
        response = owner.post(f"/api/v1/auth/sessions/{current}/revoke", json={})
        self.assertEqual(response.status_code, 204)
        self.assertIn("Max-Age=0", response.headers["set-cookie"])
        self.assertIsNone(owner.get("/api/v1/auth/session").json())
