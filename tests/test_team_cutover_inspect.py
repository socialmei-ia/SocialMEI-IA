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
                self.assertEqual(args[3:], [cutover.CONTAINERS["team_api"], "python", "-"])
                self.assertIn("SET TRANSACTION READ ONLY", kwargs["input_text"])
                self.assertIn("from database import connect", kwargs["input_text"])
                return json.dumps({
                    "versions": [f"{i:03}_fixture.sql" for i in range(1, 32)] + sorted(cutover.KNOWN_LATE_MIGRATIONS),
                    "bot_table": True,
                    "sentiment_table": True,
                    "instagram_menu_table": True,
                    "instagram_replies_table": True,
                }) + "\n"
            return None

        report = cutover.collect(CANDIDATE, runner=runner, root="/home/ubuntu/socialmei-team")
        self.assertEqual(len(used), 8)
        self.assertTrue(report["decision"]["preflight_unblocked"])
        self.assertFalse(report["decision"]["deployment_executed"])
        self.assertFalse(report["decision"]["provider_message_sent"])
        self.assertEqual(report["containers"]["waha"]["default_engine"], "WEBJS")
        self.assertTrue(report["database"]["has_033"])
        self.assertFalse(report["database"]["ledger_has_gaps"])
        self.assertEqual(report["database_source"], "effective_api_connection")
        self.assertTrue(all(
            a[:2] in (["git", "-C"], ["docker", "inspect"], ["docker", "exec"])
            for a, _ in used
        ))

    def test_failed_api_connection_never_falls_back_to_local_postgres(self):
        used = []

        def runner(args, **kwargs):
            used.append(args)
            if args[0] == "git":
                return CANDIDATE if args[3] == "rev-parse" else ""
            if args[:2] == ["docker", "exec"]:
                return '{"available": false}'
            return json.dumps([container(api=args[-1].endswith("team-api-1"))])

        report = cutover.collect(CANDIDATE, runner=runner)
        self.assertFalse(report["database"]["available"])
        self.assertIn("ledger_do_banco_indisponivel", report["decision"]["blockers"])
        probes = [args for args in used if args[:2] == ["docker", "exec"]]
        self.assertEqual(len(probes), 1)
        self.assertEqual(probes[0][3], cutover.CONTAINERS["team_api"])

    def test_effective_probe_is_read_only_and_sanitizes_connection_errors(self):
        import sys
        import types
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        module = types.ModuleType("database")
        def fail():
            raise RuntimeError("PRIVATE_DATABASE_PASSWORD")
        module.connect = fail
        output = StringIO()
        with patch.dict(sys.modules, {"database": module}), redirect_stdout(output):
            exec(cutover.API_DATABASE_PROBE, {})
        self.assertEqual(json.loads(output.getvalue()), {
            "available": False, "reason": "connection_or_schema_unavailable"})
        self.assertNotIn("PRIVATE_DATABASE_PASSWORD", output.getvalue())
        self.assertIn("conn.rollback()", cutover.API_DATABASE_PROBE)
        self.assertIn("statement_timeout", cutover.API_DATABASE_PROBE)
        self.assertNotIn("PRIVATE", json.dumps(cutover.migration_summary({
            "available": False, "reason": "PRIVATE"})))

    def test_smtp_readiness_exposes_only_presence_and_tls(self):
        raw = container(api=True)
        raw["Config"]["Env"] += ["SOCIALMEI_RECOVERY_MODE=smtp"] + [
            "SOCIALMEI_SMTP_" + key + "=PRIVATE_MAIL_VALUE"
            for key in ("HOST", "USER", "PASSWORD", "FROM")
        ] + ["SOCIALMEI_SMTP_PORT=25"]
        flags = cutover.inspect_summary(raw, "team_api")["flags"]
        self.assertTrue(flags["smtp_fields_present"])
        self.assertFalse(flags["smtp_tls_port"])
        self.assertEqual(flags["recovery_mode"], "smtp")
        self.assertNotIn("PRIVATE_MAIL_VALUE", json.dumps(flags))

    def test_probe_handles_psycopg_text_and_json_results(self):
        import sys
        import types
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import MagicMock, patch

        ledger = {"versions": [f"{i:03}_fixture.sql" for i in range(1, 32)]
                  + sorted(cutover.KNOWN_LATE_MIGRATIONS),
                  "bot_table": True, "sentiment_table": True,
                  "instagram_menu_table": True, "instagram_replies_table": True}
        for raw in (ledger, json.dumps(ledger)):
            with self.subTest(raw_type=type(raw).__name__):
                conn = MagicMock()
                conn.execute.return_value.fetchone.return_value = (raw,)
                module = types.ModuleType("database")
                module.connect = MagicMock()
                module.connect.return_value.__enter__.return_value = conn
                output = StringIO()
                with patch.dict(sys.modules, {"database": module}), redirect_stdout(output):
                    exec(cutover.API_DATABASE_PROBE, {})
                self.assertEqual(json.loads(output.getvalue()), ledger)
                self.assertTrue(cutover.migration_summary(json.loads(output.getvalue()))["has_039"])
                conn.rollback.assert_called_once()
                self.assertEqual(conn.execute.call_args_list[0].args, ("SET TRANSACTION READ ONLY",))

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
