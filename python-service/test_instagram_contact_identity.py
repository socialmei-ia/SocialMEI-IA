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
        token_binding = runtime.direct.vault.open.call_args.args[1]
        self.assertEqual(token_binding.workspace_id, 1)
        self.assertEqual(token_binding.connection_id, UUID('12345678-1234-1234-1234-123456789abc'))
        self.assertEqual(token_binding.account_id, '987')
        self.assertEqual(read_db.execute.call_args.args[1], (1, 0, 1))
        self.assertEqual(write_args[1:5], (1, 41, 'instagram:987', ref))

    def test_concurrent_name_edit_is_not_overwritten(self):
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
        # Another operation changed contact_name after the SELECT.
        write_db.execute.return_value.rowcount = 0
        runtime = MagicMock()
        runtime.status = 'configured'
        runtime.direct.adapter.contact_profile.return_value = {'username': 'actual.user'}
        with patch('instagram_contact_identity.connect', side_effect=[read_db, write_db]):
            result = refresh_contacts(runtime, 1, limit=1)
        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['last_id'], 41)
        sql, arguments = write_db.execute.call_args.args
        self.assertIn('AND contact_name=%s', sql)
        self.assertEqual(arguments[-1], fallback)

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

    def test_refresh_cursor_advances_past_unresolved_contact(self):
        # Selecting from id 41 must allow the worker to inspect later contacts,
        # even if the first contact still has an unavailable Meta profile.
        ref = 'instagram:456'
        fallback = contact_label({}, ref)
        read_db = MagicMock()
        read_db.__enter__.return_value = read_db
        read_db.execute.return_value.fetchall.return_value = [{
            'id': 42, 'contact_ref': ref, 'contact_name': fallback,
            'connection_id': UUID('12345678-1234-1234-1234-123456789abc'),
            'external_account_id': '987', 'encrypted_token': 'encrypted'
        }]
        runtime = MagicMock()
        runtime.status = 'configured'
        runtime.direct.adapter.contact_profile.return_value = {}
        with patch('instagram_contact_identity.connect', return_value=read_db):
            result = refresh_contacts(runtime, 1, limit=1, after_id=41)

        self.assertEqual(result['updated'], 0)
        self.assertEqual(result['last_id'], 42)
        sql, arguments = read_db.execute.call_args.args
        self.assertIn('v.id>%s', sql)
        self.assertEqual(arguments, (1, 41, 1))

    def test_refresh_cursor_resets_at_end_without_provider_call(self):
        read_db = MagicMock()
        read_db.__enter__.return_value = read_db
        read_db.execute.return_value.fetchall.return_value = []
        runtime = MagicMock()
        runtime.status = 'configured'
        with patch('instagram_contact_identity.connect', return_value=read_db):
            result = refresh_contacts(runtime, 1, limit=1, after_id=42)
        self.assertEqual(result['last_id'], 0)
        runtime.direct.adapter.contact_profile.assert_not_called()

    def test_invalid_refresh_cursor_fails_closed(self):
        runtime = MagicMock()
        runtime.status = 'configured'
        with patch('instagram_contact_identity.connect') as connect:
            for after_id in (True, -1, '41', 1.0, 2**63):
                with self.subTest(after_id=after_id), self.assertRaises(ValueError):
                    refresh_contacts(runtime, 1, after_id=after_id)
            connect.assert_not_called()

    def test_invalid_limit_and_workspace_fail_before_database(self):
        runtime = MagicMock()
        runtime.status = 'configured'
        with patch('instagram_contact_identity.connect') as connect:
            for limit in (True, 1.0, '1', None, 0, 11):
                with self.subTest(limit=limit), self.assertRaises(ValueError):
                    refresh_contacts(runtime, 1, limit=limit)
            for workspace in (True, 0, -1, '1', 2**63):
                with self.subTest(workspace=workspace), self.assertRaises(ValueError):
                    refresh_contacts(runtime, workspace)
            connect.assert_not_called()
