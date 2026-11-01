"""Gate 9 evidence must fail closed and disclose neither messages nor secrets."""
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "direct_proof", Path(__file__).resolve().parents[1] / "tools/instagram-direct-proof.py"
)
proof = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proof)
SHA = "a" * 40
MARKER = "SOCIALMEI-G9-0123456789ABCDEF"


def counts(**changes):
    value = dict(total_messages=1, team_messages=1, other_workspace_messages=0,
                 linked_events=1, linked_messages=1, linked_conversations=1)
    value.update(changes)
    return value


class DirectProofTests(unittest.TestCase):
    def child(self, payload, marker=None):
        queries = []
        rows = [(1,), (1,), (0, 0, None), (0,)]
        if marker:
            rows += [(1, 1, 0), (1, 1, 1)]
        rows += [[('connection', '123456', 'encrypted-private')]]

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, parameters=None):
                queries.append((sql, parameters))
                if sql.startswith('SET '):
                    return None
                value = rows.pop(0)
                return SimpleNamespace(fetchone=lambda: value, fetchall=lambda: value)

        modules = {
            'database': SimpleNamespace(connect=Connection),
            'instagram_runtime': SimpleNamespace(build_runtime=lambda: SimpleNamespace(
                oauth=SimpleNamespace(vault=SimpleNamespace(open=lambda *args: 'private-bearer')))),
            'instagram_token_vault': SimpleNamespace(TokenBinding=lambda *args: args),
        }
        output = io.StringIO()
        disabled = logging.root.manager.disable
        try:
            with patch.dict(sys.modules, modules), patch.dict(os.environ, {
                'SOCIALMEI_INSTAGRAM_GRAPH_VERSION': 'v26.0',
                'SOCIALMEI_INSTAGRAM_CLIENT_ID': '12345',
            }), patch('sys.stdin', io.StringIO(json.dumps(dict(
                marker=marker, check_subscription=True, meta_app_id='12345'
            )))), patch('sys.stdout', output), patch('urllib.request.build_opener') as opener:
                opener.return_value.open.return_value = io.BytesIO(payload)
                exec(proof.CHILD, {})
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.get_method(), 'GET')
                self.assertEqual(request.full_url, 'https://graph.instagram.com/v26.0/123456/subscribed_apps')
                self.assertNotIn('private', request.full_url)
        finally:
            logging.disable(disabled)
        self.assertNotIn('private', output.getvalue())
        return json.loads(output.getvalue()), queries

    def responses(self, marker=True, revision=SHA):
        container = {"Image": "sha256:fixture", "Config": {"Env": [
            "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED=true",
            "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false",
            "PRIVATE_TOKEN=never-print-this",
        ]}}
        image = {"Config": {"Labels": {"org.opencontainers.image.revision": revision}}}
        database = dict(connected_with_messaging_scopes=1, events=1,
                        processed_message_events=1, inbox_messages=1,
                        unexpected_private_field="private-message-or-token")
        if marker:
            database["marker"] = counts()
        return [json.dumps(item) for item in ([container], [image], database)]

    def test_one_durable_message_is_not_full_live_homologation(self):
        with patch.object(proof, "run", side_effect=self.responses()) as run:
            result = proof.inspect(SHA, MARKER)
        self.assertEqual(result["marker_status"], "one_persisted_inbound_message")
        self.assertFalse(result["site_display_verified"])
        self.assertFalse(result["signed_delivery_verified"])
        self.assertFalse(result["account_subscription_verified"])
        self.assertFalse(result["dashboard_send_enabled"])
        self.assertNotIn("private", json.dumps(result))
        self.assertNotIn(MARKER, json.dumps(result))
        self.assertEqual(json.loads(run.call_args.args[1]), {"marker": MARKER, "check_subscription": False, "meta_app_id": None})

    def test_baseline_does_not_claim_marker_test(self):
        with patch.object(proof, "run", side_effect=self.responses(marker=False)):
            result = proof.inspect(SHA)
        self.assertEqual(result["marker_status"], "not_requested")

    def test_wrong_installed_sha_stops_before_database(self):
        with patch.object(proof, "run", side_effect=self.responses(revision="b" * 40)) as run:
            with self.assertRaises(ValueError):
                proof.inspect(SHA, MARKER)
        self.assertEqual(run.call_count, 2)

    def test_invalid_target_values_never_execute_commands(self):
        for sha, marker in [("main", MARKER), (SHA, "user@example.com"),
                            (SHA, MARKER + "' OR true --"), (SHA, "x" * 5000)]:
            with self.subTest(marker=marker[:30]), patch.object(proof, "run") as run:
                with self.assertRaises(ValueError):
                    proof.inspect(sha, marker)
                run.assert_not_called()

    def test_duplicates_and_wrong_workspace_fail_proof(self):
        for value in (counts(total_messages=2, team_messages=2),
                      counts(other_workspace_messages=1), counts(linked_events=0),
                      counts(linked_conversations=2)):
            self.assertEqual(proof.marker_status(value), "requires_investigation")
        self.assertEqual(proof.marker_status(dict.fromkeys(counts(), 0)), "not_observed")

    def test_unexpected_child_fields_and_counts_are_refused(self):
        for value in (counts(secret="never-output"), counts(team_messages=True),
                      counts(total_messages=-1), None):
            with self.assertRaises(ValueError):
                proof.marker_status(value)

    def test_subprocess_errors_do_not_expose_stderr(self):
        with patch.object(proof.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], 1, "private-token", "private-error")):
            with self.assertRaises(RuntimeError) as error:
                proof.run(["docker", "inspect", proof.API])
        self.assertNotIn("private", str(error.exception))

    def test_queries_are_read_only_and_marker_is_parameterized(self):
        self.assertIn("REPEATABLE READ READ ONLY", proof.CHILD)
        self.assertIn("m.text=%s", proof.CHILD)
        self.assertIn("(marker,)", proof.CHILD)
        for word in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "urlopen", "requests.", "method='POST'"):
            self.assertNotIn(word, proof.CHILD)

    def test_subscription_summary_allowlists_fields(self):
        responses = self.responses(marker=False)
        child = json.loads(responses[-1])
        child['subscription'] = dict(status='read_confirmed', app_listed=True,
                                     messages_subscribed=True, fields_available=True, listed_apps=1, any_app_has_messages=True,
                                     secret='never-output')
        responses[-1] = json.dumps(child)
        with patch.object(proof, 'run', side_effect=responses):
            result = proof.inspect(SHA, check_subscription=True, meta_app_id="12345")
        self.assertTrue(result['account_subscription_verified'])
        self.assertFalse(result['site_display_verified'])
        self.assertNotIn('secret', json.dumps(result))

    def test_provider_failure_is_not_success(self):
        for subscription in (dict(status='provider_refused', http_status=403),
                             dict(status='unavailable'),
                             dict(status='read_confirmed', app_listed=False,
                                  messages_subscribed=False, fields_available=False, listed_apps=0, any_app_has_messages=False)):
            responses = self.responses(marker=False)
            child = json.loads(responses[-1])
            child['subscription'] = subscription
            responses[-1] = json.dumps(child)
            with patch.object(proof, 'run', side_effect=responses):
                result = proof.inspect(SHA, check_subscription=True, meta_app_id="12345")
            self.assertFalse(result['account_subscription_verified'])

    def test_oauth_client_is_not_assumed_to_be_parent_meta_app(self):
        responses = self.responses(marker=False)
        child = json.loads(responses[-1])
        child['subscription'] = dict(status='read_confirmed', app_listed=False,
                                    messages_subscribed=False, fields_available=False,
                                    listed_apps=1, any_app_has_messages=True)
        responses[-1] = json.dumps(child)
        with patch.object(proof, 'run', side_effect=responses):
            result = proof.inspect(SHA, check_subscription=True)
        self.assertFalse(result['account_subscription_verified'])
        self.assertTrue(result['account_subscription']['any_app_has_messages'])
        self.assertEqual(result['account_subscription']['identity_basis'], 'oauth_client_only')

    def test_child_checks_subscription_without_exporting_credentials(self):
        result, queries = self.child(json.dumps({'data': [dict(
            id='12345', subscribed_fields=['messages'], access_token='private-response'
        )]}).encode(), MARKER)
        self.assertTrue(result['subscription']['messages_subscribed'])
        self.assertEqual(result['marker'], counts())
        self.assertTrue(any(parameters == (MARKER,) for _, parameters in queries))
        self.assertTrue(all(sql.startswith(('SELECT ', 'SET ')) for sql, _ in queries))
        self.assertEqual(sum('READ ONLY' in sql for sql, _ in queries), 2)

    def test_child_does_not_follow_paging_or_accept_oversized_response(self):
        for raw in (b'x' * 65537, b'{"data":[],"paging":{"next":"https://evil.invalid/private"}}'):
            result, _ = self.child(raw)
            self.assertEqual(result['subscription'], {'status': 'unavailable'})

    def test_child_disables_redirects_and_proxies(self):
        self.assertIn('ProxyHandler({}),NoRedirect()', proof.CHILD)
        self.assertIn('def redirect_request(self, *args, **kwargs):\n                return None', proof.CHILD)


if __name__ == "__main__":
    unittest.main()
