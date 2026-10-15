"""Contratos de configuração sem conexão com bancos ou serviços externos."""

import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import settings
from account_auth import enabled, require_enabled
from auth_context import principal
from database import database_url
from shared_data import workspace_name, workspace_slug


class SettingsTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_authentication_typo_remains_fail_closed(self):
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_AUTH_ENABLED": "treu",
                "SOCIALMEI_SHARED_DATA_ENABLED": "true",
            },
        ):
            self.assertEqual("invalid", settings.authentication_mode())
            self.assertTrue(enabled())
            with self.assertRaises(HTTPException) as error:
                require_enabled()
            self.assertEqual(503, error.exception.status_code)

    def test_authentication_values_preserve_existing_modes(self):
        for value in ("false", "OFF", " no ", "0", ""):
            with self.subTest(value=value), patch.dict(
                os.environ, {"SOCIALMEI_AUTH_ENABLED": value}
            ):
                self.assertEqual("disabled", settings.authentication_mode())
                self.assertFalse(enabled())
        for value in ("true", "ON", " yes ", "1"):
            with self.subTest(value=value), patch.dict(
                os.environ, {"SOCIALMEI_AUTH_ENABLED": value}
            ):
                self.assertEqual("enabled", settings.authentication_mode())

    def test_explicit_database_url_has_precedence(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": " postgresql://example.invalid/test ",
                "POSTGRES_HOST": "other.invalid",
            },
        ):
            self.assertEqual("postgresql://example.invalid/test", database_url())

    def test_database_components_are_encoded_without_trimming_password(self):
        with patch.dict(
            os.environ,
            {
                "POSTGRES_HOST": " db.invalid ",
                "POSTGRES_USER": " test@user ",
                "POSTGRES_PASSWORD": " test-only:/@ ",
                "POSTGRES_DB": " test/db ",
                "POSTGRES_PORT": " ",
            },
        ):
            self.assertEqual(
                "postgresql://test%40user:%20test-only%3A%2F%40%20@db.invalid:5432/test%2Fdb",
                database_url(),
            )

    def test_missing_database_configuration_does_not_expose_values(self):
        with patch.dict(os.environ, {"POSTGRES_PASSWORD": "test-only-private-marker"}):
            with self.assertRaises(RuntimeError) as error:
                database_url()
            self.assertNotIn("test-only-private-marker", str(error.exception))

    def test_settings_do_not_cache_secrets_or_workspace(self):
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_WORKSPACE_SLUG": "first",
                "SOCIALMEI_N8N_READ_TOKEN": " first-test-value ",
            },
        ):
            self.assertEqual("first", settings.workspace_slug())
            self.assertEqual(" first-test-value ", settings.n8n_read_token())
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_WORKSPACE_SLUG": "second",
                "SOCIALMEI_N8N_READ_TOKEN": "second-test-value",
            },
        ):
            self.assertEqual("second", settings.workspace_slug())
            self.assertEqual("second-test-value", settings.n8n_read_token())

    def test_session_workspace_still_overrides_environment(self):
        token = principal.set(
            {
                "workspace_slug": "authenticated-business",
                "nome_negocio": "Negócio da sessão",
            }
        )
        self.addCleanup(principal.reset, token)
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_WORKSPACE_SLUG": "team",
                "SOCIALMEI_WORKSPACE_NAME": "Outro negócio",
            },
        ):
            self.assertEqual("authenticated-business", workspace_slug())
            self.assertEqual("Negócio da sessão", workspace_name())

    def test_empty_workspace_uses_legacy_defaults(self):
        with patch.dict(
            os.environ,
            {"SOCIALMEI_WORKSPACE_SLUG": " ", "SOCIALMEI_WORKSPACE_NAME": " "},
        ):
            self.assertEqual("development", settings.workspace_slug())
            self.assertEqual("SocialMEI Development", settings.workspace_name())

    def test_cors_is_explicit_and_rejects_wildcard(self):
        self.assertEqual([], settings.cors_origins())
        with patch.dict(
            os.environ,
            {
                "SOCIALMEI_CORS_ORIGINS": " https://app.example.com, ,http://localhost:5500 "
            },
        ):
            self.assertEqual(
                ["https://app.example.com", "http://localhost:5500"],
                settings.cors_origins(),
            )
        with patch.dict(
            os.environ, {"SOCIALMEI_CORS_ORIGINS": "https://app.example.com,*"}
        ):
            with self.assertRaises(RuntimeError):
                settings.cors_origins()

    def test_shared_data_flag_preserves_existing_whitespace_behavior(self):
        for value, expected in (
            ("TRUE", True),
            ("false", False),
            (" true ", False),
            ("typo", False),
        ):
            with self.subTest(value=value), patch.dict(
                os.environ, {"SOCIALMEI_SHARED_DATA_ENABLED": value}
            ):
                self.assertEqual(expected, settings.shared_data_enabled())


if __name__ == "__main__":
    unittest.main()
