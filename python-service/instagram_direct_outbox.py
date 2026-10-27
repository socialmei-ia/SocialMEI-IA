"""Approved Direct replies with durable attempts and no installed transport."""

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, StrictInt, field_validator
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

import settings
from account_auth import COOKIE, Strict, current, digest, require_enabled
from database import connect
from instagram_meta_adapter import InstagramAdapter, ProviderError
from instagram_persistent_oauth import _authorize, _lock
from instagram_token_vault import TokenBinding, TokenVault, VaultError

router = APIRouter(prefix="/api/v1/instagram/direct", tags=["isolated Direct outbox"])
SCOPES = {"instagram_business_basic", "instagram_business_manage_messages"}


def outbox_service(request: Request = None):
    from instagram_runtime import runtime_service
    return runtime_service(request, "direct")


def reply_text(text):
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text.encode("utf-8")) > 1000
        or any(
            (ord(c) < 32 and c not in "\t\n\r") or 0x7F <= ord(c) <= 0x9F for c in text
        )
    ):
        raise ValueError("Resposta deve conter até 1000 bytes UTF-8.")
    return text


class Operation(Strict):
    operation_id: UUID


class DraftInput(Operation):
    source_message_id: StrictInt = Field(ge=1, le=9007199254740991)
    text: str
    _text = field_validator("text")(reply_text)


class EditInput(DraftInput):
    expected_revision: StrictInt = Field(ge=1)


class RevisionInput(Operation):
    expected_revision: StrictInt = Field(ge=1)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def view(row):
    return {
        key: (str(row[key]) if key in {"id", "connection_id"} else
              row[key].isoformat() if key in {"created_at", "updated_at"} else row[key])
        for key in (
            "id",
            "conversation_id",
            "source_message_id",
            "connection_id",
            "text",
            "revision",
            "status",
            "attempts",
            "last_error",
            "provider_message_id",
            "created_at",
            "updated_at",
        )
    }


def event(conn, row, action, actor=None):
    conn.execute(
        "INSERT INTO socialmei.ig_direct_events(workspace_id,job_id,actor_id,action,revision) VALUES(%s,%s,%s,%s,%s)",
        (row["workspace_id"], row["id"], actor, action, row["revision"]),
    )


class InstagramDirectService:
    def __init__(self, *, adapter, vault, allow_dispatch=True):
        if not isinstance(adapter, InstagramAdapter) or not isinstance(
            vault, TokenVault
        ):
            raise ValueError("Dependências Direct indisponíveis.")
        if type(allow_dispatch) is not bool:
            raise ValueError("Permissão de despacho inválida.")
        self.allow_dispatch = allow_dispatch
        self.adapter, self.vault = adapter, vault

    def source(self, conn, workspace, source_id):
        row = conn.execute(
            "SELECT m.id,m.conversation_id,c.account_ref,c.contact_ref,e.connection_id,e.external_account_id,"
            "LEAST(m.occurred_at,e.received_at) AS window_start FROM socialmei.me_messages m "
            "JOIN socialmei.me_conversations c ON c.workspace_id=m.workspace_id AND c.id=m.conversation_id "
            "JOIN socialmei.ig_meta_ingress_events e ON e.workspace_id=m.workspace_id AND e.message_id=m.id "
            "WHERE m.workspace_id=%s AND m.id=%s AND m.origin='instagram' AND c.origin='instagram' "
            "AND e.kind='message' AND e.status='processed'",
            (workspace, source_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Mensagem Instagram validada não encontrada.")
        if row["window_start"] + timedelta(hours=24) <= datetime.now(timezone.utc):
            raise HTTPException(409, "Janela normal de resposta encerrada.")
        if row["account_ref"] != "instagram:" + row[
            "external_account_id"
        ] or not re.fullmatch(r"instagram:[0-9]{1,40}", row["contact_ref"]):
            raise HTTPException(409, "Destino Instagram incompatível.")
        linked = conn.execute(
            "SELECT * FROM socialmei.ig_meta_connections WHERE workspace_id=%s AND id=%s AND external_account_id=%s AND status='connected' AND expires_at>NOW() FOR SHARE",
            (workspace, row["connection_id"], row["external_account_id"]),
        ).fetchone()
        if not linked or not SCOPES.issubset(linked["scopes"]):
            raise HTTPException(409, "Conexão Instagram indisponível para resposta.")
        return row, linked

    def _authorize(self, conn, user, session, *, runner=False):
        require_enabled()
        if not (settings.instagram_direct_isolated_enabled() or settings.instagram_runtime_enabled()):
            raise HTTPException(503, "Direct isolado não habilitado.")
        _lock(conn, user["workspace_id"])
        conn.execute(
            "SELECT 1 FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s FOR SHARE",
            (user["workspace_id"], user["id"]),
        )
        _authorize(conn, user, session, manage=runner)
        role = conn.execute(
            "SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
            (user["workspace_id"], user["id"]),
        ).fetchone()
        if not role or role["role"] not in {"owner", "admin", "member"}:
            raise HTTPException(403, "Acesso somente leitura.")

    def _old_operation(self, conn, user, operation, expected):
        old = conn.execute(
            "SELECT fingerprint,response FROM socialmei.ig_direct_operations WHERE workspace_id=%s AND operation_id=%s",
            (user["workspace_id"], operation),
        ).fetchone()
        if old and old["fingerprint"] != expected:
            raise HTTPException(409, "Operação já usada com outro conteúdo.")
        return old["response"] if old else None

    def mutate(self, user, session, action, payload, job_id=None):
        data = payload.model_dump(mode="json")
        operation = data.pop("operation_id")
        key = fingerprint(
            [user["id"], session, action, str(job_id) if job_id else None, data]
        )
        with connect() as conn:
            conn.row_factory = dict_row
            self._authorize(conn, user, session)
            old = self._old_operation(conn, user, operation, key)
            if old:
                return old
            row = None
            if job_id:
                row = conn.execute(
                    "SELECT * FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s FOR UPDATE",
                    (user["workspace_id"], job_id),
                ).fetchone()
                if not row:
                    raise HTTPException(404, "Resposta não encontrada neste negócio.")
                if row["revision"] != payload.expected_revision:
                    raise HTTPException(
                        409, "Resposta mudou; atualize antes de continuar."
                    )
                if row["status"] not in {"draft", "approved", "retry_ready"}:
                    raise HTTPException(409, "Resposta já iniciada ou encerrada.")
            if action in {"created", "edited"}:
                source, linked = self.source(
                    conn, user["workspace_id"], payload.source_message_id
                )
                identity = [
                    payload.source_message_id,
                    source["conversation_id"],
                    str(linked["id"]),
                    linked["external_account_id"],
                    source["contact_ref"],
                    payload.text,
                ]
                content_key = fingerprint(identity)
                if action == "created":
                    row = conn.execute(
                        "INSERT INTO socialmei.ig_direct_jobs(workspace_id,id,conversation_id,source_message_id,connection_id,external_account_id,recipient_id,text,fingerprint,created_by,created_session) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                        (
                            user["workspace_id"],
                            uuid4(),
                            source["conversation_id"],
                            payload.source_message_id,
                            linked["id"],
                            linked["external_account_id"],
                            source["contact_ref"].split(":")[1],
                            payload.text,
                            content_key,
                            user["id"],
                            session,
                        ),
                    ).fetchone()
                else:
                    if row["attempts"]:
                        raise HTTPException(
                            409, "Tentativa existente exige outra resposta."
                        )
                    row = conn.execute(
                        "UPDATE socialmei.ig_direct_jobs SET conversation_id=%s,source_message_id=%s,connection_id=%s,external_account_id=%s,recipient_id=%s,text=%s,fingerprint=%s,revision=revision+1,status='draft',approved_by=NULL,approved_session=NULL,approved_revision=NULL,approved_fingerprint=NULL,updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING *",
                        (
                            source["conversation_id"],
                            payload.source_message_id,
                            linked["id"],
                            linked["external_account_id"],
                            source["contact_ref"].split(":")[1],
                            payload.text,
                            content_key,
                            user["workspace_id"],
                            job_id,
                        ),
                    ).fetchone()
            elif action == "approved":
                if row["status"] != "draft":
                    raise HTTPException(409, "Somente rascunhos podem ser aprovados.")
                self.source(conn, user["workspace_id"], row["source_message_id"])
                row = conn.execute(
                    "UPDATE socialmei.ig_direct_jobs SET status='approved',approved_by=%s,approved_session=%s,approved_revision=revision,approved_fingerprint=fingerprint,updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING *",
                    (user["id"], session, user["workspace_id"], job_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "UPDATE socialmei.ig_direct_jobs SET status='cancelled',updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING *",
                    (user["workspace_id"], job_id),
                ).fetchone()
            event(conn, row, action, user["id"])
            result = view(row)
            conn.execute(
                "INSERT INTO socialmei.ig_direct_operations(workspace_id,operation_id,fingerprint,response) VALUES(%s,%s,%s,%s)",
                (user["workspace_id"], operation, key, Jsonb(result)),
            )
        return result

    def read(self, user, session):
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session, manage=False)
            rows = conn.execute(
                "SELECT * FROM socialmei.ig_direct_jobs WHERE workspace_id=%s ORDER BY created_at DESC,id DESC LIMIT 100",
                (user["workspace_id"],),
            ).fetchall()
        return {"items": [view(row) for row in rows]}

    def history(self, user, session, job_id):
        with connect() as conn:
            conn.row_factory = dict_row
            _authorize(conn, user, session, manage=False)
            if not conn.execute(
                "SELECT 1 FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s",
                (user["workspace_id"], job_id),
            ).fetchone():
                raise HTTPException(404, "Resposta não encontrada neste negócio.")
            rows = conn.execute(
                "SELECT action,revision,created_at FROM socialmei.ig_direct_events WHERE workspace_id=%s AND job_id=%s ORDER BY id DESC LIMIT 100",
                (user["workspace_id"], job_id),
            ).fetchall()
        return {"items": rows}

    def _destination(self, conn, user, row):
        _authorize(
            conn,
            {"id": row["approved_by"], "workspace_id": user["workspace_id"]},
            row["approved_session"],
            manage=False,
        )
        role = conn.execute(
            "SELECT role FROM socialmei.workspace_members WHERE workspace_id=%s AND user_id=%s",
            (user["workspace_id"], row["approved_by"]),
        ).fetchone()
        if not role or role["role"] not in {"owner", "admin", "member"}:
            raise HTTPException(403, "Aprovação indisponível.")
        source, linked = self.source(
            conn, user["workspace_id"], row["source_message_id"]
        )
        expected = fingerprint(
            [
                row["source_message_id"],
                source["conversation_id"],
                str(linked["id"]),
                linked["external_account_id"],
                source["contact_ref"],
                row["text"],
            ]
        )
        if (
            row["connection_id"] != linked["id"]
            or row["external_account_id"] != linked["external_account_id"]
            or row["conversation_id"] != source["conversation_id"]
            or row["recipient_id"] != source["contact_ref"].split(":")[1]
            or row["fingerprint"] != expected
            or row["approved_fingerprint"] != expected
            or row["approved_revision"] != row["revision"]
        ):
            raise HTTPException(409, "Destino ou aprovação mudou.")
        credential = None
        try:
            credential = self.vault.open(
                linked["encrypted_token"],
                TokenBinding(
                    user["workspace_id"],
                    linked["id"],
                    linked["external_account_id"],
                ),
            )
        except VaultError:
            pass
        if credential is None:
            raise HTTPException(503, "Credencial segura indisponível.")
        return (
            credential,
            linked["external_account_id"],
            source["contact_ref"].split(":")[1],
        )

    def _lock_job(self, conn, user, job_id):
        # Lock the approver membership/session before its FK-referencing job row.
        snapshot = conn.execute(
            "SELECT * FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s",
            (user["workspace_id"], job_id),
        ).fetchone()
        expired_dispatch = bool(
            snapshot
            and snapshot["status"] == "dispatching"
            and snapshot["lease_until"] <= datetime.now(timezone.utc)
        )
        if snapshot and snapshot["approved_by"] is not None and not expired_dispatch:
            self._authorize(
                conn,
                {"id": snapshot["approved_by"], "workspace_id": user["workspace_id"]},
                snapshot["approved_session"],
            )
        return conn.execute(
            "SELECT * FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s FOR UPDATE",
            (user["workspace_id"], job_id),
        ).fetchone()

    def _dispatch(self, user, session, job_id, claim):
        with connect() as conn:
            conn.row_factory = dict_row
            self._authorize(conn, user, session, runner=True)
            row = self._lock_job(conn, user, job_id)
            if not row or row["status"] != "dispatching" or row["claim_token"] != claim:
                raise HTTPException(409, "Tentativa indisponível.")
            if row["lease_until"] <= datetime.now(timezone.utc):
                raise ProviderError(outcome_unknown=True)
            credential, account, recipient = self._destination(conn, user, row)
            try:
                return self.adapter.send_direct(
                    credential, account, recipient, row["text"]
                )
            finally:
                credential = None

    def run(self, user, session, job_id, expected_revision=None):
        if not self.allow_dispatch:
            raise HTTPException(503, "Envio externo não autorizado neste ambiente.")
        credential = None
        with connect() as conn:
            conn.row_factory = dict_row
            self._authorize(conn, user, session, runner=True)
            row = self._lock_job(conn, user, job_id)
            if not row:
                raise HTTPException(404, "Resposta não encontrada neste negócio.")
            if expected_revision is not None and row['revision'] != expected_revision:
                raise HTTPException(409, "A resposta mudou. Revise novamente antes de enviar.")
            if row["status"] == "dispatching" and row["lease_until"] <= datetime.now(
                timezone.utc
            ):
                conn.execute(
                    "UPDATE socialmei.ig_direct_attempts SET status='uncertain',finished_at=NOW() WHERE workspace_id=%s AND job_id=%s AND claim_token=%s AND status='dispatching'",
                    (user["workspace_id"], job_id, row["claim_token"]),
                )
                row = conn.execute(
                    "UPDATE socialmei.ig_direct_jobs SET status='uncertain',last_error='lease_expired',claim_token=NULL,lease_until=NULL,updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING *",
                    (user["workspace_id"], job_id),
                ).fetchone()
                event(conn, row, "uncertain", user["id"])
                return view(row)
            if row["status"] not in {"approved", "retry_ready"} or row["attempts"] >= 3:
                raise HTTPException(409, "Resposta indisponível para tentativa.")
            if row["run_after"] and row["run_after"] > datetime.now(timezone.utc):
                raise HTTPException(409, "Aguarde o intervalo de nova tentativa.")
            self._destination(conn, user, row)
            claim = uuid4()
            row = conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET status='dispatching',attempts=attempts+1,claim_token=%s,lease_until=NOW()+INTERVAL '60 seconds',last_error=NULL,updated_at=NOW() WHERE workspace_id=%s AND id=%s RETURNING *",
                (claim, user["workspace_id"], job_id),
            ).fetchone()
            conn.execute(
                "INSERT INTO socialmei.ig_direct_attempts(workspace_id,job_id,attempt,claim_token,status) VALUES(%s,%s,%s,%s,'dispatching')",
                (user["workspace_id"], job_id, row["attempts"], claim),
            )
            event(conn, row, "dispatching", user["id"])
        # Claim is committed. Any process loss beyond here must never reopen this send.
        state, code, mid, delay = "uncertain", "outcome_unknown", None, None
        try:
            receipt = self._dispatch(user, session, job_id, claim)
            state, code, mid = "confirmed", None, receipt["message_id"]
        except HTTPException as error:
            state, code = "failed", "rejected"
        except ProviderError as error:
            if not error.outcome_unknown:
                if error.status_code == 429:
                    state = "retry_ready" if row["attempts"] < 3 else "failed"
                    code = "rate_limited"
                    delay = error.retry_after or 60
                else:
                    state, code = "failed", "rejected"
        except Exception:
            pass
        finally:
            credential = None
        with connect() as conn:
            conn.row_factory = dict_row
            updated = conn.execute(
                "UPDATE socialmei.ig_direct_jobs SET status=%s,last_error=%s,provider_message_id=%s,claim_token=NULL,lease_until=NULL,run_after=%s,updated_at=NOW() WHERE workspace_id=%s AND id=%s AND status='dispatching' AND claim_token=%s RETURNING *",
                (
                    state,
                    code,
                    mid,
                    (
                        datetime.now(timezone.utc) + timedelta(seconds=delay)
                        if delay
                        else None
                    ),
                    user["workspace_id"],
                    job_id,
                    claim,
                ),
            ).fetchone()
            if updated:
                attempt_status = (
                    "confirmed"
                    if state == "confirmed"
                    else (
                        "uncertain"
                        if state == "uncertain"
                        else "rate_limited" if code == "rate_limited" else "rejected"
                    )
                )
                conn.execute(
                    "UPDATE socialmei.ig_direct_attempts SET status=%s,finished_at=NOW() WHERE workspace_id=%s AND job_id=%s AND claim_token=%s AND status='dispatching'",
                    (attempt_status, user["workspace_id"], job_id, claim),
                )
                event(conn, updated, state)
                result = view(updated)
            else:
                result = view(
                    conn.execute(
                        "SELECT * FROM socialmei.ig_direct_jobs WHERE workspace_id=%s AND id=%s",
                        (user["workspace_id"], job_id),
                    ).fetchone()
                )
        return result


def identity(request):
    require_enabled()
    if not (settings.instagram_direct_isolated_enabled() or settings.instagram_runtime_enabled()):
        raise HTTPException(503, "Direct isolado não habilitado.")
    return current(), digest(request.cookies.get(COOKIE, ""))


@router.get("/jobs")
def jobs(request: Request, service: InstagramDirectService = Depends(outbox_service)):
    return service.read(*identity(request))


@router.post("/jobs")
def create(
    payload: DraftInput,
    request: Request,
    service: InstagramDirectService = Depends(outbox_service),
):
    return service.mutate(*identity(request), "created", payload)


@router.put("/jobs/{job_id}")
def edit(
    job_id: UUID,
    payload: EditInput,
    request: Request,
    service: InstagramDirectService = Depends(outbox_service),
):
    return service.mutate(*identity(request), "edited", payload, job_id)


@router.post("/jobs/{job_id}/approve")
def approve(
    job_id: UUID,
    payload: RevisionInput,
    request: Request,
    service: InstagramDirectService = Depends(outbox_service),
):
    return service.mutate(*identity(request), "approved", payload, job_id)


@router.post("/jobs/{job_id}/cancel")
def cancel(
    job_id: UUID,
    payload: RevisionInput,
    request: Request,
    service: InstagramDirectService = Depends(outbox_service),
):
    return service.mutate(*identity(request), "cancelled", payload, job_id)


class DispatchInput(Strict):
    # Existing integrations may omit it; the native human-review UI always binds it.
    expected_revision: StrictInt | None = Field(default=None, ge=1)


@router.post("/jobs/{job_id}/run")
def run(
    job_id: UUID,
    payload: DispatchInput,
    request: Request,
    service: InstagramDirectService = Depends(outbox_service),
):
    return service.run(*identity(request), job_id, expected_revision=payload.expected_revision)


@router.get("/jobs/{job_id}/history")
def history(
    job_id: UUID,
    request: Request,
    service: InstagramDirectService = Depends(outbox_service),
):
    return service.history(*identity(request), job_id)
