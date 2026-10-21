"""Private profile contract; PostgreSQL cases use TEST_DATABASE_URL only."""
import copy
import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from app import app
from account_auth import COOKIE, csrf, digest
import test_account_auth as account_tests
from test_account_auth import ENV, ORIGIN, HEADERS, DB
from workspace_profile import Capabilities, default_preferences

PROFILE_PATH = '/api/v1/workspace-profile'
PREF_PATH = '/api/v1/auth/preferences'
PROFILE = {'version': 1, 'businessName': 'Submitted name', 'segment': 'laboratory',
           'activity': ' Technical services ', 'offers': ['services'],
           'services': [' Analysis ', 'Analysis'], 'productCategories': [],
           'capabilities': {key: False for key in Capabilities.model_fields},
           'modules': ['clients', 'services', 'inventory'],
           'ignoredSuggestions': ['Serviço:analysis'], 'completed': True}


def payload(value=PROFILE, revision=0, field='profile'):
    return {'schema_version': 1, 'expected_revision': revision, field: copy.deepcopy(value)}


class ProfileGuards(unittest.TestCase):
    def test_disabled_and_missing_configuration_fail_closed_without_database(self):
        client = TestClient(app, base_url=ORIGIN)
        with patch('workspace_profile.connect', side_effect=AssertionError('unexpected database')):
            with patch.dict(os.environ, {**ENV, 'SOCIALMEI_AUTH_ENABLED': 'false'}):
                for path in (PROFILE_PATH, PREF_PATH):
                    response = client.get(path)
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.headers['cache-control'], 'no-store')
            with patch.dict(os.environ, {**ENV, 'SOCIALMEI_AUTH_ORIGIN': ''}):
                self.assertEqual(client.get(PROFILE_PATH).status_code, 503)
            with patch.dict(os.environ, ENV):
                self.assertEqual(client.get(PROFILE_PATH).status_code, 401)


@unittest.skipUnless(DB, 'TEST_DATABASE_URL not configured')
class ProfileDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(account_tests.AccountDatabaseTests.setUpClass.__func__)
    setUp = account_tests.AccountDatabaseTests.setUp
    login = account_tests.AccountDatabaseTests.login
    invited = account_tests.AccountDatabaseTests.invited
    register = account_tests.AccountDatabaseTests.register

    def test_empty_reads_do_not_seed_and_have_no_store(self):
        for path, field, default in ((PROFILE_PATH, 'profile', None), (PREF_PATH, 'preferences', default_preferences())):
            response = self.admin_client.get(path)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), {'schema_version': 1, 'revision': 0, field: default})
            self.assertEqual(response.headers['cache-control'], 'no-store')
        with psycopg.connect(DB) as conn:
            for table in ('workspace_profiles', 'auth_preferences'):
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM socialmei.' + table).fetchone()[0], 0)

    def test_two_sessions_normalization_canonical_identity_and_stale_writes(self):
        other = self.login('admin@example.com')
        response = self.admin_client.patch(PROFILE_PATH, json=payload())
        self.assertEqual(response.status_code, 200, response.text)
        profile = response.json()['profile']
        self.assertEqual(profile['businessName'], 'Existing team')
        self.assertEqual(profile['services'], ['Analysis'])
        self.assertEqual(profile['modules'], ['clients', 'services'])
        self.assertEqual(other.get(PROFILE_PATH).json(), response.json())
        self.assertEqual(other.patch(PROFILE_PATH, json=payload()).status_code, 409)
        self.assertEqual(other.patch(PROFILE_PATH, json=payload(revision=1)).json()['revision'], 2)
        self.assertEqual(self.admin_client.get('/api/v1/auth/me').json()['negocio']['nome'], 'Existing team')

    def test_same_user_membership_switched_remains_workspace_isolated(self):
        self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload()).status_code, 200)
        prefs = payload(default_preferences(), field='preferences')
        prefs['preferences']['theme'] = 'dark'
        self.assertEqual(self.admin_client.patch(PREF_PATH, json=prefs).status_code, 200)
        token = 'b' * 64
        with psycopg.connect(DB) as conn:
            workspace = conn.execute("INSERT INTO socialmei.workspaces(slug,nome) VALUES('second','Second workspace') RETURNING id").fetchone()[0]
            conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')", (workspace, self.admin_id))
            conn.execute("INSERT INTO socialmei.auth_sessoes(token_hash,user_id,workspace_id,expira_em) VALUES(%s,%s,%s,NOW()+INTERVAL '1 hour')", (digest(token), self.admin_id, workspace))
        other = TestClient(app, base_url=ORIGIN, headers={**HEADERS, 'X-SocialMEI-CSRF': csrf(token)})
        other.cookies.set(COOKIE, token)
        self.assertIsNone(other.get(PROFILE_PATH).json()['profile'])
        self.assertEqual(other.get(PREF_PATH).json()['preferences']['theme'], 'auto')
        self.assertEqual(other.patch(PROFILE_PATH, json=payload(revision=1)).status_code, 409)
        spoof = payload(); spoof['workspace_id'] = self.admin_client.identity['negocio']['id']
        self.assertEqual(other.patch(PROFILE_PATH, json=spoof).status_code, 422)
        self.assertEqual(other.get(PROFILE_PATH + '?workspace_id=1').status_code, 422)
        self.assertEqual(other.patch(PROFILE_PATH, json=payload()).json()['profile']['businessName'], 'Second workspace')
        self.assertEqual(self.admin_client.get(PROFILE_PATH).json()['profile']['businessName'], 'Existing team')

    def test_roles_and_preferences_are_membership_private(self):
        member = self.register('member@example.com')
        with psycopg.connect(DB) as conn:
            conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'member')", (self.admin_client.identity['negocio']['id'], member.identity['usuario']['id']))
            conn.execute('UPDATE socialmei.auth_sessoes SET workspace_id=%s WHERE user_id=%s', (self.admin_client.identity['negocio']['id'], member.identity['usuario']['id']))
        # Even a platform administrator cannot bypass a business membership role.
        for role in ('owner', 'admin', 'member', 'viewer'):
            with self.subTest(role=role), psycopg.connect(DB) as conn:
                conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s', (role, self.admin_id))
            self.assertEqual(self.admin_client.get(PROFILE_PATH).status_code, 200)
            current = self.admin_client.get(PROFILE_PATH).json()['revision']
            expected = 200 if role in ('owner', 'admin') else 403
            self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=payload(revision=current)).status_code, expected)
            current = self.admin_client.get(PREF_PATH).json()['revision']
            self.assertEqual(self.admin_client.patch(PREF_PATH, json=payload(default_preferences(), current, 'preferences')).status_code, 200)
        self.assertEqual(member.get(PREF_PATH).json()['revision'], 0)
        self.assertEqual(member.get(PROFILE_PATH).json()['revision'], 2)

    def test_concurrent_insert_and_updates_have_exactly_one_winner(self):
        for path, value, field in ((PROFILE_PATH, PROFILE, 'profile'), (PREF_PATH, default_preferences(), 'preferences')):
            clients = [self.login('admin@example.com') for _ in range(2)]
            for revision in (0, 1):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(lambda client: client.patch(path, json=payload(value, revision, field)), clients))
                self.assertEqual(sorted(response.status_code for response in responses), [200, 409])
                self.assertEqual(self.admin_client.get(path).json()['revision'], revision + 1)

    def test_origin_csrf_and_unauthenticated_write_guards(self):
        for path, body in ((PROFILE_PATH, payload()), (PREF_PATH, payload(default_preferences(), field='preferences'))):
            other = TestClient(app, base_url=ORIGIN, headers=HEADERS)
            self.assertEqual(other.patch(path, json=body).status_code, 401)
            other.cookies.update(self.admin_client.cookies)
            self.assertEqual(other.patch(path, json=body).status_code, 403)
            self.assertEqual(self.admin_client.patch(path, json=body, headers={'Origin': 'https://evil.example'}).status_code, 403)

    def test_strict_validation_does_not_echo_values_and_does_not_write(self):
        invalid = []
        for key, value in [('schema_version', True), ('expected_revision', True), ('expected_revision', -1), ('expected_revision', '0'), ('schema_version', 2), ('workspace_id', 9)]:
            body = payload(); body[key] = value; invalid.append(body)
        for key, value in [('businessName', 'x'*121), ('segment', 'unsupported'), ('offers', ['bad']), ('services', ['x']*31), ('ignoredSuggestions', ['x']*61), ('modules', ['bad']), ('completed', 1), ('version', True), ('logo', 'private-value'), ('activity', None), ('activity', '\x00'), ('activity', '\ud800')]:
            body = payload(); body['profile'][key] = value; invalid.append(body)
        body = payload(); body['profile']['capabilities']['team'] = 'true'; invalid.append(body)
        for body in invalid:
            with self.subTest(body=body):
                response = self.admin_client.patch(PROFILE_PATH, content=json.dumps(body), headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertNotIn('private-value', response.text)
                self.assertEqual(response.headers['cache-control'], 'no-store')
        for field, value in [('theme', 'custom-secret'), ('notificationsEnabled', 1), ('workspace_id', 42)]:
            body = payload(default_preferences(), field='preferences'); body['preferences'][field] = value
            self.assertEqual(self.admin_client.patch(PREF_PATH, json=body).status_code, 422)
        for value in ('25:00', '1:00', '12:60', None):
            body = payload(default_preferences(), field='preferences'); body['preferences']['notifications']['quietFrom'] = value
            self.assertEqual(self.admin_client.patch(PREF_PATH, json=body).status_code, 422)
        self.assertEqual(self.admin_client.get(PROFILE_PATH).json()['revision'], 0)

    def test_incomplete_profiles_cannot_create_or_replace_saved_profile(self):
        for key, value in [('completed', False), ('offers', []), ('offers', [' '])]:
            body = payload()
            body['profile'][key] = value
            response = self.admin_client.patch(PROFILE_PATH, json=body)
            self.assertEqual(response.status_code, 422, response.text)
            self.assertEqual(self.admin_client.get(PROFILE_PATH).json()['revision'], 0)
            self.assertIsNone(self.admin_client.get(PROFILE_PATH).json()['profile'])
        saved = self.admin_client.patch(PROFILE_PATH, json=payload())
        self.assertEqual(saved.status_code, 200, saved.text)
        for key, value in [('completed', False), ('offers', [])]:
            body = payload(revision=1)
            body['profile'][key] = value
            self.assertEqual(self.admin_client.patch(PROFILE_PATH, json=body).status_code, 422)
            self.assertEqual(self.admin_client.get(PROFILE_PATH).json(), saved.json())

    def test_profile_size_is_checked_after_canonical_name_normalization(self):
        profile = copy.deepcopy(PROFILE)
        profile.update({
            'businessName': '', 'activity': '', 'offers': ['products', 'services'], 'modules': [],
            'services': [str(i).zfill(2) + 'x' * 118 for i in range(30)],
            'productCategories': [str(i).zfill(2) + 'y' * 118 for i in range(30)],
            'ignoredSuggestions': [str(i).zfill(2) + 'z' * 158 for i in range(60)],
        })
        size = lambda value: len(json.dumps(value, ensure_ascii=False).encode())
        remaining = 32768 - size(profile)
        for field in ('ignoredSuggestions', 'services', 'productCategories'):
            for i, text in enumerate(profile[field]):
                count = min(remaining, len(text) - 2)
                profile[field][i] = text[:2] + 'é' * count + text[2 + count:]
                remaining -= count
        self.assertEqual(size(profile), 32768)
        response = self.admin_client.patch(PROFILE_PATH, json=payload(profile))
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIsNone(self.admin_client.get(PROFILE_PATH).json()['profile'])
        # Removing exactly the canonical name's byte length permits a stable round trip.
        profile['ignoredSuggestions'][0] = profile['ignoredSuggestions'][0].replace('é', 'a', len('Existing team'))
        response = self.admin_client.patch(PROFILE_PATH, json=payload(profile))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(size(response.json()['profile']), 32768)
        self.assertEqual(self.admin_client.get(PROFILE_PATH).json(), response.json())

    def test_missing_migration_and_database_configuration_are_safe(self):
        with patch('workspace_profile.connect', side_effect=psycopg.errors.UndefinedTable('private database text')):
            response = self.admin_client.get(PROFILE_PATH)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('private database text', response.text)
        with patch('workspace_profile.connect', side_effect=RuntimeError('private configuration')):
            self.assertEqual(self.admin_client.get(PREF_PATH).status_code, 503)

    def test_real_missing_profile_table_fails_closed(self):
        with psycopg.connect(DB, autocommit=True) as conn:
            conn.execute('ALTER TABLE socialmei.workspace_profiles RENAME TO qa78_missing_profile')
            try:
                response = self.admin_client.get(PROFILE_PATH)
                self.assertEqual(response.status_code, 503)
                self.assertNotIn('workspace_profiles', response.text)
            finally:
                conn.execute('ALTER TABLE socialmei.qa78_missing_profile RENAME TO workspace_profiles')
