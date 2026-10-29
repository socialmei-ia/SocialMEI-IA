"""Offline contracts for Team v33 read-only runtime and image handoff audit."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "team_v33_audit",
    Path(__file__).resolve().parents[1] / "tools/team-v33-runtime-audit.py",
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def service(name, *, networks=None, mounts=None, env=None):
    service_name = name.removeprefix("socialmei-team-").removesuffix("-1")
    return {
        "Name": "/" + name,
        "Image": "sha256:" + "a" * 64,
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "HostConfig": {"PortBindings": {}},
        "Config": {
            "Labels": {
                "com.docker.compose.project": "socialmei-team",
                "com.docker.compose.service": service_name,
                "com.docker.compose.project.config_files":
                    "/home/ubuntu/socialmei-team/compose.team.yaml",
                "com.docker.compose.project.working_dir":
                    "/home/ubuntu/socialmei-team",
            },
            "Env": env or [],
        },
        "NetworkSettings": {
            "Networks": {name: {} for name in networks or []},
        },
        "Mounts": mounts or [],
    }


class RuntimeAuditTests(unittest.TestCase):
    def test_runtime_topology_preserves_egress_and_private_gateway(self):
        api = service(audit.API_NAME, networks=[
            "socialmei-team_api", "socialmei-team_database",
            "socialmei_team_egress"
        ], env=["SOCIALMEI_AUTH_ENABLED=true",
                "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED=false"])
        db = service(audit.DB_NAME, networks=["socialmei-team_database"])
        mount = lambda target: {
            "Type": "bind", "RW": False,
            "Destination": target, "Source": "/private/" + target.lstrip("/").replace("/", "_"),
        }
        gw = service(audit.GATEWAY_NAME, networks=[
            "socialmei-team_api", "socialmei_team_web",
        ], mounts=[mount(target) for target in audit.EXPECTED_MOUNTS])
        summary = audit.container_summary(audit.API_NAME, api)
        self.assertIn("socialmei_team_egress", summary["networks"])
        self.assertEqual(audit.env_flags(api)["providers_disabled"], True)
        self.assertEqual(
            set(audit.container_summary(audit.GATEWAY_NAME, gw)["bind_targets_readonly"]),
            set(audit.EXPECTED_MOUNTS),
        )
        self.assertEqual(
            set(summary["networks"]) & set(
                audit.container_summary(audit.DB_NAME, db)["networks"]),
            {"socialmei-team_database"},
        )
        self.assertNotIn("socialmei_team_automation",
                         audit.container_summary(audit.DB_NAME, db)["networks"])

    def test_no_provider_send_or_wa_ingress_can_be_enabled(self):
        base = ["SOCIALMEI_AUTH_ENABLED=true"]
        for key in audit.SENSITIVE_FLAGS:
            item = service(audit.API_NAME, env=base + [key + "=true"])
            with self.assertRaisesRegex(RuntimeError, "envios_ou_ingresso_ativos"):
                audit.env_flags(item)
        with self.assertRaisesRegex(RuntimeError, "ingresso_waha_ativo"):
            audit.env_flags(service(audit.API_NAME, env=base + [
                "SOCIALMEI_WAHA_INGRESS_MODE=connect"
            ]))
        with self.assertRaisesRegex(RuntimeError, "auth_nao_confirmada"):
            audit.env_flags(service(audit.API_NAME, env=[
                "SOCIALMEI_AUTH_ENABLED=false"
            ]))

    def test_gateway_mounts_must_be_private_readonly_and_identical_in_container(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "Caddyfile"
            source.write_text(":80 { respond \"ok\" }\n")
            mounts = [
                {"Type": "bind", "Source": str(source),
                 "Destination": "/etc/caddy/Caddyfile", "RW": False},
                {"Type": "bind", "Source": str(source),
                 "Destination": "/etc/caddy/private", "RW": False},
                {"Type": "bind", "Source": str(source),
                 "Destination": "/srv/frontend/config.js", "RW": False},
            ]
            gateway = service(audit.GATEWAY_NAME, mounts=mounts)
            summary = audit.container_summary(audit.GATEWAY_NAME, gateway)
            expected = audit.hashlib.sha256(source.read_bytes()).hexdigest()
            with patch.object(audit, "docker",
                              return_value=expected + "  /etc/caddy/Caddyfile\n"):
                result = audit.gateway_guard(gateway, summary)
            self.assertTrue(result["private_caddyfile_mounted_readonly"])
            self.assertEqual(result["private_caddyfile_sha256"], expected)
            gateway["Mounts"][0]["RW"] = True
            bad = audit.container_summary(audit.GATEWAY_NAME, gateway)
            with self.assertRaisesRegex(RuntimeError, "montagem_privada"):
                audit.gateway_guard(gateway, bad)

    def test_container_checks_dont_expose_secret_environment(self):
        api = service(audit.API_NAME, networks=[
            "socialmei-team_api", "socialmei-team_database"
        ], env=[
            "SOCIALMEI_AUTH_ENABLED=true",
            "SOCIALMEI_INSTAGRAM_CLIENT_SECRET=sensitive-secret-value"
        ])
        report = audit.container_summary(audit.API_NAME, api)
        flags = audit.env_flags(api)
        self.assertNotIn("sensitive-secret-value", str(report) + str(flags))
        self.assertNotIn("SOCIALMEI_INSTAGRAM_CLIENT_SECRET",
                         str(report) + str(flags))
        api["HostConfig"]["PortBindings"] = {"8000/tcp": [{"HostPort": "8000"}]}
        with self.assertRaisesRegex(RuntimeError, "porta_publicada_no_team"):
            audit.container_summary(audit.API_NAME, api)

    def test_database_ledger_query_read_only_and_four_table_check(self):
        queries = []
        names = [f"{i:03}_example.sql" for i in range(1, 34)]
        import json
        responses = iter([
            json.dumps(names) + "\nROLLBACK\n",
            json.dumps({table: True for table in audit.EXPECTED_NEW_TABLES}) +
            "\nROLLBACK\n",
        ])
        with patch.object(audit, "docker",
                          side_effect=lambda *args, **kw:
                          queries.append((args, kw)) or next(responses)):
            audit.ledger_current(names)
        self.assertEqual(len(queries), 2)
        for args, opts in queries:
            self.assertEqual(args[:3], ("exec", "-i", audit.DB_NAME))
            self.assertIn("BEGIN TRANSACTION READ ONLY", opts["input_text"])
            self.assertIn("ROLLBACK", opts["input_text"])
            self.assertNotIn("UPDATE ", opts["input_text"])
            self.assertNotIn("INSERT ", opts["input_text"])


if __name__ == "__main__":
    unittest.main()
