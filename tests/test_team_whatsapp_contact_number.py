"""Synthetic identities only; a LID is never inferred to be a telephone."""
import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'tools/team-whatsapp-contact-number.py'


class ContactNumberTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('contact_number', PATH)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def binding(self):
        return {'id': 1, 'workspace_id': 1, 'channel_id': 9, 'channel_revision': 1,
                'instance': 'socialmei-equipe-piloto', 'session': '01',
                'account_id': '9915976@c.us', 'account_ref': 'waha:9915976@c.us',
                'contact_ref': 'waha:opaque-test@lid', 'contact_name': 'Contato do WhatsApp', 'revision': 2}

    def mapping(self):
        return {'session': {'name': '01', 'status': 'WORKING', 'me': {'id': '9915976@c.us'},
                            'engine': {'engine': 'WEBJS'}},
                'forward': {'lid': 'opaque-test@lid', 'pn': '5511990001234@c.us'},
                'reverse': {'lid': 'opaque-test@lid', 'pn': '5511990001234@c.us'}}

    def test_bidirectional_provider_mapping_is_required_and_returns_display_only_number(self):
        b = self.binding()
        self.assertEqual(self.module.verified_phone(b, self.mapping()), '+5511990001234')
        self.assertEqual(b, self.binding())

    def test_wrong_lid_session_account_engine_and_own_number_fail_closed(self):
        changes = [lambda x: x['forward'].update(lid='other@lid'),
                   lambda x: x['reverse'].update(lid='other@lid'),
                   lambda x: x['forward'].update(pn=None),
                   lambda x: x['session'].update(status='STOPPED'),
                   lambda x: x['session']['me'].update(id='other@c.us'),
                   lambda x: x['session']['engine'].update(engine='GOWS'),
                   lambda x: x['forward'].update(pn='9915976@c.us'),
                   lambda x: x['forward'].update(pn='12345678901234567890@c.us')]
        for change in changes:
            value = self.mapping(); change(value)
            with self.subTest(change=change), self.assertRaises(self.module.Blocked):
                self.module.verified_phone(self.binding(), value)

    def test_only_generic_label_is_replaced_and_replay_is_idempotent(self):
        b = self.binding()
        self.assertTrue(self.module.needs_update(b, '+5511990001234'))
        b['contact_name'] = '+5511990001234'
        self.assertFalse(self.module.needs_update(b, '+5511990001234'))
        b['contact_name'] = 'Human selected name'
        with self.assertRaises(self.module.Blocked): self.module.needs_update(b, '+5511990001234')

    def test_binding_is_restricted_to_existing_pilot_without_changing_account_or_contact(self):
        for key, value in [('workspace_id', 2), ('instance', 'other'), ('session', 'other'),
                           ('account_ref', 'waha:other@c.us'), ('contact_ref', 'waha:12345@c.us')]:
            b = self.binding(); b[key] = value
            with self.subTest(key=key), self.assertRaises(self.module.Blocked): self.module.validate_binding(b)
