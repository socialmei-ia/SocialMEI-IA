"""Authenticated WAHA reception with an explicitly mounted private registry."""

import hashlib
import hmac
import json
import os
import re
import stat
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException
from types import MappingProxyType

import psycopg
from psycopg.rows import dict_row
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

import settings
from database import connect
from message_enrichment import _append_inbox_message, unique_json_fields, fingerprint

MAX_BODY = 65536
DIRECT = re.compile(r"(?:[0-9]{1,40}@c\.us|[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}@lid)\Z")
router = APIRouter(prefix="/internal/waha", tags=["authenticated WAHA reception"])


@dataclass(frozen=True)
class WahaBinding:
    instance: str
    session: str
    account_id: str = field(repr=False)
    workspace_id: int = field(repr=False)
    channel_id: int = field(repr=False)
    hmac_key: str = field(repr=False)
    revision: int = 1

    def __post_init__(self):
        if (
            not isinstance(self.instance, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", self.instance)
            or self.instance.startswith("fixture-")
            or not isinstance(self.session, str)
            or not re.fullmatch(r"[!-~]{1,160}", self.session)
            or self.session.startswith("fixture-")
            or not isinstance(self.account_id, str)
            or not re.fullmatch(r"[0-9]{1,40}@c\.us", self.account_id)
            or type(self.workspace_id) is not int
            or not 1 <= self.workspace_id <= 2**63 - 1
            or type(self.channel_id) is not int
            or not 1 <= self.channel_id <= 2**63 - 1
            or type(self.revision) is not int
            or not 1 <= self.revision <= 2**63 - 1
            or not isinstance(self.hmac_key, str)
            or not 32 <= len(self.hmac_key.encode()) <= 4096
        ):
            raise ValueError("Registro WAHA inválido.")


@dataclass(frozen=True)
class WahaEvent:
    mid: str = field(repr=False)
    kind: str
    sender: str = field(repr=False)
    recipient: str = field(repr=False)
    occurred_at: datetime
    text: str | None = field(repr=False)
    detail_hash: str | None = field(default=None, repr=False)
    ack: int | None = None
    account_id: str = field(default="", repr=False)

    @property
    def event_key(self):
        return fingerprint(
            ["receipt", self.mid, self.ack]
            if self.kind == "receipt"
            else ["message", self.mid]
        )

    @property
    def fingerprint(self):
        return fingerprint(
            [
                self.mid,
                self.kind,
                self.sender,
                self.recipient,
                None if self.kind == "receipt" else self.occurred_at.isoformat(),
                self.text,
                self.detail_hash,
                self.ack,
            ]
        )

    @property
    def channel(self):
        return "whatsapp"

    @property
    def account_ref(self):
        return "waha:" + self.account_id

    @property
    def contact_ref(self):
        return "waha:" + self.sender

    @property
    def contact_name(self):
        return "Contato do WhatsApp"

    @property
    def external_message_id(self):
        return self.mid


def invalid():
    raise HTTPException(422, "Evento WAHA inválido.")


def _time(value, *, milliseconds=False):
    if type(value) not in (int, Decimal):
        invalid()
    number = Decimal(value)
    if not number.is_finite():
        invalid()
    sign, digits, exponent = number.as_tuple()
    if not any(digits):
        microseconds = 0
    else:
        if sign:
            invalid()
        shift = exponent + (3 if milliseconds else 6)
        if shift < 0:
            cut = -shift
            if cut >= len(digits) or any(digits[-cut:]):
                invalid()
            digits = digits[:-cut]
            shift = 0
        if len(digits) + shift > 18:
            invalid()
        microseconds = int("".join(str(d) for d in digits)) * 10**shift
        if microseconds > 253402300799999999:
            invalid()
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=microseconds
    )


def parse_event(raw, signature, algorithm, binding):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BODY:
        invalid()
    if (
        algorithm != "sha512"
        or not isinstance(signature, str)
        or not re.fullmatch(r"[0-9a-fA-F]{128}", signature)
        or not hmac.compare_digest(
            bytes.fromhex(signature),
            hmac.new(binding.hmac_key.encode(), raw, hashlib.sha512).digest(),
        )
    ):
        raise HTTPException(403, "Autenticação do webhook indisponível.")
    value = None
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_json_fields,
            parse_float=Decimal,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeError, RecursionError, DecimalException):
        pass
    if not isinstance(value, dict) or set(value) - {
        "id",
        "timestamp",
        "event",
        "session",
        "me",
        "payload",
        "engine",
        "environment",
        "metadata",
    }:
        invalid()
    if (
        value.get("session") != binding.session
        or not isinstance(value.get("me"), dict)
        or value["me"].get("id") != binding.account_id
    ):
        invalid()
    if value.get("engine") != "WEBJS":
        invalid()
    if type(value.get("timestamp")) is not int:
        invalid()
    _time(value.get("timestamp"), milliseconds=True)
    event = value.get("event")
    message = value.get("payload")
    if (
        not isinstance(event, str)
        or event not in {"message", "message.any", "message.ack"}
        or not isinstance(message, dict)
    ):
        invalid()
    mid = message.get("id")
    if not isinstance(mid, str) or not re.fullmatch(r"[!-~]{1,1024}", mid):
        invalid()
    from_me = message.get("fromMe")
    if type(from_me) is not bool:
        invalid()
    sender = message.get("from")
    recipient = message.get("to", "") if event == "message.ack" else message.get("to")
    if (
        not isinstance(sender, str)
        or not isinstance(recipient, str)
        or len(sender) > 255
        or len(recipient) > 255
        or not re.fullmatch(r"[!-~]{1,255}", sender)
        or (
            not re.fullmatch(r"[!-~]{1,255}", recipient)
            and not (event == "message.ack" and recipient == "")
        )
    ):
        invalid()
    occurred = (
        _time(value["timestamp"], milliseconds=True)
        if event == "message.ack" and "timestamp" not in message
        else _time(message.get("timestamp"))
    )
    if event == "message.ack":
        ack = message.get("ack")
        if type(ack) is not int or not -1 <= ack <= 4:
            invalid()
        return WahaEvent(
            mid,
            "receipt",
            sender,
            recipient,
            occurred,
            None,
            ack=ack,
            account_id=binding.account_id,
        )
    if type(message.get("hasMedia")) is not bool:
        invalid()
    kind = "echo" if from_me else "message"
    if not from_me and (
        not DIRECT.fullmatch(sender) or message.get("participant") is not None
    ):
        kind = "unsupported"
    if not from_me and kind == "message" and recipient != binding.account_id:
        invalid()
    if (
        message["hasMedia"]
        or message.get("type", "chat") != "chat"
        or not isinstance(message.get("body"), str)
    ):
        kind = "unsupported" if not from_me else "echo"
    text = message.get("body") if kind == "message" else None
    if text is not None:
        try:
            valid = (
                bool(text.strip())
                and len(text.encode()) <= 8192
                and not any(ord(c) < 32 and c not in "\t\n\r" for c in text)
            )
        except UnicodeError:
            valid = False
        if not valid:
            invalid()
    details = None
    if kind == "unsupported":
        details = hashlib.sha256(
            json.dumps(
                {k: v for k, v in message.items() if k != "_data"},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()
    return WahaEvent(
        mid,
        kind,
        sender,
        recipient,
        occurred,
        text,
        details,
        account_id=binding.account_id,
    )


class WahaIngressService:
    def __init__(self, registry):
        if (
            not isinstance(registry, dict)
            or not registry
            or any(
                not isinstance(v, WahaBinding) or k != v.instance
                for k, v in registry.items()
            )
        ):
            raise ValueError("Registro WAHA inválido.")
        bindings = list(registry.values())
        if (
            len({b.channel_id for b in bindings}) != len(bindings)
            or len({b.hmac_key for b in bindings}) != len(bindings)
            or len({b.account_id for b in bindings}) != len(bindings)
        ):
            raise ValueError("Registro WAHA conflitante.")
        self._registry = MappingProxyType(dict(registry))

    @property
    def registry(self):
        return self._registry

    def _channel(self, conn, binding):
        row = conn.execute(
            "SELECT versao FROM socialmei.crm_canais WHERE workspace_id=%s AND id=%s AND instancia=%s AND sessao=%s AND identificador_conta=%s AND ingress_provisioned AND ativo AND NOT envio_habilitado AND versao=%s FOR SHARE",
            (
                binding.workspace_id,
                binding.channel_id,
                binding.instance,
                binding.session,
                binding.account_id,
                binding.revision,
            ),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Vínculo WAHA indisponível.")
        return row

    def receive(self, instance, raw, signature, algorithm):
        binding = self.registry.get(instance)
        if binding is None:
            raise HTTPException(403, "Autenticação do webhook indisponível.")
        incoming = parse_event(raw, signature, algorithm, binding)
        if settings.waha_ingress_team_pilot_enabled() and (
            len(self.registry) != 1
            or binding.workspace_id != 1
            or binding.instance != "socialmei-equipe-piloto"
            or not binding.account_id.endswith("5976@c.us")
        ):
            raise HTTPException(503, "Vínculo WAHA fora do piloto autorizado.")
        if not settings.waha_ingress_enabled():
            raise HTTPException(503, "Recepção WAHA não habilitada.")
        failed = False
        result = None
        try:
            with connect() as conn:
                conn.row_factory = dict_row
                conn.execute("SET LOCAL lock_timeout='3s'")
                conn.execute("SET LOCAL statement_timeout='10s'")
                conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("waha-ingress:" + binding.account_id,),
                )
                if not conn.execute(
                    "SELECT id FROM socialmei.workspaces WHERE id=%s FOR UPDATE",
                    (binding.workspace_id,),
                ).fetchone():
                    raise HTTPException(404, "Vínculo WAHA indisponível.")
                self._channel(conn, binding)
                old = conn.execute(
                    "SELECT fingerprint FROM socialmei.crm_eventos_canal WHERE waha_account_snapshot=%s AND waha_event_key=%s",
                    (binding.account_id, incoming.event_key),
                ).fetchone()
                if old:
                    if old["fingerprint"] != incoming.fingerprint:
                        raise HTTPException(
                            409, "Identidade de evento já usada com conteúdo diferente."
                        )
                    result = {"processed": 0, "ignored": 0, "duplicates": 1}
                else:
                    message = None
                    if incoming.kind == "message":
                        message = _append_inbox_message(
                            conn,
                            binding.workspace_id,
                            incoming,
                            incoming.fingerprint,
                            origin="waha",
                        )
                    status = "processado" if message else "ignorado"
                    conn.execute(
                        "INSERT INTO socialmei.crm_eventos_canal(workspace_id,canal_id,chave_evento,tipo,fingerprint,mensagem_externa_id,status,ocorrida_em,processado_em,waha_account_snapshot,waha_event_key,inbox_message_id,inbox_origin) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,'waha')",
                        (
                            binding.workspace_id,
                            binding.channel_id,
                            incoming.event_key,
                            incoming.kind,
                            incoming.fingerprint,
                            incoming.mid,
                            status,
                            incoming.occurred_at,
                            binding.account_id,
                            incoming.event_key,
                            message["message_id"] if message else None,
                        ),
                    )
                    result = {
                        "processed": int(message is not None),
                        "ignored": int(message is None),
                        "duplicates": 0,
                    }
        except (psycopg.Error, RuntimeError):
            failed = True
        if failed:
            raise HTTPException(503, "Recepção WAHA temporariamente indisponível.")
        return result


def waha_service():
    """Reload operator-owned bindings; no pairing, sender or implicit defaults."""
    try:
        path = os.getenv("SOCIALMEI_WAHA_REGISTRY_FILE", "")
        if not path or not os.path.isabs(path) or not hasattr(os, "O_NOFOLLOW"):
            raise ValueError()
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        )
        with os.fdopen(descriptor, "rb") as source:
            metadata = os.fstat(source.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}
                or metadata.st_uid not in {0, os.geteuid()}
                or not 1 <= metadata.st_size <= MAX_BODY
            ):
                raise ValueError()
            raw = source.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError()
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_json_fields,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "bindings"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or not isinstance(value["bindings"], list)
            or not 1 <= len(value["bindings"]) <= 100
        ):
            raise ValueError()
        if settings.waha_ingress_team_pilot_enabled() and metadata.st_uid != 0:
            raise ValueError()
        bindings = []
        for entry in value["bindings"]:
            if not isinstance(entry, dict):
                raise ValueError()
            bindings.append(WahaBinding(**entry))
        registry = {binding.instance: binding for binding in bindings}
        if len(registry) != len(bindings):
            raise ValueError()
        return WahaIngressService(registry)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        # File paths, parser diagnostics, account IDs and HMACs remain private.
        raise HTTPException(503, "Recepção WAHA ainda não configurada.") from None


@router.post("/{instance}/webhook")
async def webhook(
    instance: str, request: Request, service: WahaIngressService = Depends(waha_service)
):
    if not settings.waha_ingress_enabled():
        raise HTTPException(503, "Recepção WAHA não habilitada.")
    if (
        request.query_params
        or len(request.headers.getlist("content-type")) != 1
        or request.headers.get("content-type", "").split(";", 1)[0].lower()
        != "application/json"
    ):
        invalid()
    signatures = request.headers.getlist("x-webhook-hmac")
    algorithms = request.headers.getlist("x-webhook-hmac-algorithm")
    if len(signatures) != 1 or len(algorithms) != 1:
        raise HTTPException(403, "Autenticação do webhook indisponível.")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY:
            invalid()
        body.extend(chunk)
    return await run_in_threadpool(
        service.receive, instance, bytes(body), signatures[0], algorithms[0]
    )
