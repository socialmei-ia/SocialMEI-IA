"""Account media uses fake Meta responses and disposable PostgreSQL only."""
import json
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import httpx
import psycopg
from fastapi.testclient import TestClient

from app import app
from instagram_account_media import media_item, media_service, provider_page, public_url
from instagram_http_transport import ACCOUNT_MEDIA_FIELDS, InstagramHTTPTransport
from instagram_meta_adapter import ProviderError, ProviderRequest, ProviderResponse
import test_instagram_persistent_oauth as oauth

PATH = '/api/v1/instagram/media'


def image(**updates):
    return {'id': '123456', 'media_type': 'IMAGE', 'caption': 'Publicação de teste',
            'media_url': 'https://scontent.cdninstagram.com/test.jpg?oh=signature&oe=123',
            'permalink': 'https://www.instagram.com/p/Abc_123/',
            'timestamp': '2026-10-31T12:00:00+0000', **updates}


class MediaTransport(oauth.FakeTransport):
    def __init__(self):
        super().__init__()
        self.account = str(uuid4().int)
        self.response = {'data': [image()]}
        self.status = 200

    def __call__(self, request):
        if request.url.endswith('/media'):
            self.calls.append(request)
            if self.fail:
                raise RuntimeError('private-provider-token')
            return ProviderResponse(self.status, json.dumps(self.response).encode())
        return super().__call__(request)


class AccountMediaContracts(unittest.TestCase):
    def test_dependency_reuses_oauth_runtime_without_sending_or_publishing(self):
        marker, request = object(), object()
        with patch('instagram_runtime.runtime_service', return_value=marker) as runtime:
            self.assertIs(media_service(request), marker)
        runtime.assert_called_once_with(request, 'oauth')

    def test_unconfigured_feature_is_closed_without_provider_or_database(self):
        with patch.dict(os.environ, {**oauth.ENV, 'SOCIALMEI_INSTAGRAM_RUNTIME_MODE': 'disabled'}), patch(
            'account_auth.session_identity', return_value={'id': 1, 'workspace_id': 1, 'role': 'owner'}
        ), patch('instagram_account_media.connect', side_effect=AssertionError('no database')):
            client = TestClient(app, base_url=oauth.ORIGIN)
            client.cookies.set(oauth.COOKIE, oauth.TOKEN)
            response = client.get(PATH)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_only_public_meta_cdn_and_instagram_permalink_urls_survive(self):
        for url in ('https://scontent.cdninstagram.com/image.jpg?oh=signature',
                    'https://instagram.frec25-1.fna.fbcdn.net/image.jpg'):
            self.assertEqual(public_url(url), url)
        link = 'https://www.instagram.com/reel/Abc_123/'
        self.assertEqual(public_url(link, permalink=True), link)
        for url in ('javascript:alert(1)', 'http://scontent.cdninstagram.com/photo.jpg',
                    'https://evilcdninstagram.com/photo.jpg', 'https://cdninstagram.com.evil.example/photo.jpg',
                    'https://evil.com\\.fbcdn.net/photo.jpg', 'https://evil%5c.fbcdn.net/photo.jpg',
                    'https://127.0.0.1/photo.jpg', 'https://@scontent.cdninstagram.com/photo.jpg',
                    'https://secret@scontent.cdninstagram.com/photo.jpg',
                    'https://scontent.cdninstagram.com/photo.jpg#private',
                    'https://scontent.cdninstagram.com/photo.jpg?access_token=private',
                    'https://scontent.cdninstagram.com/photo.jpg?%61ccess_token=private',
                    'https://scontent.cdninstagram.com:444/photo.jpg'):
            with self.subTest(url=url):
                self.assertIsNone(public_url(url))
        self.assertIsNone(public_url('https://evil.example/p/Abc/', permalink=True))
        self.assertIsNone(public_url('https://www.instagram.com/p/Abc/?token=private', permalink=True))

    def test_optional_caption_metadata_and_unsafe_urls_remain_honest(self):
        item = media_item({'id': '123', 'media_type': 'VIDEO', 'media_url': 'javascript:bad'})
        self.assertEqual(item['caption'], '')
        self.assertIsNone(item['timestamp'])
        self.assertIsNone(item['media_url'])
        self.assertIsNone(item['thumbnail_url'])
        self.assertIsNone(item['permalink'])
        self.assertEqual(len(media_item(image(caption='á' * 3000))['caption']), 2200)
        self.assertEqual(media_item(image())['timestamp'], '2026-10-31T12:00:00+00:00')
        for update in ({'id': 'not-provider-id'}, {'media_type': {}}, {'media_type': 'UNKNOWN'},
                       {'caption': None}, {'caption': '\ud800'}, {'timestamp': 'yesterday'},
                       {'timestamp': '2026-10-31T12:00:00'}):
            with self.subTest(update=repr(update)), self.assertRaises(ProviderError):
                media_item(image(**update))

    def test_pagination_never_returns_or_follows_the_provider_next_url(self):
        transport = MediaTransport()
        transport.response = {'data': [image()], 'paging': {
            'next': 'https://evil.example/?access_token=private-provider-token',
            'cursors': {'after': 'Abc+/Def_123-=='},
        }}
        service = oauth.service(transport)
        result = provider_page(service.adapter, 'synthetic-long-token', transport.account, 'previousCursor')
        self.assertEqual(result['next_cursor'], 'Abc+/Def_123-==')
        self.assertEqual(len(transport.calls), 1)
        request = transport.calls[0]
        self.assertEqual(request.url, 'https://graph.instagram.com/v99.0/' + transport.account + '/media')
        self.assertEqual(dict(request.params), {'fields': ACCOUNT_MEDIA_FIELDS, 'limit': '5', 'after': 'previousCursor'})
        self.assertEqual(dict(request.headers), {'Authorization': 'Bearer synthetic-long-token'})
        self.assertNotIn('private-provider-token', json.dumps(result))

    def test_invalid_oversized_or_duplicate_provider_page_fails_closed(self):
        transport = MediaTransport()
        service = oauth.service(transport)
        for response in ({}, {'data': {}}, {'data': [image()] * 2},
                         {'data': [image(id=str(n)) for n in range(6)]}):
            transport.response = response
            with self.subTest(response=response), self.assertRaises(ProviderError):
                provider_page(service.adapter, 'synthetic-token', transport.account, None)
        transport.response = {'data': [image(caption='a' * 33000)]}
        with self.assertRaises(ProviderError):
            provider_page(service.adapter, 'synthetic-token', transport.account, None)

    def test_http_transport_allows_only_fixed_read_contract_without_send_flags(self):
        calls = []
        def factory(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(lambda request: (
                calls.append(request) or httpx.Response(200, json={'data': []})
            )), **kwargs)
        transport = InstagramHTTPTransport(client_factory=factory)
        valid = {'fields': ACCOUNT_MEDIA_FIELDS, 'limit': '5', 'after': 'Abc+/Def_123-=='}
        result = transport(ProviderRequest('GET', 'https://graph.instagram.com/v26.0/123/media', params=valid))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(calls), 1)
        for method, url, params in (
            ('POST', 'https://graph.instagram.com/v26.0/123/media', valid),
            ('GET', 'https://graph.instagram.com/v26.0/other/media', valid),
            ('GET', 'https://evil.example/v26.0/123/media', valid),
            ('GET', 'https://graph.instagram.com/v26.0/123/media', {**valid, 'limit': '25'}),
            ('GET', 'https://graph.instagram.com/v26.0/123/media', {**valid, 'fields': 'access_token'}),
            ('GET', 'https://graph.instagram.com/v26.0/123/media', {**valid, 'extra': 'unsupported'}),
            ('GET', 'https://graph.instagram.com/v26.0/123/media', {**valid, 'after': 'http://evil.example'}),
        ):
            with self.subTest(method=method, url=url, params=params), self.assertRaises(ProviderError):
                transport(ProviderRequest(method, url, params=params))
        self.assertEqual(len(calls), 1)


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Disposable PostgreSQL required')
class AccountMediaDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(oauth.PersistentTests.setUpClass.__func__)
    tearDown = oauth.PersistentTests.tearDown
    post = oauth.PersistentTests.post
    begin = oauth.PersistentTests.begin
    complete = oauth.PersistentTests.complete
    connection = oauth.PersistentTests.connection

    def setUp(self):
        oauth.PersistentTests.setUp(self)
        self.transport = MediaTransport()
        self.service = oauth.service(self.transport)
        app.dependency_overrides[media_service] = lambda: self.service
        self.addCleanup(app.dependency_overrides.pop, media_service, None)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.transport.calls.clear()

    def database(self):
        return psycopg.connect(os.environ['TEST_DATABASE_URL'])

    def test_connected_account_returns_real_provider_metadata_without_mutating_connection(self):
        previous = self.connection()
        with patch.dict(os.environ, {'SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED': 'false',
                                    'SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED': 'false'}):
            response = self.client.get(PATH, params={'account_id': 'browser-must-not-choose'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['items'][0]['id'], '123456')
        self.assertIsNone(response.json()['next_cursor'])
        self.assertEqual(self.connection(), previous)
        self.assertEqual(len(self.transport.calls), 1)
        self.assertTrue(self.transport.calls[0].url.endswith('/' + self.transport.account + '/media'))
        self.assertEqual(self.transport.calls[0].method, 'GET')
        self.assertNotIn('synthetic-long-token', response.text)
        self.assertNotIn(previous[2], response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')

    def test_other_workspace_and_missing_basic_permission_do_not_call_provider(self):
        self.identity = self.identities[1]
        self.client.cookies.set(oauth.COOKIE, 'c' * 64)
        self.assertEqual(self.client.get(PATH).status_code, 409)
        self.identity = self.identities[0]
        self.client.cookies.set(oauth.COOKIE, oauth.TOKEN)
        with self.database() as conn:
            conn.execute('UPDATE socialmei.ig_meta_connections SET scopes=%s WHERE workspace_id=%s',
                         (['instagram_business_manage_messages'], self.identity['workspace_id']))
        self.assertEqual(self.client.get(PATH).status_code, 409)
        self.assertEqual(self.transport.calls, [])

    def test_viewer_can_read_but_report_only_role_cannot(self):
        with self.database() as conn:
            conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s',
                         ('viewer', self.identity['id']))
        self.identity = {**self.identity, 'role': 'viewer'}
        self.assertEqual(self.client.get(PATH).status_code, 200)
        self.transport.calls.clear()
        with self.database() as conn:
            conn.execute('UPDATE socialmei.workspace_members SET role=%s WHERE user_id=%s',
                         ('report_viewer', self.identity['id']))
        self.identity = {**self.identity, 'role': 'report_viewer'}
        self.assertEqual(self.client.get(PATH).status_code, 403)
        self.assertEqual(self.transport.calls, [])

    def test_expired_or_missing_credential_and_bad_cursor_never_call_provider(self):
        self.assertEqual(self.client.get(PATH, params={'after': 'http://evil.example'}).status_code, 422)
        with self.database() as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW()-INTERVAL '60 days',"
                         "expires_at=NOW()-INTERVAL '1 day' WHERE workspace_id=%s", (self.identity['workspace_id'],))
        self.assertEqual(self.client.get(PATH).status_code, 409)
        with self.database() as conn:
            conn.execute("UPDATE socialmei.ig_meta_connections SET issued_at=NOW(),expires_at=NOW()+INTERVAL '1 day',"
                         'encrypted_token=%s WHERE workspace_id=%s', ('malformed-private-token', self.identity['workspace_id']))
        response = self.client.get(PATH)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('malformed-private-token', response.text)
        self.assertEqual(self.transport.calls, [])

    def test_provider_and_database_failure_preserve_connection_and_hide_private_details(self):
        previous = self.connection()
        self.transport.fail = True
        response = self.client.get(PATH)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-provider', response.text)
        self.assertEqual(self.connection(), previous)
        self.transport.calls.clear()
        with patch('instagram_account_media.connect', side_effect=psycopg.OperationalError('private-dsn-password')):
            response = self.client.get(PATH)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-dsn', response.text)
        self.assertEqual(self.transport.calls, [])
