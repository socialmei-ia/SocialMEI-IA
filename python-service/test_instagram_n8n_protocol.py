"""Handoff protocol: only opaque internal IDs, signed bytes and no transport."""
import json
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from instagram_n8n_protocol import build_job, serialize, sign, verify, SCHEMA


class N8nProtocolTests(unittest.TestCase):
    def job(self, kind="feed", count=1, mode="single", scheduled_for=None):
        return build_job(
            publication_id=uuid4(),
            operation_id=uuid4(),
            workspace_id=42,
            linked_account_id=uuid4(),
            kind=kind,
            feed_mode=mode,
            caption="Oferta de teste! #socialmei",
            media=[
                {"asset_id": str(uuid4()), "mime": "video/mp4" if kind == "reel" else "image/jpeg"}
                for _ in range(count)
            ],
            scheduled_for=scheduled_for,
        )

    def test_feed_carousel_separate_story_and_reel(self):
        self.assertEqual(self.job()["feed_mode"], "single")
        for mode in ("carousel", "separate"):
            job = self.job(count=3, mode=mode)
            self.assertEqual(len(job["media"]), 3)
            self.assertEqual(job["feed_mode"], mode)
        self.assertIsNone(self.job("story", mode=None)["feed_mode"])
        self.assertEqual(self.job("reel", mode=None)["format"], "reel")
        with self.assertRaises(ValueError):
            self.job(count=2, mode="single")
        with self.assertRaises(ValueError):
            self.job("story", count=2, mode=None)
        with self.assertRaises(ValueError):
            self.job("reel")

    def test_account_is_opaque_and_payload_has_no_meta_account_or_credentials(self):
        job = self.job()
        self.assertEqual(job["schema"], SCHEMA)
        self.assertEqual(set(job), {
            "schema", "publication_id", "operation_id", "workspace_id",
            "linked_account_id", "format", "feed_mode", "caption", "media", "scheduled_for",
        })
        self.assertNotIn("instagram_user_id", job)
        self.assertNotIn("access_token", job)
        self.assertNotIn("media_url", job)
        self.assertNotIn("credentials", serialize(job).decode())

    def test_validates_timestamp_and_media(self):
        scheduled = datetime.now(timezone.utc) + timedelta(days=2)
        self.assertTrue(self.job(scheduled_for=scheduled)["scheduled_for"].endswith("Z"))
        with self.assertRaises(ValueError):
            self.job(scheduled_for=datetime.now(timezone.utc) - timedelta(days=1))
        with self.assertRaises(ValueError):
            self.job(scheduled_for=datetime.now().replace(tzinfo=None))
        sample = self.job()
        sample["media"][0]["mime"] = "image/svg+xml"
        with self.assertRaises(ValueError):
            build_job(
                publication_id=sample["publication_id"],
                operation_id=sample["operation_id"], workspace_id=42,
                linked_account_id=sample["linked_account_id"],
                kind="feed", feed_mode="single", caption="",
                media=sample["media"],
            )

    def test_hmac_covers_body_and_timestamp(self):
        secret = b"test-only-key-" + b"x" * 36
        body = serialize(self.job())
        headers = sign(secret, body, timestamp=1_780_000_000)
        self.assertTrue(verify(secret, body, headers, now=1_780_000_001))
        self.assertFalse(verify(secret, body + b" ", headers, now=1_780_000_001))
        self.assertFalse(verify(secret, body, headers, now=1_780_000_500))
        self.assertFalse(verify(secret, body, {**headers, "X-SocialMEI-Signature": "sha256=" + "0" * 64}, now=1_780_000_000))
        with self.assertRaises(ValueError):
            sign(b"short", body)
