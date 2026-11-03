"""Workspace receiving readiness must match private registry and database exactly."""
import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from instagram_runtime import whatsapp_readiness
from test_integration_readiness import BINDING, KEY, database, registry


class WorkspaceReadinessTests(unittest.TestCase):
    def env(self):
        return patch.multiple(
            "instagram_runtime.settings",
            waha_ingress_team_pilot_enabled=lambda: False,
            waha_ingress_workspace_enabled=lambda: True,
        )

    def test_workspace_configuration_requires_matching_private_and_database_binding(self):
        binding = replace(BINDING, workspace_id=17, instance="authorized-business")
        db = database()
        with self.env(), patch("waha_ingress.waha_service", return_value=registry(binding)), patch("instagram_runtime.connect", db):
            value = whatsapp_readiness(17)
        self.assertTrue(value["receiving_configured"])
        self.assertTrue(value["configured"])
        self.assertFalse(value["session_live_verified"])
        self.assertFalse(value["sending_available"])
        self.assertNotIn(KEY, json.dumps(value))
        query = [c for c in db.return_value.__enter__.return_value.execute.call_args_list if "crm_canais" in c.args[0]]
        self.assertEqual(query[0].args[1], (17, 27, "authorized-business", "default", binding.account_id, 3))

    def test_other_workspace_and_disabled_mode_do_not_read_database(self):
        with self.env(), patch("waha_ingress.waha_service", return_value=registry(BINDING)), patch("instagram_runtime.connect") as db:
            for workspace in (2, 0, True, "1", None):
                self.assertFalse(whatsapp_readiness(workspace)["configured"])
            db.assert_not_called()

    def test_all_current_workspace_bindings_match_and_other_workspaces_are_not_queried(self):
        own = replace(BINDING, workspace_id=17, instance="own-one")
        second = replace(BINDING, workspace_id=17, instance="own-two", channel_id=28)
        foreign = replace(BINDING, workspace_id=18, instance="foreign", channel_id=29)
        db = database()
        with self.env(), patch("waha_ingress.waha_service", return_value=registry(own, second, foreign)), patch("instagram_runtime.connect", db):
            self.assertTrue(whatsapp_readiness(17)["receiving_configured"])
        queries = [c for c in db.return_value.__enter__.return_value.execute.call_args_list if "crm_canais" in c.args[0]]
        self.assertEqual(len(queries), 2)
        self.assertEqual([c.args[1][0] for c in queries], [17, 17])

    def test_missing_exact_channel_and_private_errors_fail_closed_without_details(self):
        for missing in (database(None), database()):
            with self.env(), patch("waha_ingress.waha_service", side_effect=RuntimeError(KEY)), patch("instagram_runtime.connect", missing):
                value = whatsapp_readiness(17)
                self.assertFalse(value["configured"])
                self.assertNotIn(KEY, json.dumps(value))
        binding = replace(BINDING, workspace_id=17)
        with self.env(), patch("waha_ingress.waha_service", return_value=registry(binding)), patch("instagram_runtime.connect", database(None)):
            self.assertFalse(whatsapp_readiness(17)["configured"])
