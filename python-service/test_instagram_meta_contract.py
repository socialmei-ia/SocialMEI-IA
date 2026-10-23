"""Contract tests for Instagram Login: no Meta app, HTTP calls or production data."""
import hashlib
import hmac
import json
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from instagram_meta_contract import (
    MAX_ENTRIES,
    MAX_EVENTS,
    MetaContractError,
    authorization_url_from_embed,
    inspect_verified_webhook,
    verify_webhook_challenge,
    verify_webhook_signature,
)

SECRET = "dummy-meta-app-secret-for-unit-tests-only-123"
TOKEN = "dummy-webhook-verification-value-123456"
CALLBACK = "https://socialmei.example/api/v1/integrations/instagram/oauth/callback"
SCOPES = ("instagram_business_basic", "instagram_business_manage_messages")
STATE = "f" * 45


def embed(**changes):
    data = {
        "client_id": "1234567890",
        "redirect_uri": CALLBACK,
        "scope": ",".join(SCOPES),
        "response_type": "code",
    }
    data.update(changes)
    return "https://www.instagram.com/oauth/authorize?" + urlencode(data)


def signed(payload):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return body, "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def event():
    return {
        "object": "instagram",
        "entry": [{
            "id": "17841400000001",
            "time": 1792500000,
            "messaging": [{
                "sender": {"id": "synthetic-customer"},
                "message": {"mid": "synthetic-message-1", "text": "Exemplo fictício"},
            }],
            "changes": [{"field": "comments", "value": {"id": "synthetic-comment"}}],
        }],
    }


class OAuthContracts(unittest.TestCase):
    def test_approved_embed_preserves_registered_callback_and_exact_scopes(self):
        url = authorization_url_from_embed(embed(), CALLBACK, STATE, required_scopes=SCOPES)
        parsed = urlsplit(url)
        values = parse_qs(parsed.query)
        self.assertEqual(parsed.hostname, "www.instagram.com")
        self.assertEqual(values["redirect_uri"], [CALLBACK])
        self.assertEqual(values["state"], [STATE])
        self.assertEqual(values["scope"], [",".join(SCOPES)])
        self.assertEqual(values["response_type"], ["code"])

    def test_rejects_redirect_tampering_scope_escalation_and_state_injection(self):
        bad_embeds = [
            embed(redirect_uri="https://attacker.example/callback"),
            embed(scope="instagram_business_basic,instagram_business_content_publish"),
            embed(scope="instagram_business_basic,business_manage_messages"),
            embed(scope="instagram_business_basic,instagram_business_basic"),
            embed(response_type="token"),
            embed(client_id="not-numeric"),
            embed() + "&client_id=999",
            embed() + "&state=attacker-provided",
            embed() + "&access_token=leak",
            embed().replace("www.instagram.com", "www.instagram.com.attacker.test"),
            embed().replace("https://", "http://", 1),
            embed().replace("/oauth/authorize?", "/redirect?"),
        ]
        for value in bad_embeds:
            with self.subTest(embed=value[:85]), self.assertRaises(MetaContractError):
                authorization_url_from_embed(value, CALLBACK, STATE, required_scopes=SCOPES)
        for state in ("short", "a" * 200, "a" * 42 + "/"):
            with self.subTest(state=state[:10]), self.assertRaises(MetaContractError):
                authorization_url_from_embed(embed(), CALLBACK, state, required_scopes=SCOPES)

    def test_rejects_non_https_or_different_registered_callback(self):
        for callback in ("http://socialmei.example/callback", CALLBACK + "?other=1", "https://evil.test"):
            with self.subTest(callback=callback), self.assertRaises(MetaContractError):
                authorization_url_from_embed(embed(), callback, STATE, required_scopes=SCOPES)


class WebhookContracts(unittest.TestCase):
    def test_signature_over_raw_bytes_and_safe_summary(self):
        body, signature = signed(event())
        result = inspect_verified_webhook(body, signature, SECRET)
        self.assertEqual((result.entries, result.messaging_events, result.change_events), (1, 1, 1))
        self.assertNotIn("Exemplo fictício", repr(result))
        verify_webhook_signature(body, signature, SECRET)
        # Equivalent JSON fields with different raw byte ordering require a new HMAC.
        self.assertRaises(MetaContractError, verify_webhook_signature, body + b" ", signature, SECRET)

    def test_rejects_missing_or_malformed_signatures_and_secret(self):
        body, signature = signed(event())
        for bad in ("", "sha1=" + signature[7:], "sha256=abc", signature.upper(), "sha256=" + "0" * 64):
            with self.subTest(bad=bad[:10]), self.assertRaises(MetaContractError):
                verify_webhook_signature(body, bad, SECRET)
        for raw in (b"", b"x" * (65536 + 1), bytearray(body)):
            with self.subTest(size=len(raw)), self.assertRaises(MetaContractError):
                verify_webhook_signature(raw, signature, SECRET)
        with self.assertRaises(MetaContractError):
            verify_webhook_signature(body, signature, "short")

    def test_fails_closed_for_duplicate_json_keys_and_wrong_provider(self):
        for body in (
            b'{"object":"instagram","object":"instagram","entry":[]}',
            b'{"object":"facebook","entry":[{"id":"1","messaging":[{}]}]}',
            b'{"object":"instagram","entry":[{"id":"1","messaging":[],"changes":[]}]}',
            b'{"object":"instagram","entry":[{"id":"abc","messaging":[{}]}]}',
            b'{"object":"instagram","entry":[{"id":"1","time":true,"messaging":[{}]}]}',
            b'{"object":"instagram","entry":[{"id":"1","messaging":[1]}]}',
            b'{"object":"instagram","entry":[{"id":"1","messaging":{}}]}',
            b'{"object":"instagram","entry":[{"id":"1","messaging":[{}],"changes":[{},{"a":1,"a":2}]}]}',
            b'not json',
        ):
            signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
            with self.subTest(body=body[:75]), self.assertRaises(MetaContractError):
                inspect_verified_webhook(body, signature, SECRET)

    def test_bounds_batch_and_event_count(self):
        too_many_entries = {"object": "instagram", "entry": [{"id": "1", "messaging": [{}]}] * (MAX_ENTRIES + 1)}
        too_many_messages = {"object": "instagram", "entry": [{"id": "1", "messaging": [{}] * (MAX_EVENTS + 1)}]}
        for payload in (too_many_entries, too_many_messages):
            body, signature = signed(payload)
            with self.assertRaises(MetaContractError):
                inspect_verified_webhook(body, signature, SECRET)

    def test_verification_challenge_never_leaks_on_bad_token(self):
        self.assertEqual(verify_webhook_challenge("subscribe", TOKEN, "challenge-123", TOKEN), "challenge-123")
        for args in (
            ("unsubscribe", TOKEN, "challenge-123", TOKEN),
            ("subscribe", "incorrect", "challenge-123", TOKEN),
            ("subscribe", TOKEN, "", TOKEN),
            ("subscribe", TOKEN, "challenge-123", "short"),
        ):
            with self.subTest(args=args[:2]), self.assertRaises(MetaContractError):
                verify_webhook_challenge(*args)


if __name__ == "__main__":
    unittest.main()
