"""Encryption boundary for a future server-side Instagram token store.

No storage, configuration loading, key generation, routes or external I/O.
Identity binding must come from authenticated server-side connection metadata.
"""

import base64
import binascii
import json
import os
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAX_TOKEN_BYTES = 16384
MAX_ENVELOPE_BYTES = 24000
_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,32}\Z")
_ENCODED = re.compile(r"[A-Za-z0-9_-]+\Z")


class VaultError(ValueError):
    def __init__(self):
        super().__init__("Credencial Instagram indisponível ou inválida.")


@dataclass(frozen=True)
class TokenBinding:
    workspace_id: int = field(repr=False)
    connection_id: UUID = field(repr=False)
    account_id: str = field(repr=False)
    provider: str = "instagram"

    def __post_init__(self):
        if (
            type(self.workspace_id) is not int
            or not 1 <= self.workspace_id <= 2**63 - 1
            or not isinstance(self.connection_id, UUID)
            or not isinstance(self.account_id, str)
            or not re.fullmatch(r"[0-9]{1,40}", self.account_id)
            or self.provider != "instagram"
        ):
            raise VaultError()


def _key_id(value):
    if not isinstance(value, str) or not _KEY_ID.fullmatch(value):
        raise VaultError()
    return value


def _encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value):
    if not isinstance(value, str) or not _ENCODED.fullmatch(value):
        raise VaultError()
    result = None
    try:
        result = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error):
        pass
    if result is None or _encode(result) != value:
        raise VaultError()
    return result


def _token(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= MAX_TOKEN_BYTES
        or not value.isascii()
        or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
    ):
        raise VaultError()
    return value


def _aad(binding, key_id):
    if not isinstance(binding, TokenBinding):
        raise VaultError()
    return json.dumps(
        [
            "socialmei-instagram-token",
            "v1",
            key_id,
            binding.provider,
            str(binding.workspace_id),
            str(binding.connection_id),
            binding.account_id,
        ],
        separators=(",", ":"),
    ).encode("ascii")


class TokenVault:
    def __init__(self, *, keys: Mapping[str, bytes], active_key_id: str):
        active_key_id = _key_id(active_key_id)
        if not isinstance(keys, Mapping) or not 1 <= len(keys) <= 16:
            raise VaultError()
        copied = {}
        for key_id, material in keys.items():
            _key_id(key_id)
            if not isinstance(material, bytes) or len(material) != 32:
                raise VaultError()
            copied[key_id] = material
        if active_key_id not in copied:
            raise VaultError()
        self._keys = MappingProxyType(copied)
        self._active_key_id = active_key_id

    def __repr__(self):
        return "TokenVault(keys=<redacted>)"

    def seal(self, token, binding):
        token = _token(token)
        key_id = self._active_key_id
        aad = _aad(binding, key_id)
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[key_id]).encrypt(
            nonce, token.encode("ascii"), aad
        )
        return ":".join(("v1", key_id, _encode(nonce), _encode(ciphertext)))

    def open(self, envelope, binding):
        if (
            not isinstance(envelope, str)
            or not 1 <= len(envelope) <= MAX_ENVELOPE_BYTES
        ):
            raise VaultError()
        parts = envelope.split(":")
        if len(parts) != 4 or parts[0] != "v1":
            raise VaultError()
        key_id = _key_id(parts[1])
        if key_id not in self._keys:
            raise VaultError()
        nonce, ciphertext = _decode(parts[2]), _decode(parts[3])
        if len(nonce) != 12 or not 17 <= len(ciphertext) <= MAX_TOKEN_BYTES + 16:
            raise VaultError()
        aad = _aad(binding, key_id)
        plaintext = None
        try:
            plaintext = (
                AESGCM(self._keys[key_id])
                .decrypt(nonce, ciphertext, aad)
                .decode("ascii")
            )
        except (InvalidTag, ValueError, UnicodeError):
            pass
        if plaintext is None:
            raise VaultError()
        return _token(plaintext)
