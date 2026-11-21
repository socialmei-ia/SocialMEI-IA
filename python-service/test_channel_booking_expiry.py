"""Expired textual booking choices must not become unrelated catalog commands."""
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

import channel_booking_flow as flow


class BookingExpiryTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.offer = {'channel_booking': True, 'booking_expires': 1,
                      'choices': [flow.option('1', 'Confirmar reserva', 'confirm')]}
        self.conn.execute.return_value.fetchone.return_value = {'result': self.offer}
        self.channel = {'workspace_id': 60, 'channel_id': 9, 'binding_hash': 'synthetic'}
        self.message = {'id': 42, 'conversation_id': 7, 'text': '1'}

    def test_expired_confirmation_shows_refresh_without_booking_or_catalog_fallback(self):
        with patch.object(flow, 'advance') as advance:
            state, result = flow.respond(self.conn, self.channel, self.message, {'state': 'menu'})
        self.assertEqual(state, 'menu')
        self.assertEqual(result['action'], 'booking_expired')
        self.assertEqual([choice['id'] for choice in result['choices']], ['6', '0', '5'])
        advance.assert_not_called()

    def test_fresh_choice_still_advances_and_refresh_command_starts_new_lookup(self):
        for text, expires in [('1', int(datetime.now(timezone.utc).timestamp()) + 600), ('6', 1)]:
            self.offer['booking_expires'] = expires
            with patch.object(flow, 'advance', return_value=('menu', {})) as advance:
                flow.respond(self.conn, self.channel, {**self.message, 'text': text}, {'state': 'menu'})
            advance.assert_called_once()

    def test_human_menu_and_unrelated_commands_preserve_existing_owner(self):
        for text, state in [('1', 'human'), ('0', 'menu'), ('5', 'menu'), ('produto', 'menu')]:
            with patch.object(flow, 'advance') as advance:
                self.assertIsNone(flow.respond(self.conn, self.channel,
                    {**self.message, 'text': text}, {'state': state}))
            advance.assert_not_called()


if __name__ == '__main__':
    unittest.main()
