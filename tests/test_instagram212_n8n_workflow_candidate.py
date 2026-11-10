"""Offline safety contracts for the private n8n receive-only workflow candidate."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).resolve().parents[1] / "tools" / "instagram212-n8n-workflow-candidate.py"
SPEC = importlib.util.spec_from_file_location("n8n_candidate", FILE)
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


class CandidateSafetyTests(unittest.TestCase):
    def test_official_helper_is_immutable(self):
        self.assertGreater(len(candidate.helper_identity()), 7000)

    def test_block_if_draft_and_published_differ(self):
        source = {
            "id": candidate.WORKFLOW,
            "active": True,
            "activeVersionId": "published-v",
            "versionId": "draft-v",
            "nodes": [{"id": "hook", "name": "incoming",
                       "type": "n8n-nodes-base.webhook",
                       "parameters": {"httpMethod": "POST"}}] * 17,
            "connections": {},
        }
        with self.assertRaises(candidate.Stop):
            candidate.exported_workflow(json.dumps(source).encode())

    def test_reachability_fails_if_legacy_restored(self):
        source = {"nodes": [
            {"name": "incoming", "id": "hook", "type": "n8n-nodes-base.webhook",
             "parameters": {"httpMethod": "POST", "options": {}}
             }] + [{"name": f"legacy-{n}", "id": f"n{n}", "type": "n8n-nodes-base.code",
                      "parameters": {}} for n in range(16)],
            "settings": {}
        }
        graph = {
            "incoming": {"main": [[{"node": candidate.NAMES["prepare"]}]]},
            candidate.NAMES["prepare"]: {"main": [[{"node": candidate.NAMES["persist"]}], []]},
            candidate.NAMES["persist"]: {"main": [[{"node": candidate.NAMES["validate"]}], []]},
            candidate.NAMES["validate"]: {"main": [[{"node": candidate.NAMES["ack"]}], []]},
            candidate.NAMES["ack"]: {"main": [[{"node": "legacy-0"}]]},
        }
        proposed = {**source["nodes"][0], "parameters": {"httpMethod": "POST",
                    "responseMode": "responseNode", "options": {"rawBody": True}}}
        new_nodes = [
            {"name": name, "id": name, "type": "n8n-nodes-base.code",
             "parameters": {}, **({"credentials": {
                 "httpBearerAuth": {"id": candidate.PLACEHOLDER}}
                 } if name == candidate.NAMES["persist"] else {})}
            for name in candidate.NAMES.values()
        ]
        planned = {"target_workflow_id": candidate.WORKFLOW,
                   "automatically_publish": False,
                   "resume_legacy_automation": False,
                   "candidate": {"nodes": [proposed, *source["nodes"][1:], *new_nodes],
                                 "connections": graph,
                                 "settings": {}}}
        with self.assertRaises(candidate.Stop):
            candidate.validate_candidate(source, planned)

    def test_existing_private_files_never_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            path = folder / "candidate.json"
            with patch.object(candidate, "ROOT", folder):
                candidate.write_once(path, b"first")
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                with patch.object(candidate, "private_file", side_effect=lambda p: p):
                    candidate.write_once(path, b"first")
                    with self.assertRaises(candidate.Stop):
                        candidate.write_once(path, b"changed")

    def test_sanitized_exceptions_never_echo_private_source(self):
        with patch.object(candidate, "prepare", side_effect=ValueError("secret=PRIVATE")
        ), patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(candidate.main(), 2)
            self.assertNotIn("PRIVATE", out.getvalue())
            self.assertIn('"resultado": "BLOQUEADO"', out.getvalue())

    def test_no_live_import_or_provider_calls(self):
        source = FILE.read_text()
        for action in ("import:workflow", "import:credentials",
                       "docker compose up", "docker restart",
                       "https://graph.instagram", "pg_restore",
                       "publish:workflow", "docker exec -u"):
            self.assertNotIn(action, source)

    def test_normal_graph_expected_reachability(self):
        n = candidate.NAMES
        graph = {
            "hook": {"main": [[{"node": n["prepare"]}]]},
            n["prepare"]: {"main": [[{"node": n["persist"]}],
                                      [{"node": n["fail"]}]]},
            n["persist"]: {"main": [[{"node": n["validate"]}],
                                      [{"node": n["fail"]}]]},
            n["validate"]: {"main": [[{"node": n["ack"]}],
                                       [{"node": n["fail"]}]]},
            n["ack"]: {"main": [[]]},
        }
        expected = {"hook", n["prepare"], n["persist"],
                    n["validate"], n["ack"], n["fail"]}
        self.assertEqual(candidate.reachable(graph, "hook"), expected)


if __name__ == "__main__":
    unittest.main()
