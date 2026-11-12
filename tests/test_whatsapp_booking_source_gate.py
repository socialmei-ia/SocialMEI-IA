"""Fail-closed booking entry checks without importing or contacting the live menu API."""
import ast
from pathlib import Path
import unittest


SOURCE = (Path(__file__).resolve().parents[1] / 'tools' / 'whatsapp-public-continuous.py').read_text(encoding='utf-8')
TREE = ast.parse(SOURCE)
GATE = next(node for node in TREE.body
            if isinstance(node, ast.FunctionDef) and node.name == 'booking_command_allowed')
SCOPE = {}
exec(compile(ast.fix_missing_locations(ast.Module(body=[GATE], type_ignores=[])),
             '<booking_source_gate>', 'exec'), SCOPE)
allowed = SCOPE['booking_command_allowed']


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

    def test_policy_read_from_same_workspace_and_used_only_at_source_gate(self):
        self.assertIn("JOIN socialmei.workspaces w ON w.id=e.workspace_id", SOURCE)
        self.assertIn("w.configuracao #>> '{channel_booking,policy,enabled}' AS booking_enabled", SOURCE)
        self.assertIn("booking_command_allowed(row['text'], row['state'], row['booking_enabled'])", SOURCE)


if __name__ == '__main__':
    unittest.main()
