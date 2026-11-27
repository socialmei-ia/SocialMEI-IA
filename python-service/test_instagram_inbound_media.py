import socket
import unittest
from unittest.mock import patch

import instagram_inbound_media as media


class SecurityTests(unittest.TestCase):
    def test_url_allowlist_is_exact_and_https_only(self):
        for url in (None, 'http://x.fbcdn.net/a', 'https://x.fbcdn.net.evil.test/a',
                    'https://127.0.0.1/a', 'https://x.fbcdn.net:8080/a',
                    'https://x.fbcdn.net@localhost/a', 'https://x.fbcdn.net/a#x'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                media.cdn_url(url)
        self.assertEqual(media.cdn_url('https://x.fbcdn.net/a?n=1').hostname, 'x.fbcdn.net')

    def test_private_mixed_dns_answers_fail_closed(self):
        def address(ip):
            return (socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
        with patch.object(socket, 'getaddrinfo', return_value=[address('8.8.8.8'), address('169.254.169.254')]):
            with self.assertRaises(ValueError):
                media.public_ip('x.fbcdn.net')

    def test_image_and_audio_require_matching_content(self):
        self.assertFalse(media.matches_type(b'<html>', 'image/jpeg'))
        self.assertFalse(media.matches_type(b'%PDF-1.4', 'audio/ogg'))
        self.assertTrue(media.matches_type(b'RIFF' + bytes(4) + b'WAVEfmt ', 'audio/wav'))

    def test_download_refuses_redirects_and_truncated_bodies(self):
        from unittest.mock import MagicMock

        url = 'https://x.fbcdn.net/audio.ogg?sig=fixture'
        connection = MagicMock()
        response = connection.getresponse.return_value.__enter__.return_value
        headers = {'Content-Type': 'audio/ogg', 'Content-Length': '30'}
        response.getheader.side_effect = lambda name, default=None: headers.get(name, default)
        with patch.object(media, 'PinnedHTTPS', return_value=connection):
            response.status = 302
            with self.assertRaises(ValueError):
                media.download(url, 'audio')
            self.assertEqual(connection.request.call_count, 1)
            response.status = 200
            response.read1.side_effect = [b'OggSshort', b'']
            with self.assertRaises(ValueError):
                media.download(url, 'audio')
            self.assertEqual(connection.request.call_count, 2)
