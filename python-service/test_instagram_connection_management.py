"""Verified workspace management; provider and contacts are synthetic."""
from datetime import datetime, timezone
import unittest

import psycopg
from psycopg.types.json import Jsonb

import test_instagram_persistent_oauth as oauth
from integration_setup import InstagramSetup


@unittest.skipUnless(oauth.DB, 'Disposable PostgreSQL required')
class ManagementTests(unittest.TestCase):
    setUpClass = classmethod(oauth.PersistentTests.setUpClass.__func__)
    setUp = oauth.PersistentTests.setUp
    tearDown = oauth.PersistentTests.tearDown
    post = oauth.PersistentTests.post
    begin = oauth.PersistentTests.begin
    complete = oauth.PersistentTests.complete
    connection = oauth.PersistentTests.connection

    def status(self):
        response = self.client.get(oauth.PREFIX + '/status')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_verified_profile_is_bound_to_oauth_not_preparation_or_a_different_connection(self):
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("INSERT INTO socialmei.integration_setup(workspace_id,instagram,updated_by) VALUES(%s,%s,%s)",
                         (self.identity['workspace_id'], Jsonb(InstagramSetup(username='unverified_name').normalized()), self.identity['id']))
        state = self.begin()
        self.assertEqual(self.complete(state).status_code, 200)
        result = self.status()
        self.assertEqual(result['username'], 'synthetic_account')
        self.assertEqual(result['workspace_id'], self.identity['workspace_id'])
        self.assertEqual(result['source'], 'verified_oauth_store')
        self.assertEqual(result['connection_state'], 'connected')
        self.assertNotIn('synthetic-long-token', str(result))
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("UPDATE socialmei.workspaces SET configuracao=jsonb_set(configuracao,'{instagram_profile,connection_id}',%s) WHERE id=%s",
                         (Jsonb('different-connection'), self.identity['workspace_id']))
        self.assertIsNone(self.status()['username'])

    def test_pending_callback_is_distinct_and_status_never_contacts_meta(self):
        self.assertEqual(self.status()['connection_state'], 'not_connected')
        state = self.begin()
        self.assertEqual(self.status()['connection_state'], 'connecting')
        self.assertEqual(self.complete(state).status_code, 200)
        count = len(self.transport.calls)
        for _ in range(3):
            self.assertFalse(self.status()['receiving_messages'])
        self.assertEqual(len(self.transport.calls), count)
        self.assertEqual(self.post('/connection/disconnect').status_code, 200)
        self.assertEqual(self.status()['connection_state'], 'disconnected')

    def test_expiry_permissions_and_renewal_are_different_server_evidence(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '2 days',expires_at=NOW()+INTERVAL '1 day' WHERE workspace_id=%s",
                         (self.identity['workspace_id'],))
        result = self.status()
        self.assertTrue(result['renewal']['eligible'])
        self.assertTrue(result['renewal']['expiring_soon'])
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET scopes=ARRAY['instagram_business_basic'] WHERE workspace_id=%s",
                         (self.identity['workspace_id'],))
        result = self.status()
        self.assertEqual(result['connection_state'], 'attention')
        self.assertEqual(result['attention_reason'], 'permissions_missing')
        self.assertIn('instagram_business_manage_messages', result['missing_scopes'])
        self.assertFalse(result['receiving_messages'])
        self.assertFalse(result['renewal']['eligible'])
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET expires_at=NOW()-INTERVAL '1 second' WHERE workspace_id=%s",
                         (self.identity['workspace_id'],))
        result = self.status()
        self.assertEqual(result['status'], 'expired')
        self.assertFalse(result['credential_available'])
        self.assertEqual(result['attention_reason'], 'credential_expired')

    def test_preparation_remains_explicitly_non_authoritative_after_real_connection(self):
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        response = self.client.get('/api/v1/integrations/setup')
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertFalse(value['connected'])
        self.assertEqual(value['purpose'], 'preparation_only')
        self.assertEqual(value['connection_status_path'], oauth.PREFIX + '/status')
        self.assertEqual(self.status()['connection_state'], 'connected')

    def test_receiving_requires_recent_authenticated_events_for_the_current_connection(self):
        from instagram_meta_ingress import InstagramIngressService
        from test_instagram_meta_ingress import KEY, VERIFY, encoded, payload, signature
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        ingress = InstagramIngressService(app_secret=KEY, verify_token=VERIFY)
        old = encoded(payload(mid='historical-proof'))
        self.assertEqual(ingress.receive(old, signature(old))['processed'], 1)
        self.assertFalse(self.status()['receiving_messages'])
        current = payload(mid='current-proof')
        current['entry'][0]['messaging'][0]['timestamp'] = int(datetime.now(timezone.utc).timestamp() * 1000)
        raw = encoded(current)
        self.assertEqual(ingress.receive(raw, signature(raw))['processed'], 1)
        self.assertTrue(self.status()['receiving_messages'])
        self.assertEqual(self.post('/connection/disconnect').status_code, 200)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.assertFalse(self.status()['receiving_messages'])
