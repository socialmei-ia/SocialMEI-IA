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

    def test_text_commands_work_in_both_transports_and_preserve_human_pause(self):
        from whatsapp_bot import _catalog_answer
        from channel_booking_flow import respond
        import instagram_booking_flow
        for native in (False, True):
            for command in ('encerrar', 'sair', 'finalizar', 'voltar', 'menu', 'atendente', 'humano'):
                conn = MagicMock()
                state, result = _catalog_answer(conn, 7, 'ask_product', command, None, native)
                self.assertEqual(state, 'human' if command in {'atendente', 'humano'} else 'menu')
                self.assertNotEqual(result['action'], 'ask_product')
                conn.execute.assert_not_called()
                state, result = _catalog_answer(conn, 7, 'human', command, None, native)
                self.assertEqual((state, result['action'], result['text']), ('human', 'human_wait', ''))
                conn.execute.assert_not_called()
                message = {'text': command}
                self.assertIsNone(respond(conn, {}, message, {'state': 'menu'}))
                self.assertIsNone(instagram_booking_flow.respond(conn, 7, message))
                conn.execute.assert_not_called()

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
