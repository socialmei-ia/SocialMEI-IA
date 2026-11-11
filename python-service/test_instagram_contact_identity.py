import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID
from instagram_contact_identity import contact_label, refresh_contacts


class ContactIdentityTests(unittest.TestCase):
    def test_official_username_preferred_and_neutral_fallback_is_consistent(self):
        self.assertEqual(contact_label({'username': 'fixture.user', 'name': 'Fixture'}, 'instagram:123'), '@fixture.user')
        self.assertEqual(contact_label({'name': 'Fixture'}, 'instagram:123'), 'Fixture')
        fallback = contact_label({}, 'instagram:123')
        self.assertTrue(fallback.startswith('Contato do Instagram · '))
        self.assertEqual(fallback, contact_label({}, 'instagram:123'))
        self.assertNotEqual(fallback, contact_label({}, 'instagram:456'))
        self.assertNotIn('123', fallback)

    def test_neutral_fallback_can_be_replaced_by_official_username(self):
        ref = 'instagram:123'
        fallback = contact_label({}, ref)
        read_db, write_db = MagicMock(), MagicMock()
        read_db.__enter__.return_value = read_db
        write_db.__enter__.return_value = write_db
        read_db.execute.return_value.fetchall.return_value = [{
            'id': 41, 'contact_ref': ref, 'contact_name': fallback,
            'connection_id': UUID('12345678-1234-1234-1234-123456789abc'),
            'external_account_id': '987', 'encrypted_token': 'encrypted'
        }]
        write_db.execute.return_value.rowcount = 1
        runtime = MagicMock()
        runtime.status = 'configured'
        runtime.direct.adapter.contact_profile.return_value = {'username': 'actual.user'}

        with patch('instagram_contact_identity.connect', side_effect=[read_db, write_db]):
            result = refresh_contacts(runtime, 1, limit=1)

        self.assertEqual(result['updated'], 1)
        self.assertEqual(result['official_profile_available'], 1)
        sql = read_db.execute.call_args.args[0]
        self.assertIn("[0-9A-F]{6}", sql)
        write_args = write_db.execute.call_args.args[1]
        self.assertEqual(write_args[0], '@actual.user')
        self.assertEqual(write_args[-1], fallback)

    def test_unavailable_profile_does_not_revise_unchanged_fallback(self):
        ref = 'instagram:123'
        fallback = contact_label({}, ref)
        read_db = MagicMock()
        read_db.__enter__.return_value = read_db
        read_db.execute.return_value.fetchall.return_value = [{
            'id': 41, 'contact_ref': ref, 'contact_name': fallback,
            'connection_id': UUID('12345678-1234-1234-1234-123456789abc'),
            'external_account_id': '987', 'encrypted_token': 'encrypted'
        }]
        runtime = MagicMock()
        runtime.status = 'configured'
        runtime.direct.adapter.contact_profile.return_value = {}

        with patch('instagram_contact_identity.connect', return_value=read_db) as connect:
            result = refresh_contacts(runtime, 1, limit=1)

        self.assertEqual(result['updated'], 0)
        connect.assert_called_once()
