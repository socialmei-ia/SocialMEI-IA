"""Authenticated encryption contracts using disposable synthetic key material."""

import base64
import unittest
from dataclasses import replace
from uuid import UUID

from instagram_token_vault import TokenBinding, TokenVault, VaultError

KEY = b"1" * 32
OTHER_KEY = b"2" * 32
TOKEN = "synthetic-meta-token-no-real-account"


class TokenVaultTests(unittest.TestCase):
    def binding(self, **changes):
        return replace(
            TokenBinding(
                1,
                UUID("00000000-0000-0000-0000-000000000002"),
                "12345",
            ),
            **changes
        )

    def test_roundtrip_and_secret_safe_representation(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        envelope = vault.seal(TOKEN, self.binding())
        self.assertEqual(vault.open(envelope, self.binding()), TOKEN)
        self.assertNotIn(TOKEN, envelope)
        self.assertNotIn(KEY.decode(), repr(vault))
        self.assertNotIn("12345", repr(self.binding()))
        self.assertTrue(envelope.startswith("v1:test-v1:"))

    def test_random_nonce_changes_ciphertext(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        first = vault.seal(TOKEN, self.binding())
        second = vault.seal(TOKEN, self.binding())
        self.assertNotEqual(first.split(":")[2], second.split(":")[2])
        self.assertEqual(vault.open(first, self.binding()), TOKEN)
        self.assertEqual(vault.open(second, self.binding()), TOKEN)

    def test_workspace_connection_and_account_are_authenticated(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        envelope = vault.seal(TOKEN, self.binding())
        for changed in (
            self.binding(workspace_id=3),
            self.binding(connection_id=UUID(int=4)),
            self.binding(account_id="67890"),
        ):
            with self.subTest(binding=repr(changed)), self.assertRaises(VaultError):
                vault.open(envelope, changed)

    def test_modified_ciphertext_nonce_or_key_is_rejected(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        envelope = vault.seal(TOKEN, self.binding())
        for index in (2, 3):
            parts = envelope.split(":")
            parts[index] = ("A" if parts[index][0] != "A" else "B") + parts[index][1:]
            with self.subTest(index=index), self.assertRaises(VaultError):
                vault.open(":".join(parts), self.binding())
        wrong = TokenVault(keys={"test-v1": OTHER_KEY}, active_key_id="test-v1")
        with self.assertRaises(VaultError) as caught:
            wrong.open(envelope, self.binding())
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(TOKEN, str(caught.exception))
        self.assertNotIn(KEY.decode(), str(caught.exception))

    def test_rotation_reads_previous_key_but_seals_only_active_key(self):
        original = TokenVault(keys={"old": KEY}, active_key_id="old")
        old = original.seal(TOKEN, self.binding())
        rotated = TokenVault(keys={"old": KEY, "new": OTHER_KEY}, active_key_id="new")
        self.assertEqual(rotated.open(old, self.binding()), TOKEN)
        self.assertTrue(rotated.seal(TOKEN, self.binding()).startswith("v1:new:"))
        retired = TokenVault(keys={"new": OTHER_KEY}, active_key_id="new")
        with self.assertRaises(VaultError):
            retired.open(old, self.binding())

    def test_key_identifier_cannot_be_changed_even_if_key_bytes_match(self):
        vault = TokenVault(keys={"one": KEY, "two": KEY}, active_key_id="one")
        envelope = vault.seal(TOKEN, self.binding()).replace("v1:one:", "v1:two:")
        with self.assertRaises(VaultError):
            vault.open(envelope, self.binding())

    def test_keyring_is_copied_and_invalid_keys_fail_closed(self):
        keys = {"test-v1": KEY}
        vault = TokenVault(keys=keys, active_key_id="test-v1")
        keys["test-v1"] = OTHER_KEY
        envelope = vault.seal(TOKEN, self.binding())
        self.assertEqual(
            TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1").open(
                envelope, self.binding()
            ),
            TOKEN,
        )
        for invalid in (
            {},
            {"test-v1": b"short"},
            {"test-v1": KEY.decode()},
            {"bad:id": KEY},
        ):
            with self.subTest(key_count=len(invalid)), self.assertRaises(VaultError):
                TokenVault(keys=invalid, active_key_id="test-v1")
        with self.assertRaises(VaultError):
            TokenVault(keys={"one": KEY}, active_key_id="missing")

    def test_unknown_versions_duplicate_fields_and_invalid_envelopes_rejected(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        valid = vault.seal(TOKEN, self.binding())
        for envelope in (
            "",
            None,
            valid.replace("v1:", "v2:"),
            valid + ":extra",
            "v1:test-v1:not base64:abc",
            "v1:test-v1:a:a",
            "x" * 24001,
        ):
            with self.subTest(value_type=type(envelope).__name__), self.assertRaises(
                VaultError
            ):
                vault.open(envelope, self.binding())

    def test_token_boundaries_and_no_control_characters(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        token = "x" * 16384
        self.assertEqual(
            vault.open(vault.seal(token, self.binding()), self.binding()), token
        )
        for invalid in ("", "bad\ntoken", "bad token", "ç", None, "x" * 16385):
            with self.subTest(token_type=type(invalid).__name__), self.assertRaises(
                VaultError
            ):
                vault.seal(invalid, self.binding())

    def test_binding_must_contain_server_ids_and_numeric_account_id(self):
        for changes in (
            {"workspace_id": "invalid"},
            {"connection_id": "invalid"},
            {"account_id": True},
            {"account_id": "bad"},
            {"provider": "facebook"},
        ):
            with self.subTest(fields=list(changes)), self.assertRaises(VaultError):
                self.binding(**changes)

    def test_nonce_encoding_is_canonical_and_fixed_length(self):
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        envelope = vault.seal(TOKEN, self.binding())
        nonce = envelope.split(":")[2]
        self.assertEqual(len(base64.urlsafe_b64decode(nonce)), 12)
        with self.assertRaises(VaultError):
            vault.open(envelope.replace(nonce, nonce + "="), self.binding())

    def test_workspace_binding_uses_existing_postgresql_bigint_ids(self):
        binding = TokenBinding(42, UUID(int=2), "12345")
        vault = TokenVault(keys={"test-v1": KEY}, active_key_id="test-v1")
        envelope = vault.seal(TOKEN, binding)
        self.assertEqual(vault.open(envelope, binding), TOKEN)
        for invalid in (True, 0, -1, "42", UUID(int=42), 2**63):
            with self.subTest(value_type=type(invalid).__name__), self.assertRaises(
                VaultError
            ):
                TokenBinding(invalid, UUID(int=2), "12345")
