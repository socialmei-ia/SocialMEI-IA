"""Trusted c.us phone labels; opaque LIDs and human names are never guessed/replaced."""
import unittest
import psycopg
from waha_ingress import parse_event
import test_waha_ingress as fixtures


def event(sender, mid='phone-label-mid'):
    value = fixtures.payload(mid)
    value['payload']['from'] = sender
    return value


class PhoneLabelTests(unittest.TestCase):
    def test_direct_phone_identifier_displays_number_but_lid_and_invalid_lengths_do_not(self):
        for sender, expected in (
            ('5581990001234@c.us', '+5581990001234'),
            ('14155550123@c.us', '+14155550123'),
            ('5581990001234@lid', 'Contato do WhatsApp'),
            ('222@c.us', 'Contato do WhatsApp'),
            ('01234567890@c.us', 'Contato do WhatsApp'),
            ('1234567890123456@c.us', 'Contato do WhatsApp'),
        ):
            raw = fixtures.raw(event(sender))
            parsed = parse_event(raw, fixtures.sign(raw), 'sha512', fixtures.binding())
            self.assertEqual(parsed.contact_name, expected)


@unittest.skipUnless(fixtures.DB, 'Disposable PostgreSQL required')
class PhoneLabelDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.DatabaseTests.setUpClass.__func__)
    setUp = fixtures.DatabaseTests.setUp
    tearDown = fixtures.DatabaseTests.tearDown
    receive = fixtures.DatabaseTests.receive

    def test_phone_generic_upgrade_preserves_human_names_refs_messages_and_other_workspace(self):
        sender = '5581990001234@c.us'
        self.receive(event(sender, 'first'))
        with psycopg.connect(fixtures.DB) as conn:
            before = conn.execute('SELECT id,revision,contact_name,contact_ref,account_ref FROM socialmei.me_conversations WHERE workspace_id=%s', (self.bindings[0].workspace_id,)).fetchone()
            self.assertEqual(before[2], '+5581990001234')
            conn.execute("UPDATE socialmei.me_conversations SET contact_name='Contato do WhatsApp' WHERE id=%s", (before[0],))
        self.receive(event(sender, 'second'))
        with psycopg.connect(fixtures.DB) as conn:
            after = conn.execute('SELECT id,revision,contact_name,contact_ref,account_ref FROM socialmei.me_conversations WHERE id=%s', (before[0],)).fetchone()
            self.assertEqual(after[1], before[1]+1)
            self.assertEqual(after[2], '+5581990001234')
            self.assertEqual(after[3:], before[3:])
            conn.execute("UPDATE socialmei.me_conversations SET contact_name='Nome humano preservado' WHERE id=%s", (before[0],))
        self.receive(event(sender, 'third'))
        self.assertEqual(self.receive(event(sender, 'third'))['duplicates'], 1)
        self.receive(event(sender, 'third'), self.bindings[1])
        with psycopg.connect(fixtures.DB) as conn:
            self.assertEqual(conn.execute('SELECT contact_name FROM socialmei.me_conversations WHERE id=%s', (before[0],)).fetchone()[0], 'Nome humano preservado')
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.me_messages WHERE workspace_id=%s', (self.bindings[0].workspace_id,)).fetchone()[0], 3)
            self.assertEqual(conn.execute('SELECT contact_name FROM socialmei.me_conversations WHERE workspace_id=%s', (self.bindings[1].workspace_id,)).fetchone()[0], '+5581990001234')
