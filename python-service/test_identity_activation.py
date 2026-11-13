"""Persistent account activation and scoped invitations; synthetic mail only."""
from concurrent.futures import ThreadPoolExecutor
import os
import unittest
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
import identity_activation as identity
import identity_worker
import test_account_auth as accounts

ENV = {'SOCIALMEI_IDENTITY_MODE': 'enforced', 'SOCIALMEI_SMTP_HOST': 'smtp.example.test',
       'SOCIALMEI_SMTP_PORT': '465', 'SOCIALMEI_SMTP_USER': 'synthetic',
       'SOCIALMEI_SMTP_PASSWORD': 'synthetic-test-only', 'SOCIALMEI_SMTP_FROM': 'sender@example.test'}


class IdentityContracts(unittest.TestCase):
    def test_idle_worker_checks_once_and_uses_bounded_reconciliation(self):
        with patch('sys.argv', ['identity_worker.py', '--run']), patch('identity_worker.configured'), \
                patch('identity_worker.process_one', return_value=False) as process, \
                patch('identity_worker.QueueWakeup') as wakeup:
            self.assertEqual(identity_worker.main(), 0)
        process.assert_called_once()
        wakeup.assert_called_once_with(identity.CHANNEL, interval=60, reconcile=300)

    def test_smtp_transport_uses_tls_and_only_fragment_capability(self):
        config = {'host': 'smtp.example.test', 'user': 'synthetic', 'password': 'synthetic-only', 'from': 'sender@example.test'}
        for port in (465, 587):
            with patch('identity_activation.auth.origin', return_value=accounts.ORIGIN), \
                    patch('identity_activation.smtplib.SMTP_SSL') as implicit, patch('identity_activation.smtplib.SMTP') as explicit:
                identity.send_mail('recipient@example.test', 'T' * 43, 'verification', {**config, 'port': port})
                server = (implicit if port == 465 else explicit).return_value
                message = server.send_message.call_args.args[0]
                self.assertIn('/ativar.html#verificar/' + 'T' * 43, message.get_content())
                if port == 587:
                    self.assertEqual([call[0] for call in server.method_calls][:2], ['starttls', 'login'])

    def test_off_by_default_and_invalid_mode_fails_closed(self):
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled'}):
            self.assertFalse(identity.enabled())
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'typo'}), self.assertRaises(Exception):
            identity.enabled()
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'typo'}), self.assertRaises(Exception):
            identity.guard({'id': 1, '_email_required': False, '_email_verified': False}, '/api/v1/clientes')

    def test_tokens_and_email_validation(self):
        for email in ('a,b@example.test', 'Name<a@example.test>', 'a;b@example.test'):
            with self.subTest(email=email), self.assertRaises(ValueError):
                identity.Invitation(email=email, role='member')
        with self.assertRaises(ValueError):
            identity.Invitation(email='valid@example.test', role='owner')


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class IdentityDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.flags = patch.dict(os.environ, ENV)
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.public = TestClient(accounts.app, base_url=accounts.ORIGIN, headers=accounts.HEADERS)
        self.admin_client.headers['X-SocialMEI-Identity'] = f"{self.admin_client.identity['usuario']['id']}:{self.admin_client.identity['negocio']['id']}"

    def mail(self):
        sent = []
        with patch('identity_activation.send_mail', side_effect=lambda address, token, purpose, config: sent.append((address, token, purpose))):
            self.assertTrue(identity.process_one())
        self.assertEqual(len(sent), 1)
        return sent[0][1]

    def confirm(self, token):
        return self.public.post('/api/v1/auth/verification/confirm', json={'token': token})

    def invitation(self, email='employee@example.test', role='member'):
        result = self.admin_client.post('/api/v1/team/invitations', json={'email': email, 'role': role})
        self.assertEqual(result.status_code, 202, result.text)
        return result.json()['id'], self.mail()

    def test_registration_is_pending_until_one_use_email_proof(self):
        client = self.register()
        self.assertEqual(client.identity['email_verification'], {'required': True, 'verified': False})
        self.assertEqual(client.get('/api/v1/clientes').status_code, 403)
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled'}):
            self.assertEqual(client.get('/api/v1/clientes').status_code, 403)
            self.assertTrue(client.get('/api/v1/auth/me').json()['email_verification']['required'])
            self.assertFalse(client.get('/api/v1/auth/me').json()['email_verification']['verified'])
        token = self.mail()
        self.assertEqual(self.confirm(token).status_code, 200)
        self.assertEqual(self.confirm(token).status_code, 400)
        self.assertEqual(client.get('/api/v1/clientes').status_code, 200)
        self.assertTrue(client.get('/api/v1/auth/me').json()['email_verification']['verified'])
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.users SET email='changed@example.test' WHERE id=%s", (client.identity['usuario']['id'],))
            conn.execute("UPDATE socialmei.auth_identity_mail SET created_at=NOW()-INTERVAL '61 seconds'")
        self.assertEqual(client.get('/api/v1/clientes').status_code, 403)
        self.assertEqual(client.post('/api/v1/auth/verification/resend', json={}).status_code, 202)
        self.assertEqual(self.confirm(self.mail()).status_code, 200)
        self.assertEqual(client.get('/api/v1/clientes').status_code, 200)

    def test_missing_smtp_never_silently_opens_registration(self):
        with patch.dict(os.environ, {'SOCIALMEI_SMTP_HOST': ''}):
            response = self.public.post('/api/v1/auth/register', json={'nome': 'New', 'email': 'new@example.test', 'senha': accounts.PASSWORD})
        self.assertEqual(response.status_code, 503)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM socialmei.users WHERE email='new@example.test'").fetchone()[0], 0)

    def test_correction_and_resend_invalidate_previous_links(self):
        client = self.register()
        previous = self.mail()
        bad = client.post('/api/v1/auth/verification/email', json={'email': 'correct@example.test', 'atual': 'wrong'})
        self.assertEqual(bad.status_code, 400)
        result = client.post('/api/v1/auth/verification/email', json={'email': 'correct@example.test', 'atual': accounts.PASSWORD})
        self.assertEqual(result.status_code, 202, result.text)
        self.assertEqual(self.confirm(previous).status_code, 400)
        current = self.mail()
        self.assertEqual(client.post('/api/v1/auth/verification/resend', json={}).status_code, 429)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.auth_identity_mail SET created_at=NOW()-INTERVAL '61 seconds'")
        self.assertEqual(client.post('/api/v1/auth/verification/resend', json={}).status_code, 202)
        self.assertEqual(self.confirm(current).status_code, 400)
        self.assertEqual(self.confirm(self.mail()).status_code, 200)
        self.assertEqual(client.get('/api/v1/auth/me').json()['usuario']['email'], 'correct@example.test')

    def test_uncertain_and_interrupted_mail_are_not_retried(self):
        client = self.register()
        with patch('identity_activation.send_mail', side_effect=OSError('PRIVATE_TRANSPORT_VALUE')) as sender:
            self.assertTrue(identity.process_one())
            self.assertFalse(identity.process_one())
            sender.assert_called_once()
        with psycopg.connect(accounts.DB) as conn:
            status, hashed = conn.execute('SELECT status,token_hash FROM socialmei.auth_identity_mail').fetchone()
        self.assertEqual((status, hashed), ('uncertain', None))
        self.assertEqual(client.get('/api/v1/clientes').status_code, 403)
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.auth_identity_mail SET status='processing',started_at=NOW()-INTERVAL '3 minutes'")
        with patch('identity_activation.send_mail', side_effect=AssertionError('replayed')):
            self.assertFalse(identity.process_one())

    def test_invited_employee_creates_no_new_business_and_cannot_escalate(self):
        _, token = self.invitation(role='viewer')
        preview = self.public.post('/api/v1/auth/invitations/inspect', json={'token': token})
        self.assertEqual(preview.status_code, 200)
        self.assertNotIn('workspace_id', preview.json())
        payload = {'token': token, 'email': 'employee@example.test', 'nome': 'Employee', 'senha': accounts.PASSWORD}
        result = self.public.post('/api/v1/auth/invitations/accept', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.public.post('/api/v1/auth/invitations/accept', json=payload).status_code, 400)
        client = self.login('employee@example.test')
        self.assertEqual(client.identity['papel'], 'viewer')
        self.assertEqual(client.post('/api/v1/produtos', json={'nome': 'Forbidden', 'preco': 1}).status_code, 403)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.workspaces').fetchone()[0], 1)

    def test_existing_account_requires_own_session_and_preserves_password_and_business(self):
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled'}):
            client = self.register('existing@example.test')
        _, token = self.invitation('existing@example.test', role='admin')
        payload = {'token': token, 'email': 'existing@example.test'}
        self.assertEqual(self.public.post('/api/v1/auth/invitations/accept', json=payload).status_code, 409)
        accepted = client.post('/api/v1/auth/invitations/accept', json=payload)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.login('existing@example.test').identity['negocio']['id'], client.identity['negocio']['id'])
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.workspace_members WHERE user_id=%s', (client.identity['usuario']['id'],)).fetchone()[0], 2)

    def test_late_callback_and_revocation_do_not_grant_membership(self):
        job, token = self.invitation()
        self.assertEqual(self.admin_client.delete('/api/v1/team/invitations/' + job).status_code, 204)
        self.assertEqual(self.public.post('/api/v1/auth/invitations/inspect', json={'token': token}).status_code, 400)
        _, token = self.invitation('late@example.test')
        with psycopg.connect(accounts.DB) as conn:
            conn.execute("UPDATE socialmei.workspace_members SET role='member' WHERE user_id=%s", (self.admin_id,))
        result = self.public.post('/api/v1/auth/invitations/accept', json={'token': token, 'email': 'late@example.test', 'nome': 'Late', 'senha': accounts.PASSWORD})
        self.assertEqual(result.status_code, 409)

    def test_concurrent_confirmation_has_one_winner(self):
        self.register()
        token = self.mail()
        def submit(_):
            return TestClient(accounts.app, base_url=accounts.ORIGIN, headers=accounts.HEADERS).post('/api/v1/auth/verification/confirm', json={'token': token}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(submit, range(2))), [200, 400])

    def test_admin_invitation_access_can_be_revoked_without_touching_other_business(self):
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled'}):
            client = self.register('admin-employee@example.test')
        job, token = self.invitation('admin-employee@example.test', 'admin')
        accepted = client.post('/api/v1/auth/invitations/accept', json={'token': token, 'email': 'admin-employee@example.test'})
        self.assertEqual(accepted.status_code, 200, accepted.text)
        result = self.admin_client.request('DELETE', '/api/v1/team/invitations/' + job + '/access', json={'expected_role': 'member'})
        self.assertEqual(result.status_code, 409)
        result = self.admin_client.request('DELETE', '/api/v1/team/invitations/' + job + '/access', json={'expected_role': 'admin'})
        self.assertEqual(result.status_code, 204, result.text)
        self.assertEqual(client.get('/api/v1/clientes').status_code, 200)
        with psycopg.connect(accounts.DB) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM socialmei.workspace_members WHERE user_id=%s', (client.identity['usuario']['id'],)).fetchone()[0], 1)

    def test_accept_rejects_common_password_without_echo_or_server_error(self):
        _, token = self.invitation()
        result = self.public.post('/api/v1/auth/invitations/accept', json={'token': token, 'email': 'employee@example.test', 'nome': 'Employee', 'senha': 'password'})
        self.assertEqual(result.status_code, 422)
        self.assertNotIn(token, result.text)

    def test_foreign_business_cannot_revoke_an_invitation_or_guess_its_target(self):
        with patch.dict(os.environ, {'SOCIALMEI_IDENTITY_MODE': 'disabled'}):
            other = self.register('other-owner@example.test')
        other.headers['X-SocialMEI-Identity'] = f"{other.identity['usuario']['id']}:{other.identity['negocio']['id']}"
        job, token = self.invitation()
        self.assertEqual(other.delete('/api/v1/team/invitations/' + job).status_code, 204)
        self.assertEqual(self.public.post('/api/v1/auth/invitations/inspect', json={'token': token}).status_code, 200)
        result = other.post('/api/v1/auth/invitations/accept', json={'token': token, 'email': 'employee@example.test'})
        self.assertEqual(result.status_code, 422)
        self.assertEqual(other.get('/api/v1/team/invitations').json()['items'], [])
