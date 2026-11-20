"""Private owner grants: only synthetic accounts in an explicit disposable DB."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg

import workspace_access as access
import test_account_auth as accounts

parts = urlsplit(accounts.DB)
DISPOSABLE = (os.getenv("SOCIALMEI_WORKSPACE_ACCESS_TESTS") == "1"
              and parts.hostname in {"localhost", "127.0.0.1"}
              and parts.path in {"/socialmei_access_test", "/socialmei_demo_test", "/socialmei_test"})


class AccessContracts(unittest.TestCase):
    def test_expected_scope_requires_real_ids_names_email_and_owners(self):
        valid = dict(actor_id=1, target_user_id=2, workspace_id=3, target_email="user@example.test",
                     expected_user_name="Fictício", expected_workspace_name="Negócio fictício", expected_owner_ids=[4])
        for change in ({"actor_id": True}, {"workspace_id": 0}, {"target_email": "invalid"},
                       {"expected_owner_ids": []}, {"expected_owner_ids": [True]},
                       {"expected_owner_ids": [4, 4]}, {"expected_user_name": ""}):
            with self.subTest(change=change), self.assertRaises((ValueError, access.AccessError)):
                access.AccessRequest(**{**valid, **change})
        request = access.AccessRequest(**{**valid, "target_email": " USER@EXAMPLE.TEST "})
        self.assertEqual(request.target_email, "user@example.test")
        valid["expected_owner_ids"].append(9)
        self.assertEqual(request.expected_owner_ids, (4,))


@unittest.skipUnless(DISPOSABLE, "Explicit disposable workspace-access database required")
class AccessDatabaseTests(unittest.TestCase):
    setUpClass = classmethod(accounts.AccountDatabaseTests.setUpClass.__func__)
    login = accounts.AccountDatabaseTests.login
    invited = accounts.AccountDatabaseTests.invited
    register = accounts.AccountDatabaseTests.register
    create = accounts.AccountDatabaseTests.create

    def setUp(self):
        accounts.AccountDatabaseTests.setUp(self)
        self.owner = self.register("original@example.test")
        self.project = self.register("project@example.test")
        self.workspace = self.owner.identity["negocio"]["id"]
        self.original_id = self.owner.identity["usuario"]["id"]
        self.target_id = self.project.identity["usuario"]["id"]
        self.other_workspace = self.project.identity["negocio"]["id"]
        renamed = self.owner.patch("/api/v1/auth/profile", json={"nome_negocio": "Brilho fictício"})
        self.assertEqual(renamed.status_code, 200)
        self.request = access.AccessRequest(self.admin_id, self.target_id, self.workspace,
            "project@example.test", "MEI", "Brilho fictício", [self.original_id])

    def query(self, sql, params=()):
        with psycopg.connect(accounts.DB) as conn:
            return conn.execute(sql, params).fetchall()

    def execute(self, sql, params=()):
        with psycopg.connect(accounts.DB) as conn:
            conn.execute(sql, params)

    def role(self, workspace, user):
        rows = self.query("SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s", (workspace, user))
        return rows[0][0] if rows else None

    def grant(self):
        plan = access.inspect_access(self.request)
        grant_id = uuid4()
        return plan, grant_id, access.grant_owner(self.request, plan["plan_sha256"], grant_id)

    def switch(self, client, workspace):
        value = client.get("/api/v1/auth/me").json()
        client.headers["X-SocialMEI-Identity"] = f"{value['usuario']['id']}:{value['negocio']['id']}"
        response = client.post("/api/v1/auth/workspaces/switch", json={"workspace_id": workspace})
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        client.headers["X-SocialMEI-CSRF"] = value["csrf_token"]
        client.headers["X-SocialMEI-Identity"] = f"{value['usuario']['id']}:{value['negocio']['id']}"
        return value

    def test_readonly_plan_then_additive_grant_switch_isolation_and_conditional_rollback(self):
        first = self.create(self.owner, "clientes", {"nome": "Cliente A fictício"})
        second = self.create(self.project, "clientes", {"nome": "Cliente B fictício"})
        original_credentials = self.query("SELECT * FROM socialmei.auth_credenciais ORDER BY user_id")
        memberships = self.query("SELECT * FROM socialmei.workspace_members ORDER BY workspace_id,user_id")
        audits = self.query("SELECT * FROM socialmei.auth_auditoria ORDER BY id")
        plan = access.inspect_access(self.request)
        self.assertEqual(self.query("SELECT * FROM socialmei.workspace_members ORDER BY workspace_id,user_id"), memberships)
        self.assertEqual(self.query("SELECT * FROM socialmei.auth_auditoria ORDER BY id"), audits)
        gid = uuid4()
        receipt = access.grant_owner(self.request, plan["plan_sha256"], gid)
        self.assertEqual(access.grant_owner(self.request, plan["plan_sha256"], gid), receipt)
        self.assertEqual(self.role(self.workspace, self.original_id), "owner")
        self.assertEqual(self.role(self.workspace, self.target_id), "owner")
        self.assertEqual(self.role(self.other_workspace, self.target_id), "owner")
        self.assertEqual(self.query("SELECT * FROM socialmei.auth_credenciais ORDER BY user_id"), original_credentials)
        listed = self.project.get("/api/v1/auth/workspaces").json()
        self.assertTrue({self.workspace, self.other_workspace}.issubset({row["id"] for row in listed["items"]}))
        switched = self.switch(self.project, self.workspace)
        self.assertEqual(switched["usuario"]["id"], self.target_id)
        self.assertEqual(self.project.get(f"/api/v1/clientes/{first['id']}").status_code, 200)
        self.assertEqual(self.project.get(f"/api/v1/clientes/{second['id']}").status_code, 404)
        self.assertEqual(self.project.patch(f"/api/v1/clientes/{second['id']}", json={"nome": "Forbidden", "expected_version": 1}).status_code, 404)
        separate_session = self.login("project@example.test")
        undo = access.inspect_rollback(self.request, receipt)
        self.assertTrue(access.rollback_owner(self.request, receipt, undo["plan_sha256"])["removed_added_owner"])
        self.assertTrue(access.rollback_owner(self.request, receipt, undo["plan_sha256"])["already_removed"])
        self.assertIsNone(self.role(self.workspace, self.target_id))
        self.assertEqual(self.role(self.workspace, self.original_id), "owner")
        self.assertEqual(self.project.get("/api/v1/clientes").status_code, 401)
        self.assertEqual(separate_session.get("/api/v1/clientes").status_code, 200)
        self.assertEqual(self.owner.get(f"/api/v1/clientes/{first['id']}").status_code, 200)
        with self.assertRaisesRegex(access.AccessError, "GRANT_ALREADY_ROLLED_BACK"):
            access.grant_owner(self.request, plan["plan_sha256"], gid)

    def test_missing_disabled_unprivileged_or_different_identity_is_refused(self):
        cases = [(replace(self.request, actor_id=self.original_id), "ACTIVE_PLATFORM_ADMIN_REQUIRED"),
                 (replace(self.request, target_user_id=99999), "TARGET_ACCOUNT_MISSING"),
                 (replace(self.request, target_email="other@example.test"), "TARGET_IDENTITY_CHANGED"),
                 (replace(self.request, expected_user_name="Other"), "TARGET_IDENTITY_CHANGED"),
                 (replace(self.request, expected_workspace_name="Other"), "WORKSPACE_IDENTITY_CHANGED")]
        for request, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(access.AccessError, code):
                access.inspect_access(request)
        self.execute("UPDATE socialmei.auth_credenciais SET ativo=false WHERE user_id=%s", (self.target_id,))
        with self.assertRaisesRegex(access.AccessError, "TARGET_ACCOUNT_DISABLED"):
            access.inspect_access(self.request)
        self.execute("DELETE FROM socialmei.auth_credenciais WHERE user_id=%s", (self.target_id,))
        with self.assertRaisesRegex(access.AccessError, "TARGET_CREDENTIAL_MISSING"):
            access.inspect_access(self.request)

    def test_stale_plan_different_owners_and_existing_nonowner_role_are_refused(self):
        plan = access.inspect_access(self.request)
        with self.assertRaisesRegex(access.AccessError, "APPROVED_BASELINE_CHANGED"):
            access.grant_owner(self.request, "a" * 64, uuid4())
        self.execute("UPDATE socialmei.workspaces SET slug=slug||'-changed' WHERE id=%s", (self.workspace,))
        with self.assertRaisesRegex(access.AccessError, "APPROVED_BASELINE_CHANGED"):
            access.grant_owner(self.request, plan["plan_sha256"], uuid4())
        with self.assertRaisesRegex(access.AccessError, "OWNER_SET_CHANGED"):
            access.inspect_access(replace(self.request, expected_owner_ids=[self.admin_id]))
        self.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'member')", (self.workspace, self.target_id))
        with self.assertRaisesRegex(access.AccessError, "EXISTING_ROLE_REQUIRES_SEPARATE_REVIEW"):
            access.inspect_access(self.request)

    def test_preexisting_owner_is_noop_and_never_generates_removable_receipt(self):
        self.grant()
        request = replace(self.request, expected_owner_ids=[self.original_id, self.target_id])
        plan = access.inspect_access(request)
        audits = self.query("SELECT count(*) FROM socialmei.auth_auditoria")
        result = access.grant_owner(request, plan["plan_sha256"], uuid4())
        self.assertEqual(result, {"changed": False, "already_owner": True, "receipt": None})
        self.assertEqual(self.query("SELECT count(*) FROM socialmei.auth_auditoria"), audits)

    def test_concurrent_same_grant_replays_one_membership_and_one_audit(self):
        plan = access.inspect_access(self.request)
        grant_id = uuid4()
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: access.grant_owner(self.request, plan["plan_sha256"], grant_id), range(2)))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(self.query("SELECT count(*) FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
                                    (self.workspace, self.target_id))[0][0], 1)
        self.assertEqual(self.query("SELECT count(*) FROM socialmei.auth_auditoria WHERE alvo_user_id=%s AND acao LIKE %s",
                                    (self.target_id, "own+:%"))[0][0], 1)

    def test_rollback_refuses_later_audited_access_change_instead_of_deleting(self):
        _, _, receipt = self.grant()
        self.execute("INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) VALUES(%s,%s,'equipe:review')",
                     (self.admin_id, self.target_id))
        with self.assertRaisesRegex(access.AccessError, "TARGET_ACCESS_CHANGED_AFTER_GRANT"):
            access.inspect_rollback(self.request, receipt)
        self.assertEqual(self.role(self.workspace, self.target_id), "owner")

    def test_grant_and_rollback_audit_failure_roll_back_the_entire_transaction(self):
        plan = access.inspect_access(self.request)
        with patch.object(access, "_audit", side_effect=RuntimeError("Synthetic persistence failure")):
            with self.assertRaises(RuntimeError):
                access.grant_owner(self.request, plan["plan_sha256"], uuid4())
        self.assertIsNone(self.role(self.workspace, self.target_id))
        _, _, receipt = self.grant()
        undo = access.inspect_rollback(self.request, receipt)
        with patch.object(access, "_audit", side_effect=RuntimeError("Synthetic persistence failure")):
            with self.assertRaises(RuntimeError):
                access.rollback_owner(self.request, receipt, undo["plan_sha256"])
        self.assertEqual(self.role(self.workspace, self.target_id), "owner")

    def test_receipt_write_failure_rolls_back_and_lost_response_replays_durable_receipt(self):
        import json
        plan = access.inspect_access(self.request)
        grant_id = uuid4()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-receipt.json"
            with patch.object(access.os, "fsync", side_effect=OSError("Synthetic disk failure")):
                with self.assertRaises(OSError):
                    access.grant_owner(self.request, plan["plan_sha256"], grant_id, receipt_path=path)
            self.assertFalse(path.exists())
            self.assertIsNone(self.role(self.workspace, self.target_id))
            receipt = access.grant_owner(self.request, plan["plan_sha256"], grant_id, receipt_path=path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), receipt)
            recovered = Path(directory) / "recovered-private-receipt.json"
            replay = access.grant_owner(self.request, plan["plan_sha256"], grant_id, receipt_path=recovered)
            self.assertEqual(replay, receipt)
            self.assertEqual(json.loads(recovered.read_text(encoding="utf-8")), receipt)
            with self.assertRaises(FileExistsError):
                access.grant_owner(self.request, plan["plan_sha256"], grant_id, receipt_path=path)
            self.assertEqual(self.role(self.workspace, self.target_id), "owner")

    def test_plan_preserves_owners_without_credentials_instead_of_omitting_them(self):
        with psycopg.connect(accounts.DB) as conn:
            other = conn.execute("INSERT INTO socialmei.users(email,nome) VALUES('historical@example.test','Historical fictitious owner') RETURNING id").fetchone()[0]
            conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')", (self.workspace, other))
        with self.assertRaisesRegex(access.AccessError, "OWNER_SET_CHANGED"):
            access.inspect_access(self.request)
        request = replace(self.request, expected_owner_ids=[self.original_id, other])
        plan = access.inspect_access(request)
        self.assertEqual(plan["preserved_owner_ids"], [self.original_id, other])
        access.grant_owner(request, plan["plan_sha256"], uuid4())
        self.assertEqual(self.role(self.workspace, other), "owner")

    def test_rollback_rejects_foreign_receipt_or_later_membership_changes(self):
        _, _, receipt = self.grant()
        with self.assertRaisesRegex(access.AccessError, "RECEIPT_SCOPE_MISMATCH"):
            access.inspect_rollback(self.request, {**receipt, "workspace_id": self.other_workspace})
        self.execute("UPDATE socialmei.workspace_members SET role='member' WHERE workspace_id=%s AND user_id=%s", (self.workspace, self.target_id))
        with self.assertRaisesRegex(access.AccessError, "MEMBERSHIP_CHANGED_AFTER_GRANT"):
            access.inspect_rollback(self.request, receipt)

    def test_rollback_cannot_remove_the_only_remaining_active_owner(self):
        _, _, receipt = self.grant()
        self.execute("UPDATE socialmei.auth_credenciais SET ativo=false WHERE user_id=%s", (self.original_id,))
        with self.assertRaisesRegex(access.AccessError, "EXISTING_ACTIVE_OWNER_REQUIRED"):
            access.inspect_rollback(self.request, receipt)


if __name__ == "__main__":
    unittest.main()
