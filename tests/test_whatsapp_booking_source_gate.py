"""Fail-closed booking entry checks without importing or contacting the live menu API."""
import ast
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'tools' / 'whatsapp-public-continuous.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
GATE = next(node for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == 'booking_command_allowed')
FOLLOWUP = next(node for node in TREE.body
                if isinstance(node, ast.FunctionDef) and node.name == 'booking_followup_allowed')
SCOPE = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[GATE, FOLLOWUP], type_ignores=[])),
             '<booking_source_gate>', 'exec'), SCOPE)
allowed = SCOPE['booking_command_allowed']
followup_allowed = SCOPE['booking_followup_allowed']


class BookingSourceGateTests(unittest.TestCase):
    def test_only_explicit_entries_with_enabled_workspace_are_allowed(self):
        for text in ('6', 'agendar', 'Agendar', 'AGENDAR', 'agendar horário',
                     'Agendar Horario', ' agendar '):
            with self.subTest(text=text):
                self.assertTrue(allowed(text, 'menu', 'true'))
                self.assertTrue(allowed(text, None, 'true'))

    def test_disabled_or_human_conversation_fails_closed(self):
        for enabled in ('false', None, False, True, '', 'TRUE'):
            self.assertFalse(allowed('6', 'menu', enabled))
        for state in ('human',):
            self.assertFalse(allowed('agendar', state, 'true'))

    def test_arbitrary_or_malformed_inputs_are_not_booking_commands(self):
        for text in ('1', '0', '5', 'agendar agora', 'agendar!','sm:deadbeef:1', '', None, 6, [], {}):
            with self.subTest(text=text):
                self.assertFalse(allowed(text, 'menu', 'true'))

    def test_booking_pagination_accepts_only_last_confirmed_offered_choices(self):
        choices = [
            {'id': '7', 'title': 'Horários anteriores',
             'target': {'route': 'booking', 'step': 'slots'}},
            {'id': '1', 'title': 'Confirmar',
             'target': {'route': 'booking', 'step': 'confirm'}},
            {'id': '5', 'title': 'Falar com atendente',
             'target': {'route': 'human'}},
        ]
        now = 1800000000
        self.assertTrue(followup_allowed('7', 'menu', 'true', choices, str(now + 300), now))
        self.assertTrue(followup_allowed('1', 'menu', 'true', choices, str(now + 300), now))
        for value in ('0', '5', '6', '99', 'arbitrario', None, True, 7, {}):
            with self.subTest(value=value):
                self.assertFalse(followup_allowed(value, 'menu', 'true',
                                                 choices, str(now + 300), now))
        for state, enabled, expiration in [
            ('human', 'true', str(now + 300)),
            ('menu', 'false', str(now + 300)),
            ('menu', None, str(now + 300)),
            ('menu', 'true', str(now - 1)),
            ('menu', 'true', str(now + 601)),
            ('menu', 'true', 'not-a-time'),
        ]:
            self.assertFalse(followup_allowed('7', state, enabled, choices,
                                             expiration, now))
        self.assertFalse(followup_allowed('7', 'menu', 'true',
                                         [{'id': '7', 'target': {'route': 'main'}}],
                                         str(now + 300), now))
        self.assertFalse(followup_allowed('7', 'menu', 'true', None,
                                         str(now + 300), now))

    def test_booking_followups_are_loaded_from_matching_workspace_and_channel(self):
        self.assertIn("LEFT JOIN LATERAL (", SOURCE)
        self.assertIn("q.workspace_id=e.workspace_id AND q.channel_id=e.canal_id", SOURCE)
        self.assertIn("q.conversation_id=v.id AND q.status='confirmed'", SOURCE)
        self.assertIn("q.result->>'channel_booking'='true'", SOURCE)
        self.assertIn("booking_followup_allowed(row['text'], row['state'], row['booking_enabled']", SOURCE)

    def test_policy_read_from_same_workspace_and_used_only_at_source_gate(self):
        self.assertIn("JOIN socialmei.workspaces w ON w.id=e.workspace_id", SOURCE)
        self.assertIn("w.configuracao #>> '{channel_booking,policy,enabled}' AS booking_enabled", SOURCE)
        self.assertIn("booking_command_allowed(row['text'], row['state'], row['booking_enabled'])", SOURCE)


if __name__ == '__main__':
    unittest.main()
