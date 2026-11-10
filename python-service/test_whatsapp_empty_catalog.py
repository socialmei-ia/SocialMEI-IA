"""The WhatsApp bot must never invent catalog contents for an empty workspace."""

import unittest
from unittest.mock import MagicMock

from whatsapp_bot import answer


class EmptyCatalogReplyTests(unittest.TestCase):
    def test_empty_catalog_and_unknown_product_are_distinct(self):
        database = MagicMock()
        database.execute.return_value.fetchall.return_value = []

        for state, message, expected_action, phrase in (
            ("menu", "1", "products", "não há produtos ativos"),
            ("menu", "3", "services", "não há serviços ativos"),
            ("ask_product", "bolo de milho", "availability", "Não encontrei um produto com esse nome"),
        ):
            with self.subTest(state=state, message=message):
                next_state, reply = answer(database, 1, state, message)
                self.assertEqual(next_state, "menu")
                self.assertEqual(reply["action"], expected_action)
                self.assertEqual(reply["items"], [])
                self.assertIn(phrase, reply["text"])
                self.assertIn("atendente", reply["text"])
                self.assertNotIn("R$", reply["text"])
                self.assertNotIn("esgotado", reply["text"].lower())
                sql, args = database.execute.call_args.args
                self.assertIn("workspace_id=%s", sql)
                self.assertIn("status='Ativo'", sql)
                self.assertEqual(args[0], 1)

    def test_formatted_product_list_uses_registered_price_and_stock(self):
        database = MagicMock()
        database.execute.return_value.fetchall.return_value = [
            {"nome": "Produto demonstração", "tipo": "Produto", "preco": "10.00", "estoque": 5},
            {"nome": "Última unidade", "tipo": "Produto", "preco": "3.50", "estoque": 1},
            {"nome": "A confirmar", "tipo": "Produto", "preco": "20.00", "estoque": 0},
        ]
        state, reply = answer(database, 1, "menu", "1")
        self.assertEqual(state, "menu")
        self.assertEqual(reply["action"], "products")
        self.assertIn("Produto demonstração\nPreço: R$ 10,00\nDisponibilidade: 5 unidades", reply["text"])
        self.assertIn("Última unidade\nPreço: R$ 3,50\nDisponibilidade: 1 unidade", reply["text"])
        self.assertIn("A confirmar\nPreço: R$ 20,00\nDisponibilidade: a confirmar", reply["text"])
        self.assertNotIn("registrado(s)", reply["text"])
        self.assertNotIn("esgotado", reply["text"].lower())
        self.assertIn("digite 4", reply["text"])
        self.assertIn("digite 5", reply["text"])
        self.assertIn("digite 0", reply["text"])

    def test_product_name_search_keeps_the_menu_navigation(self):
        database = MagicMock()
        database.execute.return_value.fetchall.return_value = [
            {"nome": "Produto demonstração", "tipo": "Produto", "preco": "10.00", "estoque": 5},
        ]

        next_state, prompt = answer(database, 1, "menu", "2")
        self.assertEqual(next_state, "ask_product")
        self.assertEqual(prompt["action"], "ask_product")
        database.execute.assert_not_called()

        next_state, reply = answer(database, 1, "ask_product", "demonstração")
        self.assertEqual(next_state, "menu")
        self.assertEqual(reply["action"], "availability")
        self.assertIn("Preço: R$ 10,00", reply["text"])
        self.assertIn("Disponibilidade: 5 unidades", reply["text"])
        self.assertEqual(database.execute.call_args.args[1][-2:], ("demonstração", "demonstração"))

        next_state, back = answer(database, 1, "menu", "0")
        self.assertEqual(next_state, "menu")
        self.assertEqual(back["action"], "menu")

    def test_services_have_price_without_stock(self):
        database = MagicMock()
        database.execute.return_value.fetchall.return_value = [
            {"nome": "Serviço exemplo", "tipo": "Serviço", "preco": "50.00", "estoque": 0},
        ]
        state, reply = answer(database, 1, "menu", "3")
        self.assertEqual(state, "menu")
        self.assertEqual(reply["action"], "services")
        self.assertIn("Serviço exemplo\nPreço: R$ 50,00", reply["text"])
        self.assertNotIn("Disponibilidade:", reply["text"])
        self.assertIn("digite 4", reply["text"])

    def test_numbered_menu_zero_to_five_routes_without_sending(self):
        """All numbered paths are planning only, even during a GOWS pilot."""
        from whatsapp_bot import render_waha
        database = MagicMock()
        database.execute.return_value.fetchall.return_value = []

        scenarios = (
            ("0", "menu", "menu", False),
            ("1", "menu", "products", False),
            ("2", "ask_product", "ask_product", False),
            ("3", "menu", "services", False),
            ("4", "human", "quote_handoff", True),
            ("5", "human", "human_handoff", True),
        )
        for choice, expected_state, action, handoff in scenarios:
            with self.subTest(choice=choice):
                state, result = answer(database, 1, "menu", choice)
                self.assertEqual((state, result["action"], result["handoff"]),
                                 (expected_state, action, handoff))
                self.assertIsInstance(result["text"], str)
                self.assertNotIn("send", result)
                prepared = render_waha("default", "222@c.us", result["text"],
                                       result["choices"], engine="WEBJS",
                                       list_verified=True)
                self.assertEqual(prepared["path"], "/api/sendText")
                self.assertEqual(prepared["body"]["chatId"], "222@c.us")

        # After handoff only the owner can resume the automatic menu.
        _, silent = answer(database, 1, "human", "0")
        self.assertEqual(silent["action"], "human_wait")
        self.assertEqual(silent["text"], "")

    def test_unrecognized_menu_message_never_triggers_handoff(self):
        database = MagicMock()
        database.execute.return_value.fetchall.return_value = []
        state, result = answer(database, 1, "menu", "999")
        self.assertEqual(state, "menu")
        self.assertEqual(result["action"], "menu")
        self.assertFalse(result["handoff"])
        database.execute.assert_not_called()

    def test_menu_and_handoff_still_work_without_catalog(self):
        database = MagicMock()
        for state, message, expected in (
            ("menu", "0", "menu"),
            ("menu", "5", "human_handoff"),
            ("human", "1", "human_wait"),
        ):
            with self.subTest(state=state, message=message):
                _, reply = answer(database, 1, state, message)
                self.assertEqual(reply["action"], expected)
        database.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
