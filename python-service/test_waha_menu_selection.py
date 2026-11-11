import unittest

from test_waha_ingress import binding, payload, raw, sign
from waha_ingress import parse_event


class MenuSelectionTests(unittest.TestCase):
    def event(self, kind, **fields):
        value = payload()
        value['payload'].update(type=kind, body='Titulo exibido', **fields)
        body = raw(value)
        return parse_event(body, sign(body), 'sha512', binding())

    def test_button_and_list_use_action_id_instead_of_display_text(self):
        button = self.event('buttons_response', selectedButtonId='5')
        row = self.event('list_response', _data={'listResponse': {'singleSelectReply': {'selectedRowId': '2'}}})
        self.assertEqual((button.kind, button.text), ('message', '5'))
        self.assertEqual((row.kind, row.text), ('message', '2'))
        self.assertEqual(button.contact_ref, 'waha:222@c.us')

    def test_missing_unknown_or_conflicting_selection_stays_unsupported(self):
        for values in ({}, {'selectedRowId': 'foreign-action'}, {'selectedRowId': True},
                       {'selectedRowId': '2', '_data': {'selectedButtonId': '5'}}):
            with self.subTest(values=values):
                event = self.event('list_response', **values)
                self.assertEqual((event.kind, event.text), ('unsupported', None))

    def test_media_and_echo_do_not_become_menu_commands(self):
        self.assertEqual(self.event('buttons_response', selectedButtonId='1', hasMedia=True).kind, 'unsupported')
        self.assertEqual(self.event('buttons_response', selectedButtonId='1', fromMe=True).kind, 'echo')
        for kind in ({}, [], None):
            self.assertEqual(self.event(kind, selectedButtonId='1').kind, 'unsupported')

    def test_same_choice_is_stable_and_different_choice_changes_fingerprint(self):
        self.assertEqual(self.event('buttons_response', selectedButtonId='1').fingerprint,
                         self.event('buttons_response', _data={'selectedButtonId': '1'}).fingerprint)
        self.assertNotEqual(self.event('buttons_response', selectedButtonId='1').fingerprint,
                            self.event('buttons_response', selectedButtonId='5').fingerprint)
