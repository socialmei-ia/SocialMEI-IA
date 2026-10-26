"""WAHA-shaped fixtures and disposable PostgreSQL only; no provider I/O."""

import hashlib, hmac, json, unittest
from unittest.mock import patch
from fastapi import HTTPException
from waha_ingress import WahaBinding, WahaIngressService, parse_event

KEY = "isolated-waha-secret-never-production-123"


def payload(mid="false_222@c.us_mid", **updates):
    result = {
        "id": "evt_fixture",
        "timestamp": 1792890000000,
        "event": "message",
        "session": "default",
        "me": {"id": "111@c.us", "pushName": "not identity"},
        "engine": "WEBJS",
        "payload": {
            "id": mid,
            "timestamp": 1792890000,
            "from": "222@c.us",
            "to": "111@c.us",
            "fromMe": False,
            "hasMedia": False,
            "body": " Original\n",
        },
    }
    result.update(updates)
    return result


def raw(value):
    return json.dumps(value, ensure_ascii=False).encode()


def sign(body, key=KEY):
    return hmac.new(key.encode(), body, hashlib.sha512).hexdigest()


def binding(**patches):
    return WahaBinding(
        instance="trusted-a",
        session="default",
        account_id="111@c.us",
        workspace_id=1,
        channel_id=1,
        hmac_key=KEY,
        **patches
    )


class ContractTests(unittest.TestCase):
    def test_raw_hmac_before_parse_or_database_and_exact_owner_binding(self):
        service = WahaIngressService({"trusted-a": binding()})
        with patch(
            "waha_ingress.connect", side_effect=AssertionError("DB accessed")
        ) as database:
            for body, signature in (
                (b"{", "bad"),
                (raw(payload()), "0" * 128),
                (
                    b'{"session":"default","session":"other"}',
                    sign(b'{"session":"default","session":"other"}'),
                ),
            ):
                with self.assertRaises(HTTPException):
                    service.receive("trusted-a", body, signature, "sha512")
            for value in (
                payload(session="other"),
                payload(me={"id": "999@c.us"}),
                payload(me=None),
                payload(workspace_id=2),
            ):
                body = raw(value)
                with self.assertRaises(HTTPException):
                    service.receive("trusted-a", body, sign(body), "sha512")
            database.assert_not_called()
        body = raw(payload())
        event = parse_event(body, sign(body), "sha512", binding())
        self.assertEqual(event.text, " Original\n")
        self.assertEqual(event.contact_ref, "waha:222@c.us")
        changed = payload(
            event="message.any", timestamp=1792890000999, id="another-envelope"
        )
        self.assertEqual(
            parse_event(
                raw(changed), sign(raw(changed)), "sha512", binding()
            ).fingerprint,
            event.fingerprint,
        )

    def test_bounds_algorithms_immutable_registry_and_generic_representations(self):
        b = binding()
        service = WahaIngressService({"trusted-a": b})
        with self.assertRaises(TypeError):
            service.registry["other"] = b
        self.assertNotIn(KEY, repr(b))
        body = raw(payload())
        for algorithm in ("sha256", "SHA512", ""):
            with self.assertRaises(HTTPException):
                parse_event(body, sign(body), algorithm, b)
        values = []
        for field, value in (
            ("timestamp", True),
            ("timestamp", -1),
            ("body", "x" * 8193),
            ("body", "bad\x00text"),
            ("id", "x" * 1025),
            ("fromMe", "false"),
        ):
            candidate = payload()
            candidate["payload"][field] = value
            values.append(candidate)
        for candidate in values:
            with self.assertRaises(HTTPException):
                parse_event(raw(candidate), sign(raw(candidate)), "sha512", b)
        with self.assertRaises(HTTPException):
            parse_event(b"x" * 65537, "0" * 128, "sha512", b)
        lid = payload()
        lid["payload"]["from"] = "Opaque-123@lid"
        self.assertEqual(
            parse_event(raw(lid), sign(raw(lid)), "sha512", b).contact_ref,
            "waha:Opaque-123@lid",
        )
        for instance in ("fixture-forged", "bad/instance"):
            with self.assertRaises(ValueError):
                WahaBinding(
                    instance=instance,
                    session="default",
                    account_id="111@c.us",
                    workspace_id=1,
                    channel_id=1,
                    hmac_key=KEY,
                )

    def test_routes_closed_privacy_and_ambiguous_headers_before_database(self):
        import os
        from app import app
        from fastapi.testclient import TestClient
        from waha_ingress import waha_service
        from test_instagram_simulation import ENV

        flags = {
            **ENV,
            "SOCIALMEI_WAHA_INGRESS_MODE": "isolated",
            "SOCIALMEI_WAHA_LAB_ENVIRONMENT": "isolated",
        }
        with patch.dict(os.environ, flags), patch(
            "waha_ingress.connect", side_effect=AssertionError("DB accessed")
        ) as database:
            client = TestClient(app)
            response = client.post("/internal/waha/trusted-a/webhook", json={})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            app.dependency_overrides[waha_service] = lambda: WahaIngressService(
                {"trusted-a": binding()}
            )
            try:
                body = raw(payload())
                headers = [
                    ("content-type", "application/json"),
                    ("x-webhook-hmac", sign(body)),
                    ("x-webhook-hmac", sign(body)),
                    ("x-webhook-hmac-algorithm", "sha512"),
                ]
                self.assertEqual(
                    client.post(
                        "/internal/waha/trusted-a/webhook",
                        content=body,
                        headers=headers,
                    ).status_code,
                    403,
                )
                with patch.dict(os.environ, {"SOCIALMEI_AUTH_ENABLED": "false"}):
                    self.assertEqual(
                        client.post(
                            "/internal/waha/trusted-a/webhook",
                            content=body,
                            headers=headers,
                        ).status_code,
                        503,
                    )
                with patch.dict(os.environ, {"SOCIALMEI_SHARED_DATA_ENABLED": "false"}):
                    self.assertEqual(
                        client.post(
                            "/internal/waha/trusted-a/webhook",
                            content=body,
                            headers=headers,
                        ).status_code,
                        503,
                    )
                database.assert_not_called()
            finally:
                app.dependency_overrides.pop(waha_service, None)

    def test_receipt_retry_ignores_delivery_time_and_direct_requires_recipient(self):
        value = payload(event="message.ack")
        value["payload"]["ack"] = 3
        value["payload"].pop("timestamp")
        value["payload"].pop("to")
        first = parse_event(raw(value), sign(raw(value)), "sha512", binding())
        value["timestamp"] += 1000
        value["id"] = "another-delivery"
        second = parse_event(raw(value), sign(raw(value)), "sha512", binding())
        self.assertEqual(first.event_key, second.event_key)
        self.assertEqual(first.fingerprint, second.fingerprint)
        invalid = payload()
        invalid["payload"].pop("to")
        with self.assertRaises(HTTPException):
            parse_event(raw(invalid), sign(raw(invalid)), "sha512", binding())

    def test_signed_malformed_event_types_and_extreme_decimal_fail_before_database(
        self,
    ):
        service = WahaIngressService({"trusted-a": binding()})
        bodies = []
        for kind in ([], {}):
            bodies.append(raw(payload(event=kind)))
        for number in (
            b"1e99999999999999999999",
            b"1e-10000000",
            b"1e1000000",
            b"1.0000000000000000000000000000000000000000000000001",
            b"253402300799.999998999999999999999999999999999999999999999999999999999999",
        ):
            bodies.append(raw(payload()).replace(b"1792890000,", number + b","))
        bodies.append(raw(payload()).decode().encode("utf-16"))
        with patch(
            "waha_ingress.connect", side_effect=AssertionError("DB accessed")
        ) as database:
            for index, body in enumerate(bodies):
                with self.subTest(case=index):
                    with self.assertRaises(HTTPException) as error:
                        service.receive("trusted-a", body, sign(body), "sha512")
                    self.assertEqual(error.exception.status_code, 422)
            database.assert_not_called()

    def test_timestamp_exact_microseconds_do_not_depend_on_decimal_context(self):
        from decimal import Decimal, localcontext
        from waha_ingress import _time

        with localcontext() as context:
            context.prec = 2
            self.assertEqual(
                _time(Decimal("1.123456000000000000000000000000000000")).isoformat(),
                "1970-01-01T00:00:01.123456+00:00",
            )
            self.assertEqual(
                _time(1123, milliseconds=True).isoformat(),
                "1970-01-01T00:00:01.123000+00:00",
            )
            self.assertEqual(
                _time(Decimal("253402300799.999999")).isoformat(),
                "9999-12-31T23:59:59.999999+00:00",
            )
            for value in (
                "1e-10000000",
                "1e1000000",
                "1.0000000000000000000000000000000000001",
                "253402300799.9999989999999999999999999999999999999999",
            ):
                with self.subTest(value=value), self.assertRaises(HTTPException):
                    _time(Decimal(value))


import os, time, threading
from concurrent.futures import ThreadPoolExecutor
import psycopg
from fastapi.testclient import TestClient
from app import app
from account_auth import COOKIE
import test_instagram_simulation as fixtures
from waha_ingress import waha_service

DB = fixtures.DB
FLAGS = {
    "SOCIALMEI_WAHA_INGRESS_MODE": "isolated",
    "SOCIALMEI_WAHA_LAB_ENVIRONMENT": "isolated",
}


@unittest.skipUnless(DB, "Disposable PostgreSQL not configured")
class DatabaseTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.DatabaseTests.setUpClass.__func__)

    def setUp(self):
        fixtures.DatabaseTests.setUp(self)
        flags = patch.dict(os.environ, FLAGS)
        flags.start()
        self.addCleanup(flags.stop)
        self.bindings = []
        with psycopg.connect(DB) as conn:
            for index, user in enumerate(self.identities):
                instance = "trusted-" + str(user["workspace_id"])
                account = str(111 if index == 0 else 333) + "@c.us"
                key = KEY + str(index)
                channel = conn.execute(
                    "INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ingress_provisioned,ativo) VALUES(%s,%s,'default',%s,true,true) RETURNING id",
                    (user["workspace_id"], instance, account),
                ).fetchone()[0]
                self.bindings.append(
                    WahaBinding(
                        instance=instance,
                        session="default",
                        account_id=account,
                        workspace_id=user["workspace_id"],
                        channel_id=channel,
                        hmac_key=key,
                    )
                )
        self.service = WahaIngressService({b.instance: b for b in self.bindings})
        app.dependency_overrides[waha_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.pop, waha_service, None)

    def tearDown(self):
        with psycopg.connect(DB) as conn:
            for user in self.identities:
                conn.execute(
                    "DELETE FROM socialmei.crm_eventos_canal WHERE workspace_id=%s",
                    (user["workspace_id"],),
                )
                conn.execute(
                    "DELETE FROM socialmei.crm_canais WHERE workspace_id=%s",
                    (user["workspace_id"],),
                )
        fixtures.DatabaseTests.tearDown(self)

    def receive(self, value=None, b=None):
        b = b or self.bindings[0]
        value = value or payload()
        value = {**value, "session": b.session, "me": {"id": b.account_id}}
        if value["payload"].get("to") == "111@c.us":
            value["payload"]["to"] = b.account_id
        body = raw(value)
        return self.service.receive(b.instance, body, sign(body, b.hmac_key), "sha512")

    def test_durable_text_read_and_event_alias_dedup_without_legacy_body_copy(self):
        self.assertEqual(self.receive()["processed"], 1)
        self.assertEqual(
            self.receive(
                payload(
                    event="message.any",
                    id="different-delivery",
                    timestamp=1792890000999,
                )
            )["duplicates"],
            1,
        )
        items = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(items[0]["origin"], "waha")
        self.assertEqual(items[0]["messages"][0]["text"], " Original\n")
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_mensagens_canal WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.crm_eventos_canal WHERE workspace_id=%s AND dados_normalizados='{}'::jsonb",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                1,
            )

    def test_concurrent_duplicate_conflict_and_atomic_rollback(self):
        gate = threading.Barrier(2)

        def receive(_):
            gate.wait(5)
            return self.receive()

        with ThreadPoolExecutor(2) as pool:
            rows = list(pool.map(receive, range(2)))
        self.assertEqual(sorted(r["processed"] for r in rows), [0, 1])
        altered = payload()
        altered["payload"]["body"] = "changed"
        with self.assertRaises(HTTPException) as error:
            self.receive(altered)
        self.assertEqual(error.exception.status_code, 409)
        tables = (
            "me_conversations",
            "me_messages",
            "me_external_messages",
            "crm_eventos_canal",
        )

        def snapshot():
            with psycopg.connect(DB) as conn:
                counts = [
                    conn.execute(
                        "SELECT COUNT(*) FROM socialmei."
                        + table
                        + " WHERE workspace_id=%s",
                        (self.identity["workspace_id"],),
                    ).fetchone()[0]
                    for table in tables
                ]
                revisions = conn.execute(
                    "SELECT id,revision FROM socialmei.me_conversations WHERE workspace_id=%s ORDER BY id",
                    (self.identity["workspace_id"],),
                ).fetchall()
                return counts, revisions

        before = snapshot()
        from waha_ingress import _append_inbox_message as append

        def fail_after_writes(*args, **kwargs):
            append(*args, **kwargs)
            raise RuntimeError("fixture failure after real writes")

        with patch("waha_ingress._append_inbox_message", side_effect=fail_after_writes):
            with self.assertRaises(HTTPException) as error:
                self.receive(payload(mid="retry-mid"))
            self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(snapshot(), before)
        self.assertEqual(self.receive(payload(mid="retry-mid"))["processed"], 1)
        after = snapshot()
        self.assertEqual(
            after[0],
            [before[0][0], before[0][1] + 1, before[0][2] + 1, before[0][3] + 1],
        )

    def test_echo_receipt_media_and_groups_never_create_incoming(self):
        values = []
        for mid, patches in [
            ("echo", {"fromMe": True}),
            ("media", {"hasMedia": True}),
            ("group", {"from": "123@g.us", "participant": "222@c.us"}),
        ]:
            value = payload(mid)
            value["payload"].update(patches)
            values.append(value)
        receipt = payload("ack", event="message.ack")
        receipt["payload"]["ack"] = 3
        values.append(receipt)
        for value in values:
            self.assertEqual(self.receive(value)["ignored"], 1)
        with psycopg.connect(DB) as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM socialmei.me_messages WHERE workspace_id=%s",
                    (self.identity["workspace_id"],),
                ).fetchone()[0],
                0,
            )

    def test_contact_lid_and_tenant_are_isolated_and_no_owner_fixture_claim(self):
        self.receive()
        value = payload("lid")
        value["payload"]["from"] = "opaque-22@lid"
        self.receive(value)
        self.receive(payload("other-tenant"), self.bindings[1])
        rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {r["contact_ref"] for r in rows}, {"waha:222@c.us", "waha:opaque-22@lid"}
        )
        self.identity = self.identities[1]
        rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
            "items"
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["account_ref"], "waha:333@c.us")
        from channel_ingress import Channel

        with self.assertRaises(ValueError):
            Channel(instance=self.bindings[0].instance, session="default", name="claim")

    def test_disconnect_wins_before_channel_recheck(self):
        reached = threading.Event()
        proceed = threading.Event()
        original = self.service._channel

        def paused(*args):
            reached.set()
            if not proceed.wait(10):
                raise RuntimeError("fixture pause expired")
            return original(*args)

        with patch.object(
            self.service, "_channel", side_effect=paused
        ), ThreadPoolExecutor(1) as pool:
            future = pool.submit(self.receive)
            self.assertTrue(reached.wait(5))
            with psycopg.connect(DB) as conn:
                conn.execute(
                    "UPDATE socialmei.crm_canais SET ativo=false,versao=versao+1 WHERE id=%s",
                    (self.bindings[0].channel_id,),
                )
            proceed.set()
            with self.assertRaises(HTTPException) as error:
                future.result(10)
            self.assertEqual(error.exception.status_code, 404)

    def test_transfer_replay_never_copies_old_message_to_new_owner(self):
        self.receive()
        old = self.bindings[0]
        new_owner = self.identities[1]
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.crm_canais SET ativo=false WHERE id=%s",
                (old.channel_id,),
            )
            channel = conn.execute(
                "INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ingress_provisioned,ativo) VALUES(%s,'transfer-instance','transferred',%s,true,true) RETURNING id",
                (new_owner["workspace_id"], old.account_id),
            ).fetchone()[0]
        new = WahaBinding(
            instance="transfer-instance",
            session="transferred",
            account_id=old.account_id,
            workspace_id=new_owner["workspace_id"],
            channel_id=channel,
            hmac_key=KEY + "new",
        )
        self.service = WahaIngressService({new.instance: new})
        self.assertEqual(self.receive(b=new)["duplicates"], 1)
        self.identity = new_owner
        self.assertEqual(
            self.client.get("/api/v1/message-enrichment/conversations").json()["items"],
            [],
        )
        self.assertEqual(self.receive(payload("new-mid"), new)["processed"], 1)
        changed = payload()
        changed["payload"]["hasMedia"] = True
        with self.assertRaises(HTTPException) as error:
            self.receive(changed, new)
        self.assertEqual(error.exception.status_code, 409)

    def test_stale_binding_and_unprovisioned_channel_never_receive(self):
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.crm_canais SET versao=versao+1 WHERE id=%s",
                (self.bindings[0].channel_id,),
            )
        with self.assertRaises(HTTPException) as error:
            self.receive()
        self.assertEqual(error.exception.status_code, 404)
        with psycopg.connect(DB) as conn:
            conn.execute(
                "UPDATE socialmei.crm_canais SET versao=1,ingress_provisioned=false WHERE id=%s",
                (self.bindings[0].channel_id,),
            )
        with self.assertRaises(HTTPException) as error:
            self.receive()
        self.assertEqual(error.exception.status_code, 404)

    def test_global_active_account_and_historical_binding_fks(self):
        self.receive()
        b = self.bindings[0]
        with psycopg.connect(DB) as conn:
            with self.assertRaises(psycopg.errors.UniqueViolation):
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO socialmei.crm_canais(workspace_id,instancia,sessao,identificador_conta,ingress_provisioned,ativo) VALUES(%s,'duplicate-account','other',%s,true,true)",
                        (self.identities[1]["workspace_id"], b.account_id),
                    )
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute(
                        "UPDATE socialmei.crm_canais SET identificador_conta='999@c.us' WHERE id=%s",
                        (b.channel_id,),
                    )
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                with conn.transaction():
                    conn.execute(
                        "UPDATE socialmei.crm_eventos_canal SET canal_id=%s WHERE workspace_id=%s",
                        (self.bindings[1].channel_id, b.workspace_id),
                    )

    def test_provider_messages_cannot_use_synthetic_enrichment_or_public_input(self):
        self.receive()
        from message_enrichment import Incoming

        with self.assertRaises(ValueError):
            Incoming(
                schema_version=1,
                operation_id="00000000-0000-4000-8000-000000000001",
                channel="whatsapp",
                account_ref="waha:111@c.us",
                contact_ref="waha:222@c.us",
                contact_name="Contato",
                external_message_id="mid",
                text="body",
            )
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_MESSAGE_ENRICHMENT_MODE": "stub",
                "SOCIALMEI_MESSAGE_ENRICHMENT_TEST_KEY": "isolated-enrichment-secret-long-enough",
            },
        ):
            rows = self.client.get("/api/v1/message-enrichment/conversations").json()[
                "items"
            ]
            message = rows[0]["messages"][0]
            response = self.client.post(
                "/api/v1/message-enrichment/messages/" + str(message["id"]) + "/enrich",
                json={
                    "schema_version": 1,
                    "operation_id": "00000000-0000-4000-8000-000000000002",
                    "expected_revision": message["revision"],
                },
                headers=self.headers,
            )
            self.assertEqual(response.status_code, 409, response.text)

    def test_anonymous_webhook_accepts_signature_but_inbox_read_stays_authenticated(
        self,
    ):
        b = self.bindings[0]
        value = payload()
        body = raw(value)
        anonymous = TestClient(app)
        with patch("account_auth.session_identity", return_value=None):
            response = anonymous.post(
                "/internal/waha/" + b.instance + "/webhook",
                content=body,
                headers={
                    "content-type": "application/json",
                    "x-webhook-hmac": sign(body, b.hmac_key),
                    "x-webhook-hmac-algorithm": "sha512",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                anonymous.get("/api/v1/message-enrichment/conversations").status_code,
                401,
            )
