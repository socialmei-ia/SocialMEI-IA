"""Offline contract tests for the read-only AWS Team cutover inspector."""
import importlib.util
import json
from pathlib import Path
import unittest

TARGET = Path(__file__).resolve().parents[1] / "tools/team-cutover-inspect.py"
spec = importlib.util.spec_from_file_location("team_cutover_inspect", TARGET)
cutover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cutover)

CANDIDATE = "a" * 40


def container(*, health="healthy", ports=False, engine=None, api=False,
              networks=None, exposed_secret="SECRET_DO_NOT_LEAK"):
    env = ["VERY_SENSITIVE_TOKEN=" + exposed_secret]
    if api:
        env += [
            "SOCIALMEI_AUTH_ENABLED=true",
            "SOCIALMEI_INSTAGRAM_RUNTIME_MODE=connect",
            "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false",
            "SOCIALMEI_INSTAGRAM_DIRECT_OWNER=unassigned",
            "SOCIALMEI_PROVIDER_SENTIMENT_ENABLED=false",
            "SOCIALMEI_PROVIDER_SENTIMENT_KEY=" + exposed_secret,
            "SOCIALMEI_PROVIDER_SENTIMENT_WORKSPACE_IDS=4",
        ]
    if engine:
        env.append("WHATSAPP_DEFAULT_ENGINE=" + engine)
    return {
        "State": {"Running": True, "Health": {"Status": health}},
        "Config": {
            "Env": env,
            "Labels": {"org.opencontainers.image.revision": "b" * 40},
        },
        "NetworkSettings": {"Networks": {k: {} for k in (networks or [])}},
        "HostConfig": {"PortBindings": {"8000/tcp": [{}]} if ports else {}},
    }


class TeamCutoverTests(unittest.TestCase):
    def test_sanitizer_never_prints_secret_or_actual_env_values(self):
        c = container(api=True, exposed_secret="ABC_ROOT_SECRET_123456" + "x" * 40)
        result = cutover.inspect_summary(c, "team_api")
        serialized = json.dumps(result)
        self.assertNotIn("ABC_ROOT_SECRET_123456", serialized)
        self.assertNotIn("VERY_SENSITIVE_TOKEN", serialized)
        self.assertFalse(result["flags"]["instagram_send"])
        self.assertTrue(result["flags"]["sentiment_key_configured"])
        self.assertEqual(result["flags"]["instagram_runtime"], "connect")

    def test_database_032_033_and_drift_flags(self):
        data = {
            "versions": [
                "001_initial_socialmei_schema.sql",
                "032_whatsapp_bot_conversations.sql",
                "033_provider_sentiment_jobs.sql",
            ],
            "bot_table": True,
            "sentiment_table": True,
        }
        good = cutover.migration_summary(data)
        self.assertTrue(good["has_032"] and good["has_033"])
        self.assertEqual(good["max_prefix"], 33)
        self.assertFalse(good["future_or_unknown_versions"])
        self.assertTrue(good["ledger_has_gaps"])
        data["versions"].append("040_unreviewed_change.sql")
        self.assertTrue(cutover.migration_summary(data)["future_or_unknown_versions"])
        data["versions"].pop()
        data["versions"].append("034_unreviewed_change.sql")
        self.assertTrue(cutover.migration_summary(data)["future_or_unknown_versions"])
        data["versions"] = ["032_whatsapp_bot_conversations.sql"] * 2
        self.assertTrue(cutover.migration_summary(data)["duplicate_versions"])

    def test_instagram_schema039_is_recognized_but_missing_tables_block_cutover(self):
        versions = [f"{number:03}_fixture.sql" for number in range(1, 32)] + [
            "032_whatsapp_bot_conversations.sql",
            "033_provider_sentiment_jobs.sql",
            "034_workspace_agenda.sql",
            "035_whatsapp_human_outbox.sql",
            "036_service_appointments.sql",
            "037_catalog_details.sql",
            "038_inbox_customer_link.sql",
            "039_instagram_auto_menu.sql",
        ]
        data = {
            "versions": versions,
            "bot_table": True,
            "sentiment_table": True,
            "instagram_menu_table": True,
            "instagram_replies_table": True,
        }
        summary = cutover.migration_summary(data)
        self.assertEqual(summary["max_prefix"], 39)
        self.assertTrue(summary["has_039"])
        self.assertFalse(summary["future_or_unknown_versions"])
        self.assertFalse(summary["ledger_has_gaps"])
        data["instagram_replies_table"] = False
        missing = cutover.migration_summary(data)
        self.assertFalse(missing["has_039"])
        report = {"source": {"sha": CANDIDATE, "clean": True},
                  "containers": {name: cutover.inspect_summary(container(
                      api=name == "team_api"), name)
                      for name in cutover.CONTAINERS},
                  "database": missing}
        decision = cutover.assess(report, CANDIDATE)
        self.assertIn("instagram_menu_039_incompleto", decision["blockers"])
        self.assertFalse(decision["preflight_unblocked"])

    def test_ai_egress_requires_private_network_key_and_allowlist_without_leaks(self):
        secret = "PRIVATE_AI_TEST_KEY_NOT_TO_PRINT_1234567890000"
        api = container(api=True, networks=["socialmei_team_automation"])
        api["Config"]["Env"].extend([
            "SOCIALMEI_AI_DRAFT_ENABLED=true",
            "SOCIALMEI_GROQ_API_KEY=" + secret,
            "SOCIALMEI_AI_DRAFT_WORKSPACES=4",
        ])
        summary = cutover.inspect_summary(api, "team_api")
        self.assertTrue(summary["flags"]["ai_draft_key_configured"])
        self.assertFalse(summary["flags"]["ai_egress_network"])
        self.assertNotIn(secret, json.dumps(summary))
        report = {"source": {"sha": CANDIDATE, "clean": True},
                  "containers": {name: (summary if name == "team_api"
                      else cutover.inspect_summary(container(), name))
                      for name in cutover.CONTAINERS},
                  "database": cutover.migration_summary({
                      "versions": [f"{i:03}_fixture.sql" for i in range(1, 32)]
                          + ["032_whatsapp_bot_conversations.sql",
                             "033_provider_sentiment_jobs.sql"],
                      "bot_table": True, "sentiment_table": True,
                  })}
        self.assertIn("ia_ativa_sem_credenciais_allowlist_ou_saida",
                      cutover.assess(report, CANDIDATE)["blockers"])
        api["NetworkSettings"]["Networks"]["socialmei-team_ai-egress"] = {}
        report["containers"]["team_api"] = cutover.inspect_summary(api, "team_api")
        self.assertNotIn("ia_ativa_sem_credenciais_allowlist_ou_saida",
                         cutover.assess(report, CANDIDATE)["blockers"])
        api["Config"]["Env"] = [item for item in api["Config"]["Env"]
                                if not item.startswith("SOCIALMEI_GROQ_API_KEY=")]
        report["containers"]["team_api"] = cutover.inspect_summary(api, "team_api")
        self.assertIn("ia_ativa_sem_credenciais_allowlist_ou_saida",
                      cutover.assess(report, CANDIDATE)["blockers"])

    def test_only_git_docker_inspect_and_readonly_database_commands(self):
        used = []

        def runner(args, **kwargs):
            used.append((args, kwargs))
            if args[:3] == ["git", "-C", "/home/ubuntu/socialmei-team"]:
                return CANDIDATE + "\n" if args[3] == "rev-parse" else ""
            if args[:3] == ["docker", "inspect", "--type"]:
                name = args[-1]
                return json.dumps([container(
                    api=name.endswith("team-api-1"),
                    engine="WEBJS" if name == "socialmei-waha" else None,
                    networks=["socialmei_team_automation"] if name.endswith("team-api-1")
                    else [],
                )])
            if args[:3] == ["docker", "exec", "-i"]:
                assert kwargs["input_text"].startswith("BEGIN TRANSACTION READ ONLY;")
                return json.dumps({
                    "versions": [f"{i:03}_fixture.sql" for i in range(1, 32)] + [
                        "032_whatsapp_bot_conversations.sql",
                        "033_provider_sentiment_jobs.sql"
                    ],
                    "bot_table": True,
                    "sentiment_table": True,
                }) + "\n"
            return None

        report = cutover.collect(CANDIDATE, runner=runner)
        self.assertEqual(len(used), 8)
        self.assertTrue(report["decision"]["preflight_unblocked"])
        self.assertFalse(report["decision"]["deployment_executed"])
        self.assertFalse(report["decision"]["provider_message_sent"])
        self.assertEqual(report["containers"]["waha"]["default_engine"], "WEBJS")
        self.assertTrue(report["database"]["has_033"])
        self.assertFalse(report["database"]["ledger_has_gaps"])
        self.assertTrue(all(
            a[:2] in (["git", "-C"], ["docker", "inspect"], ["docker", "exec"])
            for a, _ in used
        ))

    def test_unsafe_public_ports_legacy_owner_and_db_network_block(self):
        report = {
            "source": {"sha": CANDIDATE, "clean": True},
            "containers": {
                name: cutover.inspect_summary(container(
                    api=name == "team_api",
                    networks=["socialmei_team_automation"] if name == "team_database" else [],
                    ports=name == "team_api",
                ), name)
                for name in cutover.CONTAINERS
            },
            "database": cutover.migration_summary({
                "versions": ["032_whatsapp_bot_conversations.sql"],
                "bot_table": True, "sentiment_table": False,
            }),
        }
        decision = cutover.assess(report, CANDIDATE)
        self.assertIn("porta_privada_exposta_no_host", decision["blockers"])
        self.assertIn("postgres_conectado_a_rede_automation", decision["blockers"])
        self.assertFalse(decision["preflight_unblocked"])

    def test_absent_service_fails_closed_and_no_credential_echo(self):
        self.assertEqual(cutover.inspect_summary(None, "waha"), {"available": False})
        summary = cutover.migration_summary({"versions": ["bad-token=SECRET"]})
        self.assertEqual(summary, {"available": False})
        source = {"sha": CANDIDATE, "clean": True}
        services = {name: {"available": False} for name in cutover.CONTAINERS}
        result = cutover.assess({
            "source": source, "containers": services, "database": {"available": False}
        }, CANDIDATE)
        self.assertIn("ledger_do_banco_indisponivel", result["blockers"])
        self.assertFalse(result["preflight_unblocked"])


if __name__ == "__main__":
    unittest.main()
