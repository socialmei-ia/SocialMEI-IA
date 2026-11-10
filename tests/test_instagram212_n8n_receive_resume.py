"""Offline safety tests for resumed receive-only IG212 n8n cutover.

The previous attempt created the native credential and 23-node draft, then
erroneously rejected the missing/stale activeVersionId in PUT's response.
Resumption MUST verify the active published version by independent GET.
"""
import copy
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "instagram212-n8n-receive-resume.py"
SPEC = importlib.util.spec_from_file_location("ig212_resume", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class ResumeContracts(unittest.TestCase):
    def make(self):
        old = {"versionId": "old-version", "nodes": [{
            "id": "hook", "name": "InstagramHook",
            "type": "n8n-nodes-base.webhook", "parameters": {"httpMethod": "POST"},
        }]}
        n = mod.NAMES
        prepared = {"name": "Instagram", "settings": {"executionOrder":"v1"},
                    "connections": {
                        "InstagramHook": {"main": [[{"node":n["prepare"]}]]},
                        n["prepare"]: {"main": [[{"node":n["persist"]}],
                                                   [{"node":n["fail"]}]]},
                        n["persist"]: {"main": [[{"node":n["validate"]}],
                                                  [{"node":n["fail"]}]]},
                        n["validate"]: {"main": [[{"node":n["ack"]}],
                                                   [{"node":n["fail"]}]]},
                        n["ack"]: {"main": [[]]},
                    },
                    "nodes": [{
                        "id": "persist", "name": n["persist"],
                        "type": "n8n-nodes-base.httpRequest",
                        "credentials": {"httpBearerAuth":{"id": "credential123",
                                                          "name":"SocialMEI Instagram"}},
                        "parameters": {"headerParameters": {"parameters": [
                            {"name": "Content-Type","value": "application/json"}]}}
                    }]}
        current = dict(prepared, id=mod.WID, active=True,
                       activeVersionId="old-version",
                       versionId="new-draft-version")
        state = {"credential_id": "credential123", "new_version_id":"new-draft-version"}
        return old, prepared, current, state

    def test_independent_get_published_version_still_old(self):
        old, planned, current, state = self.make()
        mod.validate_resume_draft(current, old, planned, state)

    def test_never_publish_if_early_draft_becomes_live(self):
        old, planned, current, state = self.make()
        current["activeVersionId"] = state["new_version_id"]
        with self.assertRaises(mod.Block):
            mod.validate_resume_draft(current, old, planned, state)

    def test_never_accept_external_draft_change(self):
        old, planned, current, state = self.make()
        current = copy.deepcopy(current)
        current["nodes"][0]["parameters"]["headerParameters"]["parameters"][0]["value"] = "text/plain"
        with self.assertRaises(mod.Block):
            mod.validate_resume_draft(current, old, planned, state)

    def test_never_accept_external_version_change(self):
        old, planned, current, state = self.make()
        current["versionId"] = "someone-else-edited"
        with self.assertRaises(mod.Block):
            mod.validate_resume_draft(current, old, planned, state)

    def test_never_accept_legacy_ai_reconnected(self):
        old, planned, current, state = self.make()
        current = copy.deepcopy(current)
        current["connections"][mod.NAMES["ack"]] = {
            "main":[[{"node":"Legacy AI resposta"}]]
        }
        with self.assertRaises(mod.Block):
            mod.validate_resume_draft(current, old, planned, state)

    def test_previous_journal_must_be_recovered(self):
        script = SCRIPT.read_text()
        self.assertIn('state.get("phase") == "restored_previous_runtime"', script)
        self.assertIn('state.get("workflow_recovery") == "old_published_unchanged"', script)
        self.assertIn('state.get("api_recovery") == "healthy_previous"', script)
        self.assertIn('state.get("resume_attempted") is not True', script)

    def test_resume_uses_existing_credential_not_post_credentials_or_put_workflow(self):
        code = SCRIPT.read_text()
        start = code.index("def resume_receive(")
        end = code.index("\ndef main():", start)
        section = code[start:end]
        self.assertIn("patch_candidate(after, state[\"credential_id\"])", section)
        self.assertNotIn('stage_credential(', section)
        self.assertNotIn('"PUT", "/workflows/"', section)
        self.assertNotIn('"POST", "/credentials"', section)
        self.assertIn('"GET", "/workflows/"', section)

    def test_resume_authorization_is_separate(self):
        code = SCRIPT.read_text()
        self.assertIn('RESUME_AUTH = "AUTORIZO-RETOMAR-IG212-RECEBIMENTO-SEM-IA"',code)
        self.assertIn('verify(args.authorization == RESUME_AUTH',code)
        self.assertIn('p.add_argument("--resume", action="store_true", required=True)',code)

    def test_no_false_success_before_published_version_confirmed(self):
        code = SCRIPT.read_text()
        start = code.index("def resume_receive(")
        end = code.index("\ndef main():",start)
        section = code[start:end]
        self.assertLess(section.index("n8n_new_version_not_published"),
                        section.index('"receive_only_published"'))
        self.assertIn('"mensagem_real_meta_validada": False',section)

    def test_recovery_uses_only_current_api_image_no_whatsapp_mutations(self):
        script = SCRIPT.read_text()
        start = script.index("def resume_receive(")
        end = script.index("\ndef main():",start)
        section = script[start:end]
        self.assertIn('rollback_api(base[API], args)',section)
        self.assertIn('protected(base)',section)
        self.assertNotIn('"socialmei-waha", "up"', section)
        self.assertNotIn("docker rm",section)

    def test_staging_files_root_only(self):
        source = SCRIPT.read_text()
        self.assertIn("stat.S_IMODE(path.stat().st_mode) == 0o600",source)
        self.assertIn("stat.S_IMODE(B.stat().st_mode) == 0o700",source)

    def test_n8n_api_key_never_output_to_user(self):
        source = SCRIPT.read_text()
        self.assertIn('getpass("Chave API n8n',source)
        self.assertNotIn('print(key)',source)
        self.assertIn('"operation_failed_details_redacted"',source)


if __name__ == "__main__":
    unittest.main()
