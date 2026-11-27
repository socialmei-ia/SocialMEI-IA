from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import psycopg

import test_instagram_persistent_oauth as oauth
from instagram_meta_adapter import ProviderError
from instagram_publishing import InstagramPublishingService, service

BASE = "/api/v1/instagram/publishing/scheduled"


@unittest.skipUnless(oauth.DB, "Disposable PostgreSQL not configured")
class ScheduledImageTests(unittest.TestCase):
    setUpClass = classmethod(oauth.PersistentTests.setUpClass.__func__)
    post = oauth.PersistentTests.post
    begin = oauth.PersistentTests.begin
    complete = oauth.PersistentTests.complete
    connection = oauth.PersistentTests.connection
    # Reuse the disposable database, login and OAuth fixtures only.
    def setUp(self):
        oauth.PersistentTests.setUp(self)
        self.flags = patch.dict("os.environ", {
            "SOCIALMEI_INSTAGRAM_SCHEDULE_ENABLED": "YES",
            "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED": "true",
        })
        self.flags.start()
        self.addCleanup(self.flags.stop)
        self.assertEqual(self.complete(self.begin()).status_code, 200)
        self.account = self.connection()[0]
        with psycopg.connect(oauth.DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_connections SET scopes=array_append(scopes,%s) WHERE id=%s",
                ("instagram_business_content_publish", self.account),
            )
        self.provider = Mock(_version="v22.0")
        self.provider._request.side_effect = [
            {"id": "100"}, {"status_code": "FINISHED"}, {"id": "200"},
        ]
        self.publisher = InstagramPublishingService(self.provider, self.service.vault)
        oauth.app.dependency_overrides[service] = lambda: self.publisher
        self.addCleanup(oauth.app.dependency_overrides.pop, service, None)
        self.addCleanup(self.delete_publications)

    def delete_publications(self):
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("DELETE FROM socialmei.ig_meta_publications WHERE workspace_id=%s", (self.identities[0]["workspace_id"],))

    def tearDown(self):
        self.delete_publications()
        oauth.PersistentTests.tearDown(self)

    def send(self, path, method, payload):
        response = self.client.request(method, BASE + path, json=payload, headers=self.headers)
        return response

    def payload(self):
        return {
            "request_id": str(uuid4()),
            "connection_id": str(self.account),
            "image_url": "https://cdn.example.org/test.jpg",
            "caption": "Publicação sintética",
            "timezone": "UTC",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(timespec="seconds"),
        }

    def create(self, payload=None):
        response = self.send("", "POST", payload or self.payload())
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def make_due(self, publication_id):
        with psycopg.connect(oauth.DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_publications SET scheduled_at=NOW()-INTERVAL '1 minute' WHERE id=%s",
                (publication_id,),
            )

    def test_schedule_claim_provider_receipt_and_replay(self):
        payload = self.payload()
        row = self.create(payload)
        self.assertEqual(self.create(payload), row)
        self.assertFalse(self.publisher.process_scheduled_once())
        self.assertEqual(self.provider._request.call_count, 0)
        self.make_due(row["id"])
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda _: self.publisher.process_scheduled_once(), range(2)))
        self.publisher.process_scheduled_once()
        self.assertFalse(self.publisher.process_scheduled_once())
        stored = self.client.get(BASE).json()["items"][0]
        self.assertEqual((stored["status"], stored["media_id"]), ("published", "200"))
        self.assertEqual([args.args[0].method for args in self.provider._request.call_args_list], ["POST", "GET", "POST"])
        self.assertEqual(self.create(payload)["id"], row["id"])

    def test_cancel_and_reschedule_are_scoped_and_versioned(self):
        row = self.create()
        path = "/" + row["id"]
        payload = self.payload()
        date = {field: payload[field] for field in ("scheduled_at", "timezone")}
        self.identity = self.identities[1]
        self.client.cookies.set(oauth.COOKIE, "c" * 64)
        self.headers = {"Origin": oauth.ORIGIN, "X-SocialMEI-CSRF": oauth.csrf("c" * 64)}
        self.assertEqual(self.client.get(BASE).json(), {"items": []})
        self.assertEqual(self.send(path, "PATCH", {**date, "revision": 1}).status_code, 404)
        self.identity = self.identities[0]
        self.client.cookies.set(oauth.COOKIE, oauth.TOKEN)
        self.headers = {"Origin": oauth.ORIGIN, "X-SocialMEI-CSRF": oauth.csrf(oauth.TOKEN)}
        updated = self.send(path, "PATCH", {**date, "revision": 1})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["revision"], 2)
        self.assertEqual(self.send(path + "/cancel", "POST", {"revision": 1}).status_code, 409)
        cancelled = self.send(path + "/cancel", "POST", {"revision": 2})
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.make_due(row["id"])
        self.assertFalse(self.publisher.process_scheduled_once())
        self.provider._request.assert_not_called()

    def test_uncertain_result_never_redispatches(self):
        row = self.create()
        self.make_due(row["id"])
        self.provider._request.side_effect = ProviderError(outcome_unknown=True)
        self.assertTrue(self.publisher.process_scheduled_once())
        self.assertFalse(self.publisher.process_scheduled_once())
        self.assertEqual(self.client.get(BASE).json()["items"][0]["status"], "uncertain")
        self.provider._request.assert_called_once()

    def test_downgrade_blocks_send(self):
        row = self.create()
        self.make_due(row["id"])
        with psycopg.connect(oauth.DB) as conn:
            conn.execute("UPDATE socialmei.auth_credenciais SET ativo=FALSE WHERE user_id=%s", (self.identity["id"],))
        self.assertTrue(self.publisher.process_scheduled_once())
        self.provider._request.assert_not_called()
        with psycopg.connect(oauth.DB) as conn:
            status = conn.execute("SELECT status FROM socialmei.ig_meta_publications WHERE id=%s", (row["id"],)).fetchone()
        self.assertEqual(status, ("failed",))


    def test_stale_claim_and_late_receipt_keep_uncertain_state(self):
        row = self.create()
        with psycopg.connect(oauth.DB) as conn:
            conn.execute(
                "UPDATE socialmei.ig_meta_publications SET status='publishing',updated_at=NOW()-INTERVAL '7 minutes' WHERE id=%s",
                (row["id"],),
            )
        self.assertTrue(self.publisher.process_scheduled_once())
        self.assertFalse(self.publisher.process_scheduled_once())
        self.provider._request.assert_not_called()
        self.assertIsNone(self.publisher._result(row["id"], "published", None, "500", expected="publishing"))
        self.assertEqual(self.client.get(BASE).json()["items"][0]["status"], "uncertain")

    def test_explicit_provider_rejection_is_visible_and_not_retried(self):
        row = self.create()
        self.make_due(row["id"])
        self.provider._request.side_effect = ProviderError(status_code=403)
        self.assertTrue(self.publisher.process_scheduled_once())
        self.assertFalse(self.publisher.process_scheduled_once())
        stored = self.client.get(BASE).json()["items"][0]
        self.assertEqual((stored["status"], stored["error_code"]), ("failed", "provider_rejected"))
        self.provider._request.assert_called_once()
