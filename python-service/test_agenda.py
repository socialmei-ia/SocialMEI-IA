"""Persistent reminders: real isolated PostgreSQL/accounts, no external providers."""

import os
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from pydantic import ValidationError

import agenda
import test_account_auth as accounts
from account_auth import COOKIE, csrf

PATH = "/api/v1/agenda"
RANGE = "?from_date=2026-10-01&to_date=2026-11-30"


def fields(**changes):
    return {
        "operation_id": str(uuid4()),
        "title": "Retornar ao cliente",
        "scheduled_for": "2026-10-31T09:00:00-03:00",
        "notes": "Confirmar o orçamento antes de responder.",
        **changes,
    }


class AgendaValidationTests(unittest.TestCase):
    def test_creation_requires_explicit_timezone_and_valid_text_and_scope(self):
        for change in (
            {"scheduled_for": "2026-10-31T09:00:00"},
            {"scheduled_for": "2026-02-30T09:00:00-03:00"},
            {"scheduled_for": 1793448000},
            {"scheduled_for": "9999-12-31T23:00:00-03:00"},
            {"title": " "}, {"title": "x" * 161}, {"title": "a\x00b"},
            {"notes": "x" * 1001}, {"title": "\ud800"}, {"notes": "\udfff"}, {"cliente_id": True},
            {"workspace_id": 2}, {"operation_id": "invalid"},
        ):
            with self.subTest(change=list(change)), self.assertRaises(ValidationError):
                agenda.ReminderCreate.model_validate(fields(**change))
        value = agenda.ReminderCreate.model_validate(fields())
        self.assertEqual(value.scheduled_for.utcoffset(), timedelta(hours=-3))

    def test_update_requires_a_real_revision_and_supported_status(self):
        for values in (
            {"expected_revision": True, "status": "done"},
            {"expected_revision": 0, "status": "pending"},
            {"expected_revision": 9007199254740992, "status": "pending"},
            {"expected_revision": 1, "status": "sent"},
            {"expected_revision": 1, "status": "done", "title": "Other"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                agenda.ReminderUpdate.model_validate(values)

    def test_missing_session_and_disabled_auth_never_open_agenda_database(self):
        with patch.dict(os.environ, accounts.ENV, clear=True), patch(
            "agenda.connect", side_effect=AssertionError("No database")
        ):
            client = TestClient(accounts.app, base_url=accounts.ORIGIN)
            self.assertEqual(client.get(PATH).status_code, 401)
            with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
                self.assertEqual(client.get(PATH).status_code, 503)

    def test_database_failure_is_sanitized_and_uncacheable(self):
        user = {"id": 1, "workspace_id": 1, "role": "owner", "administrador_plataforma": False}
        with patch.dict(os.environ, accounts.ENV, clear=True), patch(
            "account_auth.session_identity", return_value=user
        ), patch("agenda.connect", side_effect=psycopg.OperationalError("private-database-marker")):
            client = TestClient(accounts.app, base_url=accounts.ORIGIN)
            client.cookies.set(COOKIE, "a" * 64)
            response = client.get(PATH)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertNotIn("private-database-marker", response.text)

    def test_invalid_unicode_http_errors_do_not_echo_private_notes(self):
        user = {"id": 1, "workspace_id": 1, "role": "owner", "administrador_plataforma": False}
        with patch.dict(os.environ, accounts.ENV, clear=True), patch(
            "account_auth.session_identity", return_value=user
        ), patch("agenda.connect", side_effect=AssertionError("No database")):
            client = TestClient(accounts.app, base_url=accounts.ORIGIN)
            client.cookies.set(COOKIE, "a" * 64)
            for field in ("title", "notes"):
                response = client.post(PATH, content=json.dumps(fields(**{field: "\ud800-private-marker"})),
                    headers={**accounts.HEADERS, "Content-Type": "application/json", "X-SocialMEI-CSRF": csrf("a" * 64)})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn("private-marker", response.text)
                self.assertEqual(response.headers['cache-control'], 'no-store')


@unittest.skipUnless(accounts.DB, "Disposable PostgreSQL required")
class AgendaDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    setUp = accounts.AccountDatabaseTests.setUp
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register

    def create(self, client=None, **changes):
        client = client or self.admin_client
        payload = fields(**changes)
        response = client.post(PATH, json=payload)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json(), payload

    def test_create_persist_replay_conflict_and_two_businesses(self):
        first, payload = self.create()
        self.assertEqual(first["id"], payload["operation_id"])
        self.assertEqual(first["status"], "pending")
        self.assertEqual(first["revision"], 1)
        self.assertEqual(self.admin_client.post(PATH, json=payload).json(), first)
        same_instant = {**payload, "scheduled_for": "2026-10-31T12:00:00Z"}
        self.assertEqual(self.admin_client.post(PATH, json=same_instant).json(), first)
        changed = self.admin_client.post(PATH, json={**payload, "title": "Different"})
        self.assertEqual(changed.status_code, 409)
        fresh_session = self.login("admin@example.com")
        self.assertEqual(fresh_session.get(PATH + RANGE).json()["items"], [first])
        other = self.register("agenda-other@example.test")
        self.assertEqual(other.get(PATH + RANGE).json()["items"], [])
        theirs = other.post(PATH, json={**payload, "title": "Outro negócio"})
        self.assertEqual(theirs.status_code, 201, theirs.text)
        self.assertEqual(self.admin_client.get(PATH + RANGE).json()["items"], [first])
        self.assertEqual(len(other.get(PATH + RANGE).json()["items"]), 1)

    def test_status_updates_use_cas_and_foreign_ids_are_not_visible(self):
        row, _ = self.create()
        other = self.register("agenda-status-other@example.test")
        resource = PATH + "/" + row["id"]
        self.assertEqual(other.patch(resource, json={"expected_revision": 1, "status": "done"}).status_code, 404)
        first = self.admin_client.patch(resource, json={"expected_revision": 1, "status": "done"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["revision"], 2)
        self.assertEqual(first.json()["status"], "done")
        stale = self.admin_client.patch(resource, json={"expected_revision": 1, "status": "cancelled"})
        self.assertEqual(stale.status_code, 409)
        cancelled = self.admin_client.patch(resource, json={"expected_revision": 2, "status": "cancelled"})
        self.assertEqual(cancelled.json()["revision"], 3)
        self.assertEqual(self.admin_client.get(PATH + RANGE).json()["items"], [])
        reopened = self.admin_client.patch(resource, json={"expected_revision": 3, "status": "pending"})
        self.assertEqual(reopened.json()["revision"], 4)
        self.assertEqual(self.admin_client.get(PATH + RANGE).json()["items"][0]["status"], "pending")

    def test_viewer_reads_but_cannot_write_and_member_can_write(self):
        row, _ = self.create()
        uid = self.admin_client.identity["usuario"]["id"]
        wid = self.admin_client.identity["negocio"]["id"]
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='viewer' WHERE workspace_id=%s AND user_id=%s", (wid, uid))
        self.assertEqual(self.admin_client.get(PATH + RANGE).status_code, 200)
        self.assertEqual(self.admin_client.post(PATH, json=fields()).status_code, 403)
        self.assertEqual(self.admin_client.patch(PATH + "/" + row["id"], json={"expected_revision": 1, "status": "done"}).status_code, 403)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE workspace_id=%s AND user_id=%s", (wid, uid))
        self.create(title="Lembrete do colaborador")

    def test_foreign_client_is_rejected_and_client_deletion_preserves_reminder(self):
        other = self.register("agenda-client-other@example.test")
        own_client = self.admin_client.post("/api/v1/clientes", json={"nome": "Cliente da agenda"}).json()
        foreign_client = other.post("/api/v1/clientes", json={"nome": "Cliente de outro negócio"}).json()
        rejected = self.admin_client.post(PATH, json=fields(cliente_id=foreign_client["id"]))
        self.assertEqual(rejected.status_code, 422)
        row, payload = self.create(cliente_id=own_client["id"])
        listed = self.admin_client.get(PATH + RANGE).json()["items"][0]
        self.assertEqual(listed["client_name"], "Cliente da agenda")
        removed = self.admin_client.delete(f"/api/v1/clientes/{own_client['id']}?expected_version={own_client['versao']}")
        self.assertEqual(removed.status_code, 204, removed.text)
        preserved = self.admin_client.get(PATH + RANGE).json()["items"][0]
        self.assertEqual(preserved["id"], row["id"])
        self.assertIsNone(preserved["cliente_id"])
        self.assertEqual(self.admin_client.post(PATH, json=payload).json(), preserved)
        with self.assertRaises(psycopg.errors.ForeignKeyViolation), psycopg.connect(accounts.DB) as conn:
            conn.execute(
                "INSERT INTO socialmei.agenda_reminders(workspace_id,id,title,scheduled_for,cliente_id,creation_fingerprint) VALUES(%s,%s,'Invalid',NOW(),%s,%s)",
                (self.admin_client.identity["negocio"]["id"], uuid4(), foreign_client["id"], "a" * 64),
            )

    def test_period_uses_business_timezone_and_invalid_periods_fail(self):
        self.create(scheduled_for="2026-11-01T01:30:00Z")
        with patch.dict(os.environ, {"TZ": "America/Recife"}):
            selected = self.admin_client.get(PATH + "?from_date=2026-10-31&to_date=2026-10-31")
            following = self.admin_client.get(PATH + "?from_date=2026-11-01&to_date=2026-11-01")
        self.assertEqual(len(selected.json()["items"]), 1)
        self.assertEqual(following.json()["items"], [])
        for query in ("?from_date=2026-10-31&to_date=2026-10-01", "?from_date=2025-01-01&to_date=2026-12-01", "?from_date=invalid"):
            self.assertEqual(self.admin_client.get(PATH + query).status_code, 422)

    def test_concurrent_creation_commits_one_reminder(self):
        payload = fields()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.admin_client.post(PATH, json=payload), range(2)))
        self.assertEqual([response.status_code for response in results], [201, 201])
        self.assertEqual(results[0].json(), results[1].json())
        self.assertEqual(len(self.admin_client.get(PATH + RANGE).json()["items"]), 1)

    def test_limit_reports_truncation_without_cross_workspace_rows(self):
        workspace = self.admin_client.identity["negocio"]["id"]
        with psycopg.connect(accounts.DB) as conn:
            for index in range(501):
                conn.execute(
                    "INSERT INTO socialmei.agenda_reminders(workspace_id,id,title,scheduled_for,creation_fingerprint) VALUES(%s,%s,%s,%s,%s)",
                    (workspace, uuid4(), f"Lembrete {index}", datetime(2026, 10, 31, 12, tzinfo=timezone.utc), "a" * 64),
                )
        response = self.admin_client.get(PATH + RANGE)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["items"]), 500)
        self.assertTrue(response.json()["truncated"])


if __name__ == "__main__":
    unittest.main()
