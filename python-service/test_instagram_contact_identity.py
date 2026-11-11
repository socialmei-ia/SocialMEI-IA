import unittest
from instagram_contact_identity import contact_label


class ContactIdentityTests(unittest.TestCase):
    def test_official_username_preferred_and_neutral_fallback_is_consistent(self):
        self.assertEqual(contact_label({'username': 'fixture.user', 'name': 'Fixture'}, 'instagram:123'), '@fixture.user')
        self.assertEqual(contact_label({'name': 'Fixture'}, 'instagram:123'), 'Fixture')
        fallback = contact_label({}, 'instagram:123')
        self.assertTrue(fallback.startswith('Contato do Instagram · '))
        self.assertEqual(fallback, contact_label({}, 'instagram:123'))
        self.assertNotEqual(fallback, contact_label({}, 'instagram:456'))
        self.assertNotIn('123', fallback)
