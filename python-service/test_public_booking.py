"""Visitor contracts and real disposable PostgreSQL; SMTP stays synthetic."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
import public_booking as public
import test_account_auth as accounts
import test_service_appointments as fixtures

KEY = 'synthetic-public-booking-key-not-real-' + 'k' * 32
ENV = {'SOCIALMEI_PUBLIC_BOOKING_ENABLED': 'true', 'SOCIALMEI_PUBLIC_BOOKING_KEY': KEY,
       'SOCIALMEI_SMTP_HOST': 'smtp.example.test', 'SOCIALMEI_SMTP_USER': 'synthetic-user',
       'SOCIALMEI_SMTP_PASSWORD': 'synthetic-not-a-credential', 'SOCIALMEI_SMTP_FROM': 'sender@example.test'}


class PublicContracts(unittest.TestCase):
    def test_contact_is_a_single_mailbox_and_publication_ids_are_strict(self):
        for address in ('a,b@example.test', 'a;b@example.test', 'Nome<a@example.test>'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                public.VerificationRequest(offer='opaque', name='Teste', email=address)
        self.assertEqual(public.VerificationRequest(offer='opaque', name='Teste', email='A+tag@example.test').email, 'a+tag@example.test')
        for identifiers in ([True], ['1'], [1, 1]):
            with self.subTest(ids=identifiers), self.assertRaises(ValueError):
                public.Publication(service_ids=identifiers)

    def test_disabled_feature_never_accesses_database_or_admin_identity(self):
        with patch.dict(os.environ, {**accounts.ENV, 'SOCIALMEI_PUBLIC_BOOKING_ENABLED': 'false'}), \
                patch('public_booking.connect', side_effect=AssertionError('database')), \
                patch('account_auth.session_identity', side_effect=AssertionError('account')):
            response = TestClient(accounts.app).get('/api/v1/public/booking/test')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_incomplete_smtp_fails_closed_before_database_access(self):
        with patch.dict(os.environ, {**accounts.ENV, **ENV, 'SOCIALMEI_SMTP_HOST': ''}), \
                patch('public_booking.connect', side_effect=AssertionError('database')):
            response = TestClient(accounts.app).get('/api/v1/public/booking/test')
        self.assertEqual(response.status_code, 503)

    def test_tokens_are_encrypted_purpose_bound_and_tamper_proof(self):
        with patch.dict(os.environ, ENV):
            token = public.opaque('test', {'email': 'visitor@example.test', 'workspace': 17})
            self.assertNotIn('visitor', token)
            self.assertEqual(public.decode(token, 'test')['workspace'], 17)
            for altered, purpose in ((token[:-10] + 'A' * 10, 'test'), (token, 'other')):
                with self.assertRaises(Exception):
                    public.decode(altered, purpose)
            expired = public.opaque('test', {}, -1)
            with self.assertRaises(Exception):
                public.decode(expired, 'test')

    def test_validation_response_never_echoes_contact_or_proof(self):
        with patch.dict(os.environ, {**accounts.ENV, **ENV}), patch('public_booking.limit'):
            response = TestClient(accounts.app, base_url=accounts.ORIGIN).post(
                '/api/v1/public/booking/test/verification/confirm', headers={'Origin': accounts.ORIGIN},
                json={'challenge': 'PRIVATE_PROOF_VALUE', 'code': 'secret-contact@example.test'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('PRIVATE_PROOF', response.text)
        self.assertNotIn('secret-contact', response.text)

    def test_smtp_requires_tls_and_uncertain_results_are_sanitized(self):
        env = {'SOCIALMEI_SMTP_HOST': 'smtp.example.test', 'SOCIALMEI_SMTP_USER': 'synthetic-user',
               'SOCIALMEI_SMTP_PASSWORD': 'synthetic-private-password', 'SOCIALMEI_SMTP_FROM': 'sender@example.test'}
        for port in (465, 587):
            with patch.dict(os.environ, {**env, 'SOCIALMEI_SMTP_PORT': str(port)}), \
                    patch('public_booking.smtplib.SMTP_SSL') as implicit, patch('public_booking.smtplib.SMTP') as explicit:
                public.send_code('visitor@example.test', '123456')
                server = (implicit if port == 465 else explicit).return_value
                server.send_message.assert_called_once()
                if port == 587:
                    self.assertEqual([call[0] for call in server.method_calls][:2], ['starttls', 'login'])
        with patch.dict(os.environ, {**env, 'SOCIALMEI_SMTP_PORT': '465'}), \
                patch('public_booking.smtplib.SMTP_SSL', side_effect=RuntimeError('PRIVATE PASSWORD')):
            with self.assertRaises(public.HTTPException) as caught:
                public.send_code('visitor@example.test', '123456')
            self.assertEqual(caught.exception.status_code, 503)
            self.assertNotIn('PRIVATE', caught.exception.detail)


@unittest.skipUnless(accounts.DB, 'Disposable PostgreSQL required')
class PublicDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    register = accounts.AccountDatabaseTests.register
    invited = accounts.AccountDatabaseTests.invited
    post = fixtures.AppointmentDatabaseTests.post

    def setUp(self):
        fixtures.AppointmentDatabaseTests.setUp(self)
        self.flags = patch.dict(os.environ, ENV)
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.public = TestClient(accounts.app, base_url=accounts.ORIGIN, headers={'Origin': accounts.ORIGIN})
        self.workspace = self.client.identity['negocio']['id']
        with psycopg.connect(accounts.DB) as conn:
            self.slug = conn.execute('SELECT slug FROM socialmei.workspaces WHERE id=%s', (self.workspace,)).fetchone()[0]
        policy = {'enabled': True, 'timezone': 'UTC', 'lead_minutes': 0,
                  'hours': [{'weekday': day, 'opens': '09:00', 'closes': '17:00'} for day in range(7)]}
        self.assertEqual(self.client.put('/api/v1/agenda/channel-booking', json={'expected_revision': 0, 'policy': policy}).status_code, 200)
        self.path = '/api/v1/public/booking/' + self.slug
        self.publish()
        self.day = (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat()

    def publish(self, **changes):
        existing = self.client.get('/api/v1/agenda/public-booking').json()
        policy = {'enabled': True, 'service_ids': [self.service['id']], 'resource_ids': [self.resource['id']],
                  'allow_new_customers': True, 'allow_verified_email_match': False, **changes}
        result = self.client.put('/api/v1/agenda/public-booking', json={'expected_revision': existing['revision'], 'policy': policy})
        self.assertEqual(result.status_code, 200, result.text)

    def get_slots(self):
        result = self.public.get(self.path)
        self.assertEqual(result.status_code, 200, result.text)
        service = result.json()['services'][0]['reference']
        resources = self.public.post(self.path + '/resources', json={'service': service})
        self.assertEqual(resources.status_code, 200, resources.text)
        resource = resources.json()['items'][0]['reference']
        response = self.public.post(self.path + '/slots', json={'service': service, 'resource': resource, 'day': self.day})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def get_offer(self):
        return self.get_slots()['items'][0]['offer']

    def verify(self, offer, email='visitor@example.test'):
        codes = []
        with patch('public_booking.send_code', side_effect=lambda address, code: codes.append(code)):
            result = self.public.post(self.path + '/verification/request', json={'offer': offer, 'name': 'Visitante fictício', 'email': email})
        self.assertEqual(result.status_code, 202, result.text)
        challenge = result.json()['challenge']
        verified = self.public.post(self.path + '/verification/confirm', json={'challenge': challenge, 'code': codes[0]})
        self.assertEqual(verified.status_code, 200, verified.text)
        return verified.json()['proof'], challenge

    def test_verified_guest_booking_is_persistent_visible_and_idempotent(self):
        offer = self.get_offer()
        proof, _ = self.verify(offer)
        payload = {'offer': offer, 'proof': proof, 'confirmed': True}
        result = self.public.post(self.path + '/confirm', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['status'], 'scheduled')
        self.assertEqual(result.json(), self.public.post(self.path + '/confirm', json=payload).json())
        self.assertEqual(set(result.json()), {'status', 'reference', 'scheduled_for', 'service_name', 'duration_minutes', 'price'})
        rows = self.client.get('/api/v1/agenda/appointments').json()['items']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['service_name'], self.service['nome'])
        # Disabling publication after commit must not turn a lost response into another booking.
        self.publish(enabled=False)
        self.assertEqual(result.json(), self.public.post(self.path + '/confirm', json=payload).json())

    def test_unverified_mismatched_and_cross_business_contact_cannot_book(self):
        offer = self.get_offer()
        proof, challenge = self.verify(offer)
        self.assertEqual(self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': challenge, 'confirmed': True}).status_code, 409)
        other = self.register('second-business@example.test')
        with psycopg.connect(accounts.DB) as conn:
            slug = conn.execute('SELECT slug FROM socialmei.workspaces WHERE id=%s', (other.identity['negocio']['id'],)).fetchone()[0]
        cross = self.public.post('/api/v1/public/booking/' + slug + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
        self.assertEqual(cross.status_code, 409)
        self.assertEqual(self.client.get('/api/v1/agenda/appointments').json()['items'], [])

    def test_changed_details_or_policy_are_not_confirmed(self):
        for field, value in (('preco', 200), ('duracao_minutos', 45), ('nome', 'Alterado')):
            offer = self.get_offer()
            proof, _ = self.verify(offer, field + '@example.test')
            current = self.client.get('/api/v1/produtos/' + str(self.service['id'])).json()
            changed = self.client.patch('/api/v1/produtos/' + str(self.service['id']),
                json={'expected_version': current['versao'], field: value})
            self.assertEqual(changed.status_code, 200, changed.text)
            result = self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
            self.assertEqual(result.status_code, 409, result.text)
        self.assertEqual(self.client.get('/api/v1/agenda/appointments').json()['items'], [])

    def test_two_visitors_and_admin_compete_for_the_same_resource(self):
        offer = self.get_offer()
        first, _ = self.verify(offer, 'first@example.test')
        second, _ = self.verify(offer, 'second@example.test')
        def confirm(proof):
            client = TestClient(accounts.app, base_url=accounts.ORIGIN, headers={'Origin': accounts.ORIGIN})
            return client.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(confirm, [first, second]))
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(len(self.client.get('/api/v1/agenda/appointments').json()['items']), 1)

    def test_crm_match_requires_explicit_verified_policy_and_preserves_human_name(self):
        changed = self.client.patch('/api/v1/clientes/' + str(self.person['id']),
            json={'email': 'known@example.test', 'expected_version': self.person['versao']})
        self.assertEqual(changed.status_code, 200, changed.text)
        offer = self.get_offer()
        proof, _ = self.verify(offer, 'known@example.test')
        payload = {'offer': offer, 'proof': proof, 'confirmed': True}
        self.assertEqual(self.public.post(self.path + '/confirm', json=payload).status_code, 409)
        self.publish(allow_verified_email_match=True)
        offer = self.get_offer()
        proof, _ = self.verify(offer, 'known@example.test')
        booked = self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
        self.assertEqual(booked.status_code, 200, booked.text)
        self.assertEqual(self.client.get('/api/v1/clientes/' + str(self.person['id'])).json()['nome'], self.person['nome'])

    def test_durable_attempt_limits_and_smtp_uncertainty_never_create_booking(self):
        offer = self.get_offer()
        with patch('public_booking.send_code', side_effect=public.HTTPException(503, 'Envio incerto.')):
            result = self.public.post(self.path + '/verification/request', json={'offer': offer, 'name': 'Teste', 'email': 'uncertain@example.test'})
        self.assertEqual(result.status_code, 503)
        proof, challenge = self.verify(offer)
        for _ in range(8):
            self.public.post(self.path + '/verification/confirm', json={'challenge': challenge, 'code': '999999'})
        fresh = TestClient(accounts.app, base_url=accounts.ORIGIN, headers={'Origin': accounts.ORIGIN})
        blocked = fresh.post(self.path + '/verification/confirm', json={'challenge': challenge, 'code': '999999'})
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(self.client.get('/api/v1/agenda/appointments').json()['items'], [])

    def test_admin_publication_and_visitor_origin_boundaries(self):
        stranger = self.public.put('/api/v1/agenda/public-booking', json={})
        self.assertEqual(stranger.status_code, 401)
        result = self.public.post(self.path + '/resources', headers={'Origin': 'https://foreign.example.test'}, json={'service': 'opaque'})
        self.assertEqual(result.status_code, 403)
        self.assertNotIn('workspace_id', self.public.get(self.path).json())

    def test_bella_and_brilho_book_independently_with_the_same_verified_email(self):
        other = self.register('brilho-owner@example.test')
        other_workspace = other.identity['negocio']['id']
        with psycopg.connect(accounts.DB) as conn:
            conn.execute('UPDATE socialmei.workspaces SET nome=%s WHERE id=%s', ('Bella Store', self.workspace))
            conn.execute('UPDATE socialmei.workspaces SET nome=%s WHERE id=%s', ('Brilho Limpeza', other_workspace))
            slug = conn.execute('SELECT slug FROM socialmei.workspaces WHERE id=%s', (other_workspace,)).fetchone()[0]
        service = self.post('/api/v1/produtos', {'nome': 'Limpeza de teste', 'tipo': 'Serviço', 'preco': 150, 'duracao_minutos': 30}, client=other)
        resource = self.post('/api/v1/agenda/resources', {'operation_id': str(uuid4()), 'nome': 'Equipe Brilho fictícia'}, client=other)
        policy = self.client.get('/api/v1/agenda/channel-booking').json()['policy']
        self.assertEqual(other.put('/api/v1/agenda/channel-booking', json={'expected_revision': 0, 'policy': policy}).status_code, 200)
        publication = other.put('/api/v1/agenda/public-booking', json={'expected_revision': 0, 'policy': {
            'enabled': True, 'service_ids': [service['id']], 'resource_ids': [resource['id']], 'allow_new_customers': True}})
        self.assertEqual(publication.status_code, 200, publication.text)
        first_path = self.path
        first_offer = self.get_offer()
        first_proof, _ = self.verify(first_offer, 'shared@example.test')
        self.path = '/api/v1/public/booking/' + slug
        second_path = self.path
        second_offer = self.get_offer()
        second_proof, _ = self.verify(second_offer, 'shared@example.test')
        wrong = self.public.post(first_path + '/confirm', json={'offer': second_offer, 'proof': second_proof, 'confirmed': True})
        self.assertEqual(wrong.status_code, 409)
        def submit(packet):
            path, offer, proof = packet
            visitor = TestClient(accounts.app, base_url=accounts.ORIGIN, headers={'Origin': accounts.ORIGIN})
            return visitor.post(path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [(first_path, first_offer, first_proof), (second_path, second_offer, second_proof)]))
        self.assertEqual([r.status_code for r in results], [200, 200], [r.text for r in results])
        bella = self.client.get('/api/v1/agenda/appointments').json()['items']
        brilho = other.get('/api/v1/agenda/appointments').json()['items']
        self.assertEqual(len(bella), 1)
        self.assertEqual(len(brilho), 1)
        self.assertNotEqual(bella[0]['cliente_id'], brilho[0]['cliente_id'])
        self.assertEqual(brilho[0]['service_name'], 'Limpeza de teste')

    def test_inactive_or_ambiguous_crm_contacts_are_never_merged_or_duplicated(self):
        self.publish(allow_verified_email_match=True)
        result = self.client.patch('/api/v1/clientes/' + str(self.person['id']),
            json={'email': 'inactive@example.test', 'status': 'Inativo', 'expected_version': self.person['versao']})
        self.assertEqual(result.status_code, 200)
        offer = self.get_offer()
        proof, _ = self.verify(offer, 'inactive@example.test')
        result = self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(len(self.client.get('/api/v1/clientes').json()), 1)

        self.post('/api/v1/clientes', {'nome': 'Contato duplicado fictício', 'email': 'ambiguous@example.test'})
        self.post('/api/v1/clientes', {'nome': 'Outro contato fictício', 'email': 'ambiguous@example.test'})
        proof, _ = self.verify(offer, 'ambiguous@example.test')
        result = self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(len(self.client.get('/api/v1/clientes').json()), 3)

    def test_publication_rejects_foreign_identifiers_and_stale_revision(self):
        other = self.register('foreign-services@example.test')
        service = self.post('/api/v1/produtos', {'nome': 'Estrangeiro', 'tipo': 'Serviço', 'preco': 10, 'duracao_minutos': 30}, client=other)
        config = self.client.get('/api/v1/agenda/public-booking').json()
        invalid = self.client.put('/api/v1/agenda/public-booking', json={'expected_revision': config['revision'], 'policy': {
            **config['policy'], 'service_ids': [service['id']]}})
        self.assertEqual(invalid.status_code, 422)
        stale = self.client.put('/api/v1/agenda/public-booking', json={'expected_revision': 0, 'policy': config['policy']})
        self.assertEqual(stale.status_code, 409)

    def test_public_and_administrative_writers_share_the_same_conflict_lock(self):
        offer = self.get_offer()
        proof, _ = self.verify(offer)
        start = public.decode(offer, 'offer')['start']
        def admin():
            return self.client.post('/api/v1/agenda/appointments', json={
                'operation_id': str(uuid4()), 'cliente_id': self.person['id'],
                'servico_id': self.service['id'], 'resource_id': self.resource['id'],
                'scheduled_for': start}).status_code
        def guest():
            return self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = pool.submit(admin), pool.submit(guest)
            statuses = [a.result(), b.result()]
        self.assertEqual(sum(status in (200, 201) for status in statuses), 1, statuses)
        self.assertIn(409, statuses)
        self.assertEqual(len(self.client.get('/api/v1/agenda/appointments').json()['items']), 1)

    def test_expired_offer_resource_changes_and_out_of_horizon_fail_closed(self):
        offer = self.get_offer()
        proof, _ = self.verify(offer)
        original = public.decode(offer, 'offer')
        changed = self.client.patch('/api/v1/agenda/resources/' + self.resource['id'],
            json={'expected_revision': self.resource['revision'], 'nome': 'Nome alterado'})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True}).status_code, 409)
        catalog = self.public.get(self.path).json()
        service = catalog['services'][0]['reference']
        resource = self.public.post(self.path + '/resources', json={'service': service}).json()['items'][0]['reference']
        response = self.public.post(self.path + '/slots', json={'service': service, 'resource': resource, 'day': '9999-12-31'})
        self.assertEqual(response.status_code, 422)
        expired_offer = public.opaque('offer', {k: v for k, v in original.items() if k not in ('purpose', 'expires')}, -1)
        result = self.public.post(self.path + '/verification/request', json={'offer': expired_offer, 'name': 'Teste', 'email': 'expired@example.test'})
        self.assertEqual(result.status_code, 409)

    def test_persisted_receipt_survives_proof_expiry_and_reflects_cancellation(self):
        offer = self.get_offer()
        proof, _ = self.verify(offer)
        result = self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': proof, 'confirmed': True})
        self.assertEqual(result.status_code, 200)
        data = public.decode(proof, 'proof')
        expired_proof = public.opaque('proof', {k: v for k, v in data.items() if k not in ('purpose', 'expires')}, -1)
        row = self.client.get('/api/v1/agenda/appointments').json()['items'][0]
        cancel = self.client.patch('/api/v1/agenda/appointments/' + row['id'],
            json={'expected_revision': row['revision'], 'status': 'cancelled'})
        self.assertEqual(cancel.status_code, 200)
        replay = self.public.post(self.path + '/confirm', json={'offer': offer, 'proof': expired_proof, 'confirmed': True})
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()['status'], 'cancelled')
        self.assertEqual(replay.json()['reference'], result.json()['reference'])

    def test_dst_slot_end_matches_elapsed_service_duration(self):
        current = self.client.get('/api/v1/produtos/' + str(self.service['id'])).json()
        self.assertEqual(self.client.patch('/api/v1/produtos/' + str(self.service['id']),
            json={'expected_version': current['versao'], 'duracao_minutos': 180}).status_code, 200)
        config = self.client.get('/api/v1/agenda/channel-booking').json()
        changed = self.client.put('/api/v1/agenda/channel-booking', json={
            'expected_revision': config['revision'], 'policy': {'enabled': True, 'timezone': 'America/New_York',
            'lead_minutes': 0, 'hours': [{'weekday': 6, 'opens': '00:00', 'closes': '06:00'}]}})
        self.assertEqual(changed.status_code, 200)
        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2027, 3, 13, 12, tzinfo=timezone.utc).astimezone(tz or timezone.utc)
        self.day = '2027-03-14'
        with patch('public_booking.datetime', Frozen):
            row = self.get_slots()['items'][0]
        start, end = datetime.fromisoformat(row['scheduled_for']), datetime.fromisoformat(row['ends_at'])
        self.assertEqual((end - start).total_seconds(), 180 * 60)
        self.assertEqual(end.hour, 4)


if __name__ == '__main__':
    unittest.main()
