"""Private, approved additive owner access. No public routes or account creation."""
import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID

from psycopg.rows import dict_row

from account_auth import normalize_email
from database import connect


class AccessError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise AccessError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class AccessRequest:
    actor_id: int
    target_user_id: int
    workspace_id: int
    target_email: str
    expected_user_name: str
    expected_workspace_name: str
    expected_owner_ids: list[int]

    def __post_init__(self):
        for value in (self.actor_id, self.target_user_id, self.workspace_id):
            require(type(value) is int and 0 < value <= 9007199254740991, "INVALID_ID")
        require(isinstance(self.target_email, str), "INVALID_EMAIL")
        object.__setattr__(self, "target_email", normalize_email(self.target_email))
        for value in (self.expected_user_name, self.expected_workspace_name):
            require(isinstance(value, str) and bool(value.strip()) and len(value) <= 160
                    and not any(ord(c) < 32 for c in value), "INVALID_EXPECTED_NAME")
        owners = self.expected_owner_ids
        require(isinstance(owners, (list, tuple)) and bool(owners)
                and all(type(i) is int and 0 < i <= 9007199254740991 for i in owners)
                and len(owners) == len(set(owners)), "INVALID_EXPECTED_OWNERS")
        object.__setattr__(self, "expected_owner_ids", tuple(sorted(owners)))


def _scope(conn, request, *, lock=False):
    conn.row_factory = dict_row
    if lock:
        conn.execute("SET LOCAL lock_timeout='5s'")
        conn.execute("SELECT pg_advisory_xact_lock(72426002)")
    workspace = conn.execute("SELECT id,nome,slug FROM socialmei.workspaces WHERE id=%s"
                             + (" FOR UPDATE" if lock else ""), (request.workspace_id,)).fetchone()
    require(workspace is not None, "WORKSPACE_MISSING")
    require(workspace["nome"] == request.expected_workspace_name, "WORKSPACE_IDENTITY_CHANGED")
    ids = sorted({request.actor_id, request.target_user_id})
    users = conn.execute(
        "SELECT id,email,nome FROM socialmei.users "
        "WHERE id=ANY(%s) ORDER BY id" + (" FOR SHARE" if lock else ""),
        (ids,),
    ).fetchall()
    users = {row["id"]: row for row in users}
    credentials = conn.execute(
        "SELECT user_id,ativo,administrador_plataforma FROM socialmei.auth_credenciais "
        "WHERE user_id=ANY(%s) ORDER BY user_id" + (" FOR SHARE" if lock else ""), (ids,),
    ).fetchall()
    for credential in credentials:
        users[credential["user_id"]].update(credential)
    actor, target = users.get(request.actor_id), users.get(request.target_user_id)
    require(actor and actor.get("ativo") and actor.get("administrador_plataforma"), "ACTIVE_PLATFORM_ADMIN_REQUIRED")
    require(target is not None, "TARGET_ACCOUNT_MISSING")
    require("ativo" in target, "TARGET_CREDENTIAL_MISSING")
    require(target["ativo"], "TARGET_ACCOUNT_DISABLED")
    require(normalize_email(target["email"]) == request.target_email
            and target["nome"] == request.expected_user_name, "TARGET_IDENTITY_CHANGED")
    members = conn.execute(
        "SELECT m.user_id,m.role,m.criado_em,c.ativo FROM socialmei.workspace_members m "
        "LEFT JOIN socialmei.auth_credenciais c ON c.user_id=m.user_id WHERE m.workspace_id=%s "
        "ORDER BY m.user_id" + (" FOR UPDATE OF m" if lock else ""), (request.workspace_id,),
    ).fetchall()
    owners = [row for row in members if row["role"] == "owner"]
    require(any(row["ativo"] for row in owners), "EXISTING_ACTIVE_OWNER_REQUIRED")
    membership = next((row for row in members if row["user_id"] == request.target_user_id), None)
    return {"database": conn.execute("SELECT current_database() AS name").fetchone()["name"],
            "workspace": workspace, "actor_id": request.actor_id,
            "target": {"id": target["id"], "email_digest": digest(target["email"]),
                       "name_digest": digest(target["nome"]),
                       "platform_admin": target["administrador_plataforma"]},
            "owners": owners, "membership": membership}


def _grant_plan(request, scope):
    owners = sorted(row["user_id"] for row in scope["owners"])
    require(owners == sorted(request.expected_owner_ids), "OWNER_SET_CHANGED")
    member = scope["membership"]
    require(not member or member["role"] == "owner", "EXISTING_ROLE_REQUIRES_SEPARATE_REVIEW")
    return {"version": 1, "operation": "add_owner", "actor_id": request.actor_id,
            "target_user_id": request.target_user_id, "workspace_id": request.workspace_id,
            "workspace_name": request.expected_workspace_name, "preserved_owner_ids": owners,
            "already_owner": bool(member), "plan_sha256": digest(scope)}


def inspect_access(request):
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='5s'")
        return _grant_plan(request, _scope(conn, request))


def _actions(request, grant_id, approved_plan):
    grant_id = str(UUID(str(grant_id)))
    binding = digest([request.__dict__, grant_id, approved_plan])[:32]
    return grant_id, "own+:" + binding, "own-:" + binding


def _audit(conn, request, action):
    return conn.execute(
        "INSERT INTO socialmei.auth_auditoria(user_id,alvo_user_id,acao) VALUES(%s,%s,%s) "
        "RETURNING id,criado_em", (request.actor_id, request.target_user_id, action),
    ).fetchone()


def _save_receipt(path, value):
    path = Path(path)
    require(not path.is_symlink() and all(not parent.is_symlink() for parent in path.parents), "RECEIPT_PATH_SYMLINK")
    created = False
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            parent_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise


def grant_owner(request, approved_plan, grant_id, *, receipt_path=None):
    require(isinstance(approved_plan, str) and len(approved_plan) == 64, "APPROVED_PLAN_REQUIRED")
    grant_id, action, rollback_action = _actions(request, grant_id, approved_plan)
    with connect() as conn:
        scope = _scope(conn, request, lock=True)
        prior = conn.execute("SELECT id,criado_em FROM socialmei.auth_auditoria "
            "WHERE user_id=%s AND alvo_user_id=%s AND acao=%s ORDER BY id",
            (request.actor_id, request.target_user_id, action)).fetchall()
        require(len(prior) <= 1, "AMBIGUOUS_GRANT_RECEIPT")
        if prior:
            require(not conn.execute("SELECT 1 FROM socialmei.auth_auditoria WHERE acao=%s", (rollback_action,)).fetchone(),
                    "GRANT_ALREADY_ROLLED_BACK")
            member = scope["membership"]
            require(member and member["role"] == "owner" and member["criado_em"] == prior[0]["criado_em"],
                    "MEMBERSHIP_CHANGED_AFTER_GRANT")
            require(sorted(row["user_id"] for row in scope["owners"] if row["user_id"] != request.target_user_id)
                    == sorted(request.expected_owner_ids), "OWNER_SET_CHANGED")
            receipt = _receipt(request, scope, grant_id, approved_plan, prior[0])
            if receipt_path is not None:
                _save_receipt(receipt_path, receipt)
            return receipt
        plan = _grant_plan(request, scope)
        require(plan["plan_sha256"] == approved_plan, "APPROVED_BASELINE_CHANGED")
        if plan["already_owner"]:
            result = {"changed": False, "already_owner": True, "receipt": None}
            if receipt_path is not None:
                _save_receipt(receipt_path, result)
            return result
        conn.execute("INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')",
                     (request.workspace_id, request.target_user_id))
        audit = _audit(conn, request, action)
        receipt = _receipt(request, scope, grant_id, approved_plan, audit)
        # Keep the grant transaction open until its private receipt is durable.
        if receipt_path is not None:
            _save_receipt(receipt_path, receipt)
        return receipt


def _receipt(request, scope, grant_id, approved_plan, audit):
    return {"version": 1, "operation": "add_owner", "grant_id": grant_id,
            "actor_id": request.actor_id, "target_user_id": request.target_user_id,
            "workspace_id": request.workspace_id, "database": scope["database"],
            "request_sha256": digest(request.__dict__), "approved_grant_plan": approved_plan,
            "audit_id": audit["id"], "membership_created_at": audit["criado_em"].isoformat()}


def _rollback_plan(conn, request, receipt, scope):
    require(receipt.get("version") == 1 and receipt.get("operation") == "add_owner"
            and receipt.get("actor_id") == request.actor_id
            and receipt.get("target_user_id") == request.target_user_id
            and receipt.get("workspace_id") == request.workspace_id
            and receipt.get("database") == scope["database"]
            and receipt.get("request_sha256") == digest(request.__dict__), "RECEIPT_SCOPE_MISMATCH")
    _, action, undo = _actions(request, receipt["grant_id"], receipt["approved_grant_plan"])
    event = conn.execute("SELECT id,criado_em,user_id,alvo_user_id,acao FROM socialmei.auth_auditoria WHERE id=%s",
                         (receipt["audit_id"],)).fetchone()
    require(event and event["user_id"] == request.actor_id and event["alvo_user_id"] == request.target_user_id
            and event["acao"] == action and event["criado_em"].isoformat() == receipt["membership_created_at"],
            "GRANT_AUDIT_MISMATCH")
    member = scope["membership"]
    undone = conn.execute("SELECT id,user_id,alvo_user_id FROM socialmei.auth_auditoria WHERE acao=%s ORDER BY id",
                          (undo,)).fetchall()
    if undone:
        require(len(undone) == 1 and undone[0]["user_id"] == request.actor_id
                and undone[0]["alvo_user_id"] == request.target_user_id and not member,
                "ROLLBACK_STATE_CHANGED")
        require(sorted(row["user_id"] for row in scope["owners"]) == sorted(request.expected_owner_ids),
                "OWNER_SET_CHANGED")
        return {"version": 1, "operation": "remove_added_owner", "workspace_id": request.workspace_id,
                "target_user_id": request.target_user_id, "already_removed": True,
                "plan_sha256": digest([receipt, scope]), "audit_action": undo}
    require(member and member["role"] == "owner" and member["criado_em"] == event["criado_em"],
            "MEMBERSHIP_CHANGED_AFTER_GRANT")
    require(sorted(row["user_id"] for row in scope["owners"] if row["user_id"] != request.target_user_id)
            == sorted(request.expected_owner_ids), "OWNER_SET_CHANGED")
    require(any(row["ativo"] and row["user_id"] != request.target_user_id for row in scope["owners"]),
            "EXISTING_ACTIVE_OWNER_REQUIRED")
    require(not conn.execute("SELECT 1 FROM socialmei.auth_auditoria WHERE alvo_user_id=%s AND id>%s",
                             (request.target_user_id, event["id"])).fetchone(), "TARGET_ACCESS_CHANGED_AFTER_GRANT")
    return {"version": 1, "operation": "remove_added_owner", "workspace_id": request.workspace_id,
            "target_user_id": request.target_user_id,
            "plan_sha256": digest([receipt, scope]), "audit_action": undo}


def inspect_rollback(request, receipt):
    with connect() as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        conn.execute("SET LOCAL statement_timeout='5s'")
        plan = _rollback_plan(conn, request, receipt, _scope(conn, request))
        return {key: value for key, value in plan.items() if key != "audit_action"}


def rollback_owner(request, receipt, approved_plan):
    require(isinstance(approved_plan, str) and len(approved_plan) == 64, "APPROVED_PLAN_REQUIRED")
    with connect() as conn:
        scope = _scope(conn, request, lock=True)
        plan = _rollback_plan(conn, request, receipt, scope)
        if plan.get("already_removed"):
            return {"removed_added_owner": False, "already_removed": True}
        require(plan["plan_sha256"] == approved_plan, "APPROVED_ROLLBACK_CHANGED")
        # Existing tenant FK revokes only this membership's sessions/preferences.
        conn.execute("DELETE FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
                     (request.workspace_id, request.target_user_id))
        _audit(conn, request, plan["audit_action"])
        return {"removed_added_owner": True, "preserved_owner_ids": list(request.expected_owner_ids)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-plan")
    parser.add_argument("--grant-id")
    parser.add_argument("--rollback-receipt")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    try:
        request = AccessRequest(**json.loads(Path(args.request_file).read_text(encoding="utf-8-sig")))
        if args.rollback_receipt:
            receipt = json.loads(Path(args.rollback_receipt).read_text(encoding="utf-8-sig"))
            result = rollback_owner(request, receipt, args.approved_plan) if args.apply else inspect_rollback(request, receipt)
        elif args.apply:
            require(args.grant_id and args.receipt and args.approved_plan, "GRANT_ID_APPROVAL_AND_RECEIPT_REQUIRED")
            require(not Path(args.receipt).exists(), "RECEIPT_OUTPUT_ALREADY_EXISTS")
            grant_owner(request, args.approved_plan, args.grant_id, receipt_path=args.receipt)
            result = {"grant_confirmed": True, "receipt_saved": True}
        else:
            result = inspect_access(request)
        print(json.dumps(result))
    except Exception as error:
        print(json.dumps({"complete": False, "verify_grant_id_before_retry": bool(args.apply),
                          "reason": str(error) if isinstance(error, AccessError) else type(error).__name__}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
