"""Offline contract for a future authenticated FastAPI -> n8n worker.

There is deliberately NO webhook URL, HTTP request, token store, live router or
direct Meta publisher in this module. The caller must authorize workspace and
account server-side before preparing a job, and own a durable asset ledger.
"""
import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

SCHEMA = "socialmei.instagram.publish.v1"
JOB_FIELDS = frozenset({
    "schema", "publication_id", "operation_id", "workspace_id",
    "linked_account_id", "format", "feed_mode", "caption", "media", "scheduled_for",
})
SAFE_MIME = {
    "feed": {"image/jpeg", "image/png"},
    "story": {"image/jpeg", "image/png", "video/mp4"},
    "reel": {"video/mp4"},
}


def _uuid(value, field):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{field} precisa ser um UUID válido.") from None


def _media(items, kind, mode):
    if not isinstance(items, list) or not 1 <= len(items) <= 10:
        raise ValueError("Informe entre uma e dez mídias.")
    if kind != "feed" and len(items) != 1:
        raise ValueError("Story e Reel exigem uma mídia.")
    if kind == "feed" and (
        (len(items) == 1 and mode != "single")
        or (len(items) > 1 and mode not in {"carousel", "separate"})
    ):
        raise ValueError("Modo do Feed incompatível com a quantidade de mídias.")
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"asset_id", "mime"}:
            raise ValueError("Manifesto de mídia inválido.")
        asset = _uuid(item["asset_id"], "asset_id")
        if asset in seen or item["mime"] not in SAFE_MIME[kind]:
            raise ValueError("Mídia duplicada ou incompatível.")
        seen.add(asset)
        result.append({"asset_id": asset, "mime": item["mime"]})
    return result


def build_job(*, publication_id, operation_id, workspace_id, linked_account_id,
              kind, feed_mode, caption, media, scheduled_for=None):
    """Prepare an opaque handoff; account and assets must already be authorized.

    In particular, linked_account_id is an internal UUID, NOT Meta's IG user ID.
    It must be resolved in a server-side trusted account binding, never from
    user-supplied IDs. This function does not prove such binding exists.
    """
    if kind not in SAFE_MIME:
        raise ValueError("Tipo de publicação não suportado.")
    if kind != "feed" and feed_mode is not None:
        raise ValueError("Somente Feed possui modo de múltiplas mídias.")
    if not isinstance(workspace_id, int) or isinstance(workspace_id, bool) or workspace_id < 1:
        raise ValueError("Workspace inválido.")
    if not isinstance(caption, str) or len(caption) > 2200:
        raise ValueError("Legenda inválida.")
    manifest = _media(media, kind, feed_mode)
    moment = None
    if scheduled_for is not None:
        if not isinstance(scheduled_for, datetime) or scheduled_for.tzinfo is None:
            raise ValueError("Agendamento exige data e fuso horário.")
        when = scheduled_for.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)
        if not now + timedelta(minutes=1) < when < now + timedelta(days=60):
            raise ValueError("Agendamento fora do intervalo permitido.")
        moment = when.isoformat().replace("+00:00", "Z")
    return {
        "schema": SCHEMA,
        "publication_id": _uuid(publication_id, "publication_id"),
        "operation_id": _uuid(operation_id, "operation_id"),
        "workspace_id": workspace_id,
        "linked_account_id": _uuid(linked_account_id, "linked_account_id"),
        "format": kind,
        "feed_mode": feed_mode if kind == "feed" else None,
        "caption": caption,
        "media": manifest,
        "scheduled_for": moment,
    }


def serialize(job):
    """Stable wire encoding so both parties sign identical UTF-8 bytes."""
    if not isinstance(job, dict) or set(job) != JOB_FIELDS or job.get("schema") != SCHEMA:
        raise ValueError("Esquema incompatível ou campos não permitidos.")
    return json.dumps(
        job, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def sign(secret, body, *, timestamp=None):
    """Produce headers to be checked *before* parsing JSON at n8n ingress."""
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("Segredo de serviço inválido.")
    if not isinstance(body, bytes):
        raise ValueError("Corpo deve ser bytes.")
    issued = int(time.time()) if timestamp is None else int(timestamp)
    token = hmac.new(secret, str(issued).encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"X-SocialMEI-Timestamp": str(issued), "X-SocialMEI-Signature": "sha256=" + token}


def verify(secret, body, headers, *, now=None, tolerance=300):
    """Offline verification helper; real worker also needs replay/idempotency store."""
    if not isinstance(headers, dict) or not isinstance(body, bytes):
        return False
    supplied_time = headers.get("X-SocialMEI-Timestamp", "")
    supplied_sig = headers.get("X-SocialMEI-Signature", "")
    if not isinstance(supplied_time, str) or not re.fullmatch(r"[0-9]{10,11}", supplied_time):
        return False
    if not isinstance(supplied_sig, str) or not re.fullmatch(r"sha256=[a-f0-9]{64}", supplied_sig):
        return False
    clock = int(time.time()) if now is None else int(now)
    issued = int(supplied_time)
    if abs(clock - issued) > tolerance:
        return False
    try:
        expected = sign(secret, body, timestamp=issued)["X-SocialMEI-Signature"]
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(expected, supplied_sig)
