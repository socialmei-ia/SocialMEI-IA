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
from psycopg.types.json import Jsonb
from whatsapp_catalog_navigation import valid_token
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
    engine: str = 'WEBJS'  # Explicit per-channel cutover; legacy registries stay WEBJS.
    ingress_after: int = 0

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
            or self.engine not in {'WEBJS', 'GOWS'}
            or type(self.ingress_after) is not int
            or not 0 <= self.ingress_after <= 4102444800
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
    selection: str | None = field(default=None, repr=False)
    media_kind: str | None = field(default=None, repr=False)

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
                "unsupported" if self.kind == "media" else self.kind,
                self.sender,
                self.recipient,
                None if self.kind == "receipt" else self.occurred_at.isoformat(),
                None if self.kind == "media" else self.text,
                self.detail_hash,
                self.ack,
            ] + ([self.selection] if self.selection else [])
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
        if re.fullmatch(r"[1-9][0-9]{7,14}@c\.us", self.sender):
            return "+" + self.sender.removesuffix("@c.us")
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


def _gows_list_choices(raw_data):
    """Read the observed Go protobuf fields, including the optional raw mirror."""
    if not isinstance(raw_data, dict):
        return []
    choices = []
    for name in ("Message", "RawMessage"):
        message = raw_data.get(name)
        if not isinstance(message, dict) or "listResponseMessage" not in message:
            continue
        selection = message["listResponseMessage"]
        reply = selection.get("singleSelectReply") if isinstance(selection, dict) else None
        value = reply.get("selectedRowID") if isinstance(reply, dict) else None
        choices.append(value if isinstance(value, str) and (value in {"0", "1", "2", "3", "4", "5"} or valid_token(value)) else None)
    return choices


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
    if value.get("engine") != binding.engine:
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
    # GOWS emits null or omits the destination of private messages. Infer only for a
    # signed inbound direct message bound to this authenticated account.
    # WEBJS and explicitly conflicting destinations remain strictly validated.
    if (
        recipient is None
        and binding.engine == "GOWS"
        and event in {"message", "message.any"}
        and not from_me
        and isinstance(sender, str)
        and DIRECT.fullmatch(sender)
        and message.get("participant") is None
    ):
        recipient = binding.account_id
    elif (
        recipient is None
        and binding.engine == "GOWS"
        and from_me
        and event in {"message", "message.any"}
    ):
        # Outgoing copies are echo-only and never authorize a new send.
        recipient = ""
    if (
        not isinstance(sender, str)
        or not isinstance(recipient, str)
        or len(sender) > 255
        or len(recipient) > 255
        or not re.fullmatch(r"[!-~]{1,255}", sender)
        or (
            not re.fullmatch(r"[!-~]{1,255}", recipient)
            and not ((event == "message.ack" or (binding.engine == "GOWS" and from_me)) and recipient == "")
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
    # SM_WA_INBOUND_MEDIA_V1
    if (kind == "message" and message["hasMedia"]
            and binding.engine == "GOWS"
            and binding.workspace_id == 60 and binding.channel_id == 3):
        mt = message.get("type", "chat")
        media = message.get("media")
        mime = str(media.get("mimetype", "")).lower().split(";")[0].strip() if isinstance(media, dict) else ""
        mk = {"audio":"audio","ptt":"audio","voice":"audio","image":"imagem","document":"documento"}.get(mt) if isinstance(mt,str) else None

        if mt == "chat":
            mk = ("audio" if mime.startswith("audio/") else
                  "imagem" if mime.startswith("image/") else
                  "documento" if mime == "application/pdf" else None)

        if mk:
            details = hashlib.sha256(json.dumps(
                {k:v for k,v in message.items() if k != "_data"},
                sort_keys=True,separators=(",",":"),default=str
            ).encode()).hexdigest()

            return WahaEvent(
                mid,"media",sender,recipient,occurred,
                {"audio":"Áudio recebido","imagem":"Imagem recebida","documento":"Documento recebido"}[mk],
                details,account_id=binding.account_id,media_kind=mk
            )

    selection_token = None
    text = message.get("body")
    message_type = message.get("type", "chat")
    native_choices = _gows_list_choices(message.get("_data")) if binding.engine == "GOWS" else []
    if native_choices:
        if "type" in message and message_type != "list_response":
            native_choices = [None]
        message_type = "list_response"
    if isinstance(message_type, str) and message_type in {"buttons_response", "list_response"}:
        raw_data = message.get("_data")
        raw_data = raw_data if isinstance(raw_data, dict) else {}
        selection = raw_data.get("listResponse")
        selection = selection if isinstance(selection, dict) else {}
        reply = selection.get("singleSelectReply")
        reply = reply if isinstance(reply, dict) else {}
        choices = [
            message.get("selectedButtonId"), message.get("selectedRowId"),
            raw_data.get("selectedButtonId"), reply.get("selectedRowId"),
        ]
        choices = [value for value in choices if value is not None] + native_choices
        text = choices[0] if choices else None
        if not isinstance(text, str) or (text not in {"0", "1", "2", "3", "4", "5", "9"} and not (binding.engine == "GOWS" and native_choices and valid_token(text))) or any(value != text for value in choices):
            text = None
        elif text == "9":
            text = "5"
        elif valid_token(text):
            selection_token = text
            text = message.get("body") or "Opção selecionada"
    if (
        message["hasMedia"]
        or not isinstance(message_type, str)
        or message_type not in {"chat", "buttons_response", "list_response"}
        or not isinstance(text, str)
    ):
        kind = "unsupported" if not from_me else "echo"
    text = text if kind == "message" else None
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
        selection=selection_token,
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
            or not settings.waha_pilot_binding_allowed(binding.workspace_id,binding.channel_id,
                binding.instance,binding.session,binding.account_id,binding.revision,binding.engine)
        ):
            raise HTTPException(503, "Vínculo WAHA fora do piloto autorizado.")
        if not settings.waha_ingress_enabled():
            raise HTTPException(503, "Recepção WAHA não habilitada.")
        if (binding.engine == 'GOWS' and incoming.kind in ('message','media')
                and incoming.occurred_at.timestamp() < binding.ingress_after):
            return {'processed': 0, 'ignored': 1, 'duplicates': 0}
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
                    if incoming.kind in ("message","media"):
                        message = _append_inbox_message(
                            conn,
                            binding.workspace_id,
                            incoming,
                            incoming.fingerprint,
                            origin="waha",
                        )
                        if not message["replayed"] and incoming.contact_name != "Contato do WhatsApp":
                            # This append already increments the conversation revision. Only
                            # upgrade the generic label; preserve human names and opaque LIDs.
                            conn.execute(
                                "UPDATE socialmei.me_conversations SET contact_name=%s "
                                "WHERE workspace_id=%s AND id=%s AND origin='waha' "
                                "AND account_ref=%s AND contact_ref=%s "
                                "AND contact_name='Contato do WhatsApp'",
                                (incoming.contact_name, binding.workspace_id,
                                 message["conversation_id"], incoming.account_ref, incoming.contact_ref),
                            )
                    status = "processado" if message else "ignorado"
                    conn.execute(
                        "INSERT INTO socialmei.crm_eventos_canal(workspace_id,canal_id,chave_evento,tipo,fingerprint,mensagem_externa_id,status,ocorrida_em,processado_em,waha_account_snapshot,waha_event_key,inbox_message_id,inbox_origin,dados_normalizados) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s,%s,'waha',%s)",
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
                            Jsonb({"media_kind":incoming.media_kind,"contact_ref":incoming.contact_ref} if incoming.kind=="media" else {"wa_selection":incoming.selection} if incoming.selection else {}),
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

        if incoming.kind == "message" and binding.workspace_id == 60:
            pass

        if incoming.kind == "message" and binding.workspace_id == 60:
            pass

        if incoming.kind=="message" and binding.workspace_id==60:
            _brilho_apply_event_phone(raw,binding,incoming)
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
        if (settings.waha_ingress_team_pilot_enabled()
                or settings.waha_workspace_inbox_requested()) and metadata.st_uid != 0:
            raise ValueError()
        bindings = []
        for entry in value["bindings"]:
            if not isinstance(entry, dict):
                raise ValueError()
            bindings.append(WahaBinding(**entry))
            if (bindings[-1].engine == 'GOWS' and not bindings[-1].ingress_after
                    and (settings.waha_ingress_team_pilot_enabled() or settings.waha_workspace_inbox_requested())):
                raise ValueError()
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


def _brilho_phone_label(binding, contact_ref):
    import httpx
    from urllib.parse import quote

    if (
        binding.workspace_id != 60
        or binding.engine != "GOWS"
        or not settings.waha_pilot_binding_allowed(
            binding.workspace_id,binding.channel_id,
            binding.instance,binding.session,
            binding.account_id,binding.revision,binding.engine
        )
        or not contact_ref.startswith("waha:")
    ):
        return False

    sender=contact_ref.removeprefix("waha:")

    if not DIRECT.fullmatch(sender):
        return False

    scope=(60,"waha:"+binding.account_id,contact_ref)

    try:
        with connect() as conn:
            exists=conn.execute(
                "SELECT EXISTS(SELECT 1 "
                "FROM socialmei.me_conversations "
                "WHERE workspace_id=%s AND account_ref=%s "
                "AND contact_ref=%s AND origin='waha' "
                "AND contact_name='Contato do WhatsApp')",
                scope
            ).fetchone()[0]

        if not exists:
            return False

        if re.fullmatch(r"[1-9][0-9]{7,14}@c\.us",sender):
            phone=sender

        elif sender.endswith("@lid"):
            cfg=settings.whatsapp_human_configuration()

            if (
                cfg is None
                or cfg.workspace_id!=60
                or cfg.account_id!=binding.account_id
                or cfg.session!=binding.session
                or cfg.engine!="GOWS"
            ):
                return False

            url=(
                cfg.base_url.rstrip("/")+
                "/api/"+quote(binding.session,safe="")+
                "/lids/"+quote(sender,safe="")
            )

            with httpx.Client(
                timeout=3,trust_env=False,
                follow_redirects=False
            ) as client:
                response=client.get(
                    url,headers={"X-Api-Key":cfg.api_key}
                )

                if response.status_code!=200:
                    return False

                result=response.json()

            if result.get("lid")!=sender:
                return False

            phone=result.get("pn")

            if not isinstance(phone,str) or not re.fullmatch(
                r"[1-9][0-9]{7,14}@c\.us",phone
            ):
                return False

        else:
            return False

        label="+"+phone.removesuffix("@c.us")

        with connect() as conn:
            changed=conn.execute(
                "UPDATE socialmei.me_conversations "
                "SET contact_name=%s "
                "WHERE workspace_id=%s AND account_ref=%s "
                "AND contact_ref=%s AND origin='waha' "
                "AND contact_name='Contato do WhatsApp' "
                "AND EXISTS(SELECT 1 FROM socialmei.crm_canais "
                "WHERE workspace_id=60 AND id=%s "
                "AND ativo AND ingress_provisioned "
                "AND versao=%s AND identificador_conta=%s)",
                (label,*scope,binding.channel_id,
                 binding.revision,binding.account_id)
            ).rowcount

        return changed>0

    except Exception:
        # Identificacao opcional: nunca bloquear recebimento.
        return False


def _brilho_phone_label(binding, contact_ref):
    import httpx
    from urllib.parse import quote

    if (
        binding.workspace_id != 60
        or binding.engine != "GOWS"
        or not settings.waha_pilot_binding_allowed(
            binding.workspace_id,binding.channel_id,
            binding.instance,binding.session,
            binding.account_id,binding.revision,binding.engine
        )
        or not contact_ref.startswith("waha:")
    ):
        return False

    sender=contact_ref.removeprefix("waha:")

    if not DIRECT.fullmatch(sender):
        return False

    scope=(60,"waha:"+binding.account_id,contact_ref)

    try:
        with connect() as conn:
            exists=conn.execute(
                "SELECT EXISTS(SELECT 1 "
                "FROM socialmei.me_conversations "
                "WHERE workspace_id=%s AND account_ref=%s "
                "AND contact_ref=%s AND origin='waha' "
                "AND contact_name='Contato do WhatsApp')",
                scope
            ).fetchone()[0]

        if not exists:
            return False

        if re.fullmatch(r"[1-9][0-9]{7,14}@c\.us",sender):
            phone=sender

        elif sender.endswith("@lid"):
            cfg=settings.whatsapp_human_configuration()

            if (
                cfg is None
                or cfg.workspace_id!=60
                or cfg.account_id!=binding.account_id
                or cfg.session!=binding.session
                or cfg.engine!="GOWS"
            ):
                return False

            url=(
                cfg.base_url.rstrip("/")+
                "/api/"+quote(binding.session,safe="")+
                "/lids/"+quote(sender,safe="")
            )

            with httpx.Client(
                timeout=3,trust_env=False,
                follow_redirects=False
            ) as client:
                response=client.get(
                    url,headers={"X-Api-Key":cfg.api_key}
                )

                if response.status_code!=200:
                    return False

                result=response.json()

            if result.get("lid")!=sender:
                return False

            phone=result.get("pn")

            if not isinstance(phone,str) or not re.fullmatch(
                r"[1-9][0-9]{7,14}@c\.us",phone
            ):
                return False

        else:
            return False

        if phone == binding.account_id:
            return False

        label="+"+phone.removesuffix("@c.us")

        with connect() as conn:
            changed=conn.execute(
                "UPDATE socialmei.me_conversations "
                "SET contact_name=%s "
                "WHERE workspace_id=%s AND account_ref=%s "
                "AND contact_ref=%s AND origin='waha' "
                "AND contact_name='Contato do WhatsApp' "
                "AND EXISTS(SELECT 1 FROM socialmei.crm_canais "
                "WHERE workspace_id=60 AND id=%s "
                "AND ativo AND ingress_provisioned "
                "AND versao=%s AND identificador_conta=%s)",
                (label,*scope,binding.channel_id,
                 binding.revision,binding.account_id)
            ).rowcount

        return changed>0

    except Exception:
        # Identificacao opcional: nunca bloquear recebimento.
        return False


def _brilho_phone_from_event(raw,binding,incoming):
    if (
        binding.workspace_id!=60
        or binding.engine!="GOWS"
        or incoming.kind!="message"
        or not incoming.sender.endswith("@lid")
        or not settings.waha_pilot_binding_allowed(
            binding.workspace_id,binding.channel_id,
            binding.instance,binding.session,
            binding.account_id,binding.revision,binding.engine
        )
    ):
        return None

    try:
        event=json.loads(raw)
        p=event["payload"]

        if (
            event.get("engine")!="GOWS"
            or event.get("session")!=binding.session
            or event.get("me",{}).get("id")!=binding.account_id
            or p.get("id")!=incoming.mid
            or p.get("from")!=incoming.sender
            or p.get("fromMe") is not False
        ):
            return None

        alt=p.get("_data",{}).get(
            "Info",{}
        ).get("SenderAlt","")

        match=re.fullmatch(
            r"([1-9][0-9]{7,14})"
            r"(?::[0-9]+)?@"
            r"(?:s\.whatsapp\.net|c\.us)",
            alt
        )

        if not match:
            return None

        number=match.group(1)

        if number in (
            incoming.sender.split("@")[0],
            binding.account_id.split("@")[0]
        ):
            return None

        return "+"+number

    except Exception:
        return None


def _brilho_apply_event_phone(raw,binding,incoming):
    label=_brilho_phone_from_event(raw,binding,incoming)

    if not label:
        return False

    try:
        with connect() as conn:
            conn.execute(
                "UPDATE socialmei.me_conversations "
                "SET contact_name=%s "
                "WHERE workspace_id=60 AND origin='waha' "
                "AND account_ref=%s AND contact_ref=%s "
                "AND contact_name='Contato do WhatsApp' "
                "AND EXISTS(SELECT 1 FROM socialmei.crm_canais "
                "WHERE workspace_id=60 AND id=%s "
                "AND ativo AND ingress_provisioned "
                "AND versao=%s AND identificador_conta=%s)",
                (
                    label,incoming.account_ref,
                    incoming.contact_ref,binding.channel_id,
                    binding.revision,binding.account_id
                )
            )

        return True

    except Exception:
        return False


_socialmei_original_phone_label=_brilho_apply_event_phone

def _brilho_apply_event_phone(raw,binding,incoming):
    result=_socialmei_original_phone_label(
        raw,binding,incoming
    )

    try:
        import unicodedata

        if (
            binding.workspace_id!=60
            or binding.engine!="GOWS"
            or incoming.kind!="message"
            or not settings.waha_pilot_binding_allowed(
                binding.workspace_id,binding.channel_id,
                binding.instance,binding.session,
                binding.account_id,binding.revision,binding.engine
            )
        ):
            return result

        event=json.loads(raw)
        p=event["payload"]

        if (
            event.get("engine")!="GOWS"
            or event.get("session")!=binding.session
            or event.get("me",{}).get("id")!=binding.account_id
            or p.get("id")!=incoming.mid
            or p.get("from")!=incoming.sender
            or p.get("fromMe") is not False
            or incoming.sender==binding.account_id
            or not incoming.sender.endswith(("@lid","@c.us"))
        ):
            return result

        name=p.get("_data",{}).get("Info",{}).get("PushName")

        if not isinstance(name,str):
            return result

        name=" ".join(name.split())

        if (
            not name or len(name)>100
            or any(x in name for x in "<>&")
            or not any(x.isalpha() for x in name)
            or any(
                unicodedata.category(x).startswith("C")
                for x in name
            )
        ):
            return result

        with connect() as conn:
            conn.execute(
                "UPDATE socialmei.me_conversations "
                "SET contact_name=CASE "
                "WHEN contact_name ~ '^[+][0-9]{8,15}$' "
                "THEN %s||' ('||contact_name||')' "
                "ELSE %s END "
                "WHERE workspace_id=60 AND origin='waha' "
                "AND account_ref=%s AND contact_ref=%s "
                "AND cliente_id IS NULL "
                "AND (contact_name='Contato do WhatsApp' "
                "OR contact_name ~ '^[+][0-9]{8,15}$') "
                "AND EXISTS(SELECT 1 FROM socialmei.crm_canais "
                "WHERE workspace_id=60 AND id=%s "
                "AND ativo AND ingress_provisioned "
                "AND versao=%s AND identificador_conta=%s)",
                (
                    name,name,incoming.account_ref,
                    incoming.contact_ref,binding.channel_id,
                    binding.revision,binding.account_id
                )
            )

    except Exception:
        pass

    return result
