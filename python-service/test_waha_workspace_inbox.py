"""Opt-in multibusiness receiving; fictional accounts and disposable PostgreSQL."""

import os
import stat
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psycopg
from fastapi import HTTPException

import settings
import test_waha_ingress as fixtures
import whatsapp_bot
from waha_ingress import WahaIngressService, waha_service
from whatsapp_human_outbox import reply_service

FLAGS = {
    "SOCIALMEI_AUTH_ENABLED": "true",
    "SOCIALMEI_SHARED_DATA_ENABLED": "true",
    "SOCIALMEI_WAHA_INGRESS_MODE": "workspace-inbox",
    "SOCIALMEI_WAHA_WORKSPACE_INBOX_ENABLED": "true",
    "SOCIALMEI_WAHA_REGISTRY_FILE": "/run/socialmei/private/waha-registry.json",
}
INBOX = "/api/v1/message-enrichment/conversations"


class WorkspaceInboxGuards(unittest.TestCase):
    def test_explicit_mode_and_opt_in_private_path_auth_and_shared_data_required(self):
        with patch.dict(os.environ, FLAGS):
            self.assertTrue(settings.waha_ingress_workspace_enabled())
            self.assertTrue(settings.waha_ingress_enabled())
            self.assertFalse(settings.waha_ingress_isolated_enabled())
            self.assertFalse(settings.waha_ingress_team_pilot_enabled())
            self.assertTrue(settings.waha_inbox_enabled(2))
            self.assertTrue(settings.waha_inbox_enabled(3))
            for invalid in (True, 0, -1, "2", 2**63):
                self.assertFalse(settings.waha_inbox_enabled(invalid))
            for field, value in (
                ("SOCIALMEI_AUTH_ENABLED", "false"),
                ("SOCIALMEI_SHARED_DATA_ENABLED", "false"),
                ("SOCIALMEI_WAHA_INGRESS_MODE", "enabled"),
                ("SOCIALMEI_WAHA_WORKSPACE_INBOX_ENABLED", "false"),
                ("SOCIALMEI_WAHA_REGISTRY_FILE", "/tmp/public.json"),
            ):
                with self.subTest(field=field), patch.dict(os.environ, {field: value}):
                    self.assertFalse(settings.waha_ingress_workspace_enabled())
                    self.assertFalse(settings.waha_ingress_enabled())

    def test_sender_and_bot_stay_closed_even_with_stale_enable_flags(self):
        with patch.dict(os.environ, {
            **FLAGS,
            "SOCIALMEI_WHATSAPP_BOT_ENABLED": "true",
            "SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED": "true",
        }):
            self.assertFalse(whatsapp_bot.enabled())
            with self.assertRaises(HTTPException) as error:
                whatsapp_bot.require_bot()
            self.assertEqual(error.exception.status_code, 503)
            self.assertIsNone(settings.whatsapp_human_configuration())
            self.assertFalse(reply_service().send_enabled)

    def test_registry_requires_root_owner_and_does_not_reveal_private_material(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "registry.json"
            path.write_text('{"version":1,"bindings":[]}', encoding="utf-8")
            path.chmod(0o600)
            metadata = SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600, st_uid=123, st_size=path.stat().st_size
            )
            with patch.dict(os.environ, {**FLAGS, "SOCIALMEI_WAHA_REGISTRY_FILE": str(path)}), patch(
                "waha_ingress.os.geteuid", return_value=123
            ), patch("waha_ingress.os.fstat", return_value=metadata):
                with self.assertRaises(HTTPException) as error:
                    waha_service()
                self.assertEqual(error.exception.status_code, 503)
                self.assertNotIn(str(path), error.exception.detail)

    def test_duplicate_accounts_channels_or_keys_never_form_a_registry(self):
        first = fixtures.binding()
        second = replace(first, instance="trusted-b", channel_id=2, workspace_id=2,
                         account_id="333@c.us", hmac_key=fixtures.KEY + "-second")
        for conflicting in (
            replace(second, account_id=first.account_id),
            replace(second, channel_id=first.channel_id),
            replace(second, hmac_key=first.hmac_key),
        ):
            with self.assertRaises(ValueError):
                WahaIngressService({first.instance: first, conflicting.instance: conflicting})


@unittest.skipUnless(fixtures.DB, "Disposable PostgreSQL not configured")
class WorkspaceInboxDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.DatabaseTests.setUpClass.__func__)
    tearDown = fixtures.DatabaseTests.tearDown
    receive = fixtures.DatabaseTests.receive

    def setUp(self):
        fixtures.DatabaseTests.setUp(self)
        flags = patch.dict(os.environ, FLAGS)
        flags.start()
        self.addCleanup(flags.stop)

    def items(self, index):
        self.identity = self.identities[index]
        response = self.client.get(INBOX)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["items"]

    def test_two_registered_accounts_same_mid_persist_and_read_in_own_workspace(self):
        for item in self.bindings:
            self.assertEqual(self.receive(fixtures.payload("same-provider-mid"), item)["processed"], 1)
            alias = fixtures.payload("same-provider-mid", event="message.any", id="other-envelope")
            self.assertEqual(self.receive(alias, item)["duplicates"], 1)
        for index, item in enumerate(self.bindings):
            rows = self.items(index)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["origin"], "waha")
            self.assertEqual(rows[0]["account_ref"], "waha:" + item.account_id)
            self.assertEqual(len(rows[0]["messages"]), 1)
            self.assertEqual(rows[0]["messages"][0]["text"], " Original\n")

    def test_tampered_signature_payload_scope_and_registry_scope_cannot_write(self):
        first, second = self.bindings
        event = fixtures.payload(me={"id": first.account_id}, session=first.session)
        event["payload"]["to"] = first.account_id
        body = fixtures.raw(event)
        with self.assertRaises(HTTPException) as error:
            self.service.receive(first.instance, body, fixtures.sign(body, second.hmac_key), "sha512")
        self.assertEqual(error.exception.status_code, 403)
        forged = {**event, "workspace_id": second.workspace_id}
        with self.assertRaises(HTTPException) as error:
            self.receive(forged, first)
        self.assertEqual(error.exception.status_code, 422)
        bad_binding = replace(first, workspace_id=second.workspace_id)
        service = WahaIngressService({first.instance: bad_binding})
        with self.assertRaises(HTTPException) as error:
            service.receive(first.instance, body, fixtures.sign(body, first.hmac_key), "sha512")
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.items(0), [])
        self.assertEqual(self.items(1), [])

    def test_http_reception_authenticates_raw_bytes_before_persistence(self):
        item = self.bindings[0]
        event = fixtures.payload(me={"id": item.account_id}, session=item.session)
        event["payload"]["to"] = item.account_id
        body = fixtures.raw(event)
        path = "/internal/waha/" + item.instance + "/webhook"
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Hmac": fixtures.sign(body, item.hmac_key),
            "X-Webhook-Hmac-Algorithm": "sha512",
        }
        wrong = self.client.post(path, content=body + b" ", headers=headers)
        self.assertEqual(wrong.status_code, 403)
        self.assertEqual(self.items(0), [])
        received = self.client.post(path, content=body, headers=headers)
        self.assertEqual(received.status_code, 200, received.text)
        self.assertEqual(received.json()["processed"], 1)
        self.assertEqual(len(self.items(0)), 1)
        self.assertEqual(self.items(1), [])

    def test_db_binding_revision_send_flag_and_account_uniqueness_are_enforced(self):
        first, second = self.bindings
        with psycopg.connect(fixtures.DB) as conn:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                with conn.transaction():
                    conn.execute("UPDATE socialmei.crm_canais SET identificador_conta=%s WHERE id=%s", (first.account_id, second.channel_id))
            conn.execute("UPDATE socialmei.crm_canais SET versao=versao+1 WHERE id=%s", (first.channel_id,))
        with self.assertRaises(HTTPException) as error:
            self.receive(b=first)
        self.assertEqual(error.exception.status_code, 404)
        with psycopg.connect(fixtures.DB) as conn:
            conn.execute("UPDATE socialmei.crm_canais SET envio_habilitado=true WHERE id=%s", (second.channel_id,))
        with self.assertRaises(HTTPException) as error:
            self.receive(b=second)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(self.items(0), [])
        self.assertEqual(self.items(1), [])
