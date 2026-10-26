"""Live Instagram publication policy tests: no real network or secrets."""
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-service"))

from instagram_publishing import ImagePost, image_url
from instagram_http_transport import InstagramHTTPTransport
from instagram_meta_adapter import ProviderError, ProviderRequest
from instagram_runtime import InstagramRuntime


class ImagePublishingTests(unittest.TestCase):
    def test_valid_public_image(self):
        payload = ImagePost(
            request_id=uuid4(), image_url="https://cdn.example.org/photo.jpg", caption="Olá"
        )
        self.assertEqual(payload.caption, "Olá")

    def test_block_private_or_ambiguous_urls(self):
        values = [
            "http://cdn.example.org/photo.jpg",
            "https://localhost/photo.jpg",
            "https://127.0.0.1/photo.jpg",
            "https://internal.local/photo.jpg",
            "https://cdn.example.org/photo.jpg?token=secret",
            "https://user:secret@cdn.example.org/photo.jpg",
            "https://cdn.example.org:444/photo.jpg",
            "https://cdn.example.org/photo.jpg#fragment",
        ]
        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    image_url(value)

    def test_invalid_captions_and_duplicate_fields(self):
        with self.assertRaises(ValidationError):
            ImagePost(request_id=uuid4(), image_url="https://cdn.example.org/photo.jpg", caption=" ")
        with self.assertRaises(ValidationError):
            ImagePost(request_id=uuid4(), image_url="https://cdn.example.org/photo.jpg", caption="OK", unexpected=True)

    def test_publishing_off_by_default(self):
        self.assertIsNone(InstagramRuntime().publish)
        denied = InstagramHTTPTransport()
        for edge in ["media", "media_publish"]:
            with self.subTest(edge=edge):
                with self.assertRaises(ProviderError):
                    denied._allowed(ProviderRequest("POST", f"https://graph.instagram.com/v26.0/12345/{edge}"))

    def test_allow_exact_meta_media_edges_only_when_explicit(self):
        transport = InstagramHTTPTransport(allow_publishing=True)
        for edge in ["media", "media_publish"]:
            transport._allowed(ProviderRequest("POST", f"https://graph.instagram.com/v26.0/12345/{edge}"))
        for url in [
            "https://graph.instagram.com/v26.0/12345/messages",
            "https://graph.instagram.com/v26.0/12345/media/other",
            "https://graph.instagram.com/v26.0/12345/media_publish?token=wrong",
            "https://graph.facebook.com/v26.0/12345/media",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(ProviderError):
                    transport._allowed(ProviderRequest("POST", url))

    def test_status_read_allowlist_requires_exact_fields_and_flag(self):
        read = ProviderRequest('GET','https://graph.instagram.com/v22.0/12345',params={'fields':'status_code'})
        with self.assertRaises(ProviderError):
            InstagramHTTPTransport()._allowed(read)
        InstagramHTTPTransport(allow_publishing=True)._allowed(read)
        for params in ({'fields':'messages'}, {}, {'fields':'status_code','access_token':'hidden'}):
            with self.assertRaises(ProviderError):
                InstagramHTTPTransport(allow_publishing=True)._allowed(ProviderRequest('GET',read.url,params=params))
