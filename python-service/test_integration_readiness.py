"""WAHA readiness is evidence of a private receiving binding, never a send claim."""

import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from instagram_runtime import InstagramRuntime, readiness, whatsapp_readiness
from waha_ingress import WahaBinding

KEY = "synthetic-readiness-hmac-key-not-a-real-secret"
BINDING = WahaBinding(
    instance="socialmei-equipe-piloto",
    session="default",
    account_id="551199995976@c.us",
    workspace_id=1,
    channel_id=27,
    hmac_key=KEY,
    revision=3,
)


def database(found=(1,)):
    db = MagicMock()
    db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = found
    return db


def registry(*bindings):
    return SimpleNamespace(registry={item.instance: item for item in bindings})


class WhatsappReadinessTests(unittest.TestCase):
    def test_other_workspace_is_closed_without_accessing_registry_or_db(self):
        with patch(
            "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
            return_value=True,
        ), patch(
            "waha_ingress.waha_service",
            side_effect=AssertionError("private mount accessed"),
        ) as service, patch(
            "instagram_runtime.connect",
            side_effect=AssertionError("database accessed"),
        ) as db:
            for workspace in (2, None, "1", True, 0):
                with self.subTest(workspace=workspace):
                    result = whatsapp_readiness(workspace)
                    self.assertFalse(result["configured"])
                    self.assertFalse(result["receiving_configured"])
                    self.assertFalse(result["sending_available"])
            service.assert_not_called()
            db.assert_not_called()

    def test_pilot_requires_explicit_mode_and_private_registry(self):
        with patch(
            "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
            return_value=False,
        ), patch(
            "waha_ingress.waha_service",
            side_effect=AssertionError("private mount accessed"),
        ):
            self.assertFalse(whatsapp_readiness(1)["configured"])

        with patch(
            "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
            return_value=True,
        ), patch(
            "waha_ingress.waha_service",
            side_effect=RuntimeError("private-registry-secret"),
        ), patch("instagram_runtime.connect") as db:
            output = whatsapp_readiness(1)
            self.assertFalse(output["configured"])
            self.assertNotIn("private-registry-secret", json.dumps(output))
            db.assert_not_called()

    def test_matches_authorized_binding_and_persisted_channel(self):
        db = database()
        with patch(
            "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
            return_value=True,
        ), patch(
            "waha_ingress.waha_service", return_value=registry(BINDING)
        ), patch("instagram_runtime.connect", db):
            value = whatsapp_readiness(1)
        self.assertTrue(value["configured"])
        self.assertTrue(value["receiving_configured"])
        self.assertFalse(value["session_live_verified"])
        self.assertFalse(value["sending_available"])
        self.assertNotIn(KEY, json.dumps(value))
        conn = db.return_value.__enter__.return_value
        query = [
            call for call in conn.execute.call_args_list
            if "crm_canais" in call.args[0]
        ]
        self.assertEqual(len(query), 1)
        self.assertIn("NOT envio_habilitado", query[0].args[0])
        self.assertEqual(
            query[0].args[1],
            (1, 27, "socialmei-equipe-piloto", "default", "551199995976@c.us", 3),
        )

    def test_inconsistent_bindings_or_database_fail_closed(self):
        wrong = [
            registry(),
            registry(replace(BINDING, instance="another")),
            registry(replace(BINDING, workspace_id=2)),
            registry(replace(BINDING, account_id="551199991234@c.us")),
            registry(BINDING, replace(BINDING, instance="another")),
        ]
        for service in wrong:
            with self.subTest(registry=list(service.registry)), patch(
                "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
                return_value=True,
            ), patch(
                "waha_ingress.waha_service", return_value=service
            ), patch("instagram_runtime.connect") as db:
                self.assertFalse(whatsapp_readiness(1)["configured"])
                db.assert_not_called()

        for db in (database(None), MagicMock()):
            with self.subTest(db=str(type(db))), patch(
                "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
                return_value=True,
            ), patch(
                "waha_ingress.waha_service", return_value=registry(BINDING)
            ), patch("instagram_runtime.connect", db):
                self.assertFalse(whatsapp_readiness(1)["configured"])

        with patch(
            "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
            return_value=True,
        ), patch(
            "waha_ingress.waha_service", return_value=registry(BINDING)
        ), patch(
            "instagram_runtime.connect", side_effect=RuntimeError("db-secret")
        ):
            result = whatsapp_readiness(1)
            self.assertFalse(result["configured"])
            self.assertNotIn("db-secret", json.dumps(result))

    def test_readiness_endpoint_only_uses_authenticated_workspace(self):
        request = SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(instagram_runtime=InstagramRuntime())
            )
        )
        with patch("instagram_runtime.require_enabled"), patch(
            "instagram_runtime.current", return_value={"workspace_id":2}
        ), patch(
            "instagram_runtime.settings.waha_ingress_team_pilot_enabled",
            return_value=True,
        ), patch(
            "instagram_runtime.schema_ready", return_value=False
        ), patch(
            "waha_ingress.waha_service",
            side_effect=AssertionError("private mount accessed"),
        ):
            response = readiness(request)
        self.assertEqual(response["source"], "server")
        self.assertFalse(response["whatsapp"]["configured"])
        self.assertFalse(response["whatsapp"]["sending_available"])


if __name__ == "__main__":
    unittest.main()
