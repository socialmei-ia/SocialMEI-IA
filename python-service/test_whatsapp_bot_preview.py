"""The owner's WhatsApp bot preview reads true workspace catalog only; never sends."""
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi import HTTPException, Response

from whatsapp_bot import preview


class FakeCursor:
    def __init__(self, rows=()):
        self.rows = rows

    def fetchall(self):
        return self.rows


class FakeReadOnlyDatabase:
    def __init__(self, rows=()):
        self.rows = rows
        self.queries = []
        self.row_factory = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        if "SELECT nome,tipo,preco,estoque" in sql:
            return FakeCursor(self.rows)
        return FakeCursor()


class WhatsAppBotPreviewContracts(unittest.TestCase):
    def query(self, db, choice="0", product="", workspace=1):
        with patch("whatsapp_bot.require_owner", return_value={"workspace_id": workspace}), patch(
            "whatsapp_bot.connect", return_value=db
        ), patch("whatsapp_bot.enabled", side_effect=AssertionError("Bot enabled check must not run")):
            response = Response()
            data = preview(response, opcao=choice, produto=product)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIs(data["preview_only"], True)
        self.assertIs(data["send_enabled"], False)
        self.assertTrue(all(sql.lstrip().startswith(("SET", "SELECT")) for sql, _ in db.queries))
        if db.queries:
            self.assertEqual(db.queries[0][0], "SET TRANSACTION READ ONLY")
        return data

    def test_real_catalog_matches_text_bot_would_render_for_WEBJS(self):
        db = FakeReadOnlyDatabase([{
            "nome": "Bolo da loja", "tipo": "Produto",
            "preco": Decimal("18.50"), "estoque": 7,
        }])
        menu = self.query(db, "0")
        self.assertEqual(menu["action"], "menu")
        self.assertIn("1 - Ver produtos", menu["text"])
        self.assertIn("5 - Falar com atendente", menu["text"])
        self.assertEqual(menu["items"], [])

        db.queries.clear()
        listed = self.query(db, "1", workspace=41)
        self.assertEqual(listed["action"], "products")
        self.assertIn("Bolo da loja", listed["text"])
        self.assertIn("R$ 18,50", listed["text"])
        self.assertIn("estoque: 7", listed["text"])
        sql, params = db.queries[-1]
        self.assertIn("workspace_id=%s", sql)
        self.assertEqual(params[0], 41)
        self.assertEqual(params[1], "Produto")
        self.assertEqual(listed["items"][0]["disponibilidade"], "em_estoque")

    def test_product_lookup_and_empty_catalog_do_not_invent_price(self):
        empty = FakeReadOnlyDatabase()
        data = self.query(empty, "1")
        self.assertIn("Ainda não há produtos ativos", data["text"])
        self.assertNotIn("R$", data["text"])
        ask = self.query(empty, "2")
        self.assertEqual(ask["action"], "ask_product")
        self.assertIn("Qual produto", ask["text"])
        missing = self.query(empty, "2", product="bolo")
        self.assertEqual(missing["action"], "availability")
        self.assertIn("Não encontrei", missing["text"])
        self.assertNotIn("R$", missing["text"])
        self.assertEqual(missing["items"], [])

    def test_handoff_is_preview_only_and_does_not_write_conversations(self):
        db = FakeReadOnlyDatabase()
        for choice in ("4", "5"):
            reply = self.query(db, choice)
            self.assertTrue(reply["handoff"])
            self.assertEqual(reply["choices"], [])
            self.assertIn("atendente", reply["text"].lower())
        self.assertFalse(any("INSERT" in sql.upper() for sql, _ in db.queries))

    def test_invalid_query_and_non_owner_fail_before_database(self):
        with patch("whatsapp_bot.require_owner", return_value={"workspace_id": 1}), patch(
            "whatsapp_bot.connect", side_effect=AssertionError("Should not query DB")
        ):
            for choice, product in (("1", "bolo"), ("3", "qualquer"), ("2", "ab\x00cd")):
                with self.subTest(choice=choice):
                    with self.assertRaises(HTTPException) as err:
                        preview(Response(), opcao=choice, produto=product)
                    self.assertEqual(err.exception.status_code, 422)

        with patch("whatsapp_bot.require_owner", side_effect=HTTPException(403, "Somente dono")), patch(
            "whatsapp_bot.connect", side_effect=AssertionError("Should not query DB")
        ):
            with self.assertRaises(HTTPException) as error:
                preview(Response(), opcao="1", produto="")
        self.assertEqual(error.exception.status_code, 403)


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Disposable PostgreSQL required")
class WhatsAppBotPreviewDatabaseTests(unittest.TestCase):
    import test_account_auth as auth_fixtures

    setUpClass = classmethod(auth_fixtures.AccountDatabaseTests.setUpClass.__func__)
    setUp = auth_fixtures.AccountDatabaseTests.setUp
    register = auth_fixtures.AccountDatabaseTests.register

    def test_owner_sees_only_own_real_catalog_with_bot_disabled(self):
        import psycopg

        first = self.register("preview-owner-a@example.test")
        second = self.register("preview-owner-b@example.test")
        first_id = first.identity["negocio"]["id"]
        second_id = second.identity["negocio"]["id"]
        with patch.dict(os.environ, {"SOCIALMEI_WHATSAPP_BOT_ENABLED": "false"}):
            for client, name, stock in (
                (first, "Bolo do negócio A", 7),
                (second, "Bolo do negócio B", 99),
            ):
                saved = client.post("/api/v1/produtos", json={
                    "nome": name, "tipo": "Produto", "preco": 18.5,
                    "estoque": stock, "minimo": 0,
                })
                self.assertEqual(saved.status_code, 201, saved.text)
            first_result = first.get("/api/v1/whatsapp/bot/preview?opcao=1")
            second_result = second.get("/api/v1/whatsapp/bot/preview?opcao=1")
            self.assertEqual(first_result.status_code, 200, first_result.text)
            self.assertEqual(second_result.status_code, 200, second_result.text)
            self.assertIn("Bolo do negócio A", first_result.json()["text"])
            self.assertNotIn("Bolo do negócio B", first_result.text)
            self.assertIn("Bolo do negócio B", second_result.json()["text"])
            self.assertNotIn("Bolo do negócio A", second_result.text)
            self.assertEqual(first_result.json()["send_enabled"], False)
            self.assertEqual(first_result.headers["cache-control"], "no-store")
            self.assertEqual(first.get("/api/v1/whatsapp/bot/preview?opcao=1&produto=Bolo").status_code, 422)
            self.assertEqual(first.get("/api/v1/whatsapp/bot/preview?opcao=2&produto=Bolo").json()["action"], "availability")
            with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as conn:
                bot_records = conn.execute(
                    "SELECT COUNT(*) FROM socialmei.wa_bot_decisions WHERE workspace_id IN (%s,%s)",
                    (first_id, second_id),
                ).fetchone()[0]
                self.assertEqual(bot_records, 0)
                conn.execute(
                    "UPDATE socialmei.workspace_members SET role='viewer' "
                    "WHERE workspace_id=%s AND user_id=%s",
                    (first_id, first.identity["usuario"]["id"]),
                )
            self.assertEqual(first.get("/api/v1/whatsapp/bot/preview?opcao=1").status_code, 403)


if __name__ == "__main__":
    unittest.main()
