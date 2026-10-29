#!/usr/bin/env python3
"""Migrate the *existing* Team database to 033, after repeating a real restore trial.

--inspect is read-only. --apply is an explicit opt-in, atomic database DDL action.
Never deploy, change containers/images/Caddy/volumes, or enable provider sending.
Run only on the authorized Ubuntu host with the matching restore helper beside this file.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

RESTORE_TOOL = Path(__file__).with_name("team-v33-restore-rehearsal.py")
DB_CONTAINER = "socialmei-team-team-postgres-1"
API_CONTAINER = "socialmei-team-team-api-1"
LOCK_KEY = 72426001
EXPECTED_SUFFIX = (
    "032_whatsapp_bot_conversations.sql",
    "033_provider_sentiment_jobs.sql",
)


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def restore_module():
    require(RESTORE_TOOL.is_file() and not RESTORE_TOOL.is_symlink(),
            "helper_de_restauracao_ausente")
    spec = importlib.util.spec_from_file_location("team_v33_restore", RESTORE_TOOL)
    require(spec is not None and spec.loader is not None, "helper_de_restauracao_invalido")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(args, *, input_text=None, timeout=30):
    """Capture and discard raw Docker/psql diagnostics which may contain secrets."""
    try:
        result = subprocess.run(
            args, input=input_text, text=True, capture_output=True,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("comando_indisponivel") from None
    require(result.returncode == 0, "comando_falhou")
    return result.stdout


def docker(*args, **kw):
    require(Path("/var/run/docker.sock").is_socket(), "docker_local_indisponivel")
    return command(["docker", "--host=unix:///var/run/docker.sock", *args], **kw)


def pgsql(sql, *, write=False, timeout=30):
    # Literal shell script is fixed here. POSTGRES_* are expanded only inside
    # the trusted, existing database container; no passwords in arguments.
    script = 'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1'
    args = [
        "exec", "-i", DB_CONTAINER, "sh", "-c",
        script + (" -q -1 -f -" if write else " -At"),
    ]
    return docker(*args, input_text=sql, timeout=timeout)


def live_ledger():
    query = (
        "BEGIN TRANSACTION READ ONLY;\n"
        "SELECT COALESCE(json_agg(version ORDER BY version), '[]'::json)::text "
        "FROM socialmei.schema_migrations;\n"
        "ROLLBACK;\n"
    )
    response = pgsql(query)
    lines = [s.strip() for s in response.splitlines() if s.strip().startswith("[")]
    require(len(lines) == 1, "ledger_producao_indisponivel")
    ledger = json.loads(lines[0])
    require(isinstance(ledger, list) and all(
        isinstance(v, str) and re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", v)
        for v in ledger
    ), "ledger_producao_invalido")
    return ledger


def runtime_safety():
    data = {}
    for name in (API_CONTAINER, DB_CONTAINER):
        raw = json.loads(docker("inspect", "--type", "container", name))
        require(isinstance(raw, list) and len(raw) == 1, "container_invalido")
        obj = raw[0]
        require(obj.get("Name") == "/" + name
                and obj.get("State", {}).get("Running") is True,
                "container_nao_saudavel")
        require(not (obj.get("HostConfig", {}).get("PortBindings") or {}),
                "porta_interna_exposta")
        nets = set((obj.get("NetworkSettings") or {}).get("Networks") or {})
        data[name] = {"state": obj["State"], "networks": nets,
                      "env": obj.get("Config", {}).get("Env") or []}
    require(data[API_CONTAINER]["state"].get("Health", {}).get("Status") == "healthy",
            "api_nao_saudavel")
    require(data[DB_CONTAINER]["state"].get("Health", {}).get("Status") == "healthy",
            "banco_nao_saudavel")
    require(len(data[API_CONTAINER]["networks"] & data[DB_CONTAINER]["networks"]) == 1,
            "rede_banco_ambigua")
    require("socialmei_team_automation" not in data[DB_CONTAINER]["networks"],
            "banco_na_rede_de_automacao")
    env = {}
    for item in data[API_CONTAINER]["env"]:
        if "=" in item:
            k, v = item.split("=", 1)
            env[k] = v
    require(env.get("SOCIALMEI_AUTH_ENABLED", "").strip().lower()
            in {"true", "1", "yes", "on"}, "autenticacao_desligada")
    for key in (
        "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED",
        "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED",
        "SOCIALMEI_INSTAGRAM_PUBLISH_ENABLED",
        "SOCIALMEI_WHATSAPP_BOT_ENABLED",
        "SOCIALMEI_PROVIDER_SENTIMENT_ENABLED",
    ):
        require(env.get(key, "false").strip().lower() in {"", "false", "0"},
                "provedor_ativo_bloqueia_migracao")
    return True


def check_inputs(backup_name, stage_name):
    helper = restore_module()
    backup = helper.backup_receipt(backup_name)
    source, names, sha = helper.stage_receipt(stage_name)
    require(tuple(names[-2:]) == EXPECTED_SUFFIX, "migrations_de_fonte_invalidas")
    require(len(names) == 33 and len(set(names)) == 33, "migrations_de_fonte_invalidas")
    for version in names:
        require(re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", version),
                "migrations_de_fonte_invalidas")
    live = live_ledger()
    require(live == names[:len(live)], "ledger_nao_e_prefixo")
    require(len(live) in (31, 33), "baseline_nao_revisada")
    if len(live) == 33:
        pending = []
    else:
        pending = names[31:]
    return helper, backup, source, names, sha, live, pending


def guarded_sql(source, names):
    """Only source-reviewed SQL in one transaction, under the app migration lock."""
    require(len(names) == 33 and tuple(names[-2:]) == EXPECTED_SUFFIX,
            "migrations_nao_revisadas")
    known = json.dumps(names[:31], separators=(",", ":"))
    require("'" not in known, "ledger_literal_invalido")
    script = [
        "SET LOCAL lock_timeout = '5s';",
        "SET LOCAL statement_timeout = '120s';",
        f"SELECT pg_advisory_xact_lock({LOCK_KEY});",
        "DO $team_migration_guard$",
        "BEGIN",
        "  IF (SELECT COALESCE(jsonb_agg(version ORDER BY version), '[]'::jsonb)",
        "      FROM socialmei.schema_migrations) <> '" + known.replace("'", "''") + "'::jsonb THEN",
        "    RAISE EXCEPTION 'Team ledger changed during migration';",
        "  END IF;",
        "END;",
        "$team_migration_guard$;",
    ]
    for name in EXPECTED_SUFFIX:
        file = source / "database/migrations" / name
        require(file.is_file() and not file.is_symlink(), "migration_invalida")
        content = file.read_text()
        require(content.strip() and len(content) < 20000, "migration_invalida")
        script.append(content)
        script.append(
            "INSERT INTO socialmei.schema_migrations(version) VALUES ('" + name + "');"
        )
    return "\n".join(script) + "\n"


def restore_trial(helper, backup, source, names):
    helper.disk_memory_preflight((backup / "equipe.dump").stat().st_size)
    trial = helper.Rehearsal()
    valid = False
    cleanup_ok = False
    try:
        result = trial.execute(backup, source, names)
        valid = all(result.get(k) is True for k in (
            "restore_verified", "migration_032_033_rehearsed",
            "original_rowcounts_preserved",
        ))
    finally:
        problems = trial.cleanup()
        cleanup_ok = not problems
    require(cleanup_ok, "recursos_temporarios_pendentes")
    require(valid, "ensaio_restauracao_reprovado")
    return True


def run(backup_name, stage_name, *, apply=False):
    helper, backup, source, names, sha, live, pending = check_inputs(
        backup_name, stage_name
    )
    runtime_safety()
    report = {
        "target": "team",
        "stage_sha": sha,
        "production_migration_count_before": len(live),
        "pending_migrations": pending,
        "backup_checksum_verified": True,
        "runtime_safety_verified": True,
        "production_changed": False,
        "provider_messages_sent": False,
        "api_restarted": False,
    }
    if not apply:
        report["action"] = "read_only_inspection"
        return report
    if not pending:
        report["action"] = "already_at_033"
        return report
    require(tuple(pending) == EXPECTED_SUFFIX, "migrations_pendentes_inesperadas")
    restore_trial(helper, backup, source, names)
    # Guard again after the potentially long restore, before any real DB write.
    runtime_safety()
    require(live_ledger() == names[:31], "ledger_mudou_antes_da_aplicacao")
    pgsql(guarded_sql(source, names), write=True, timeout=180)
    require(live_ledger() == names, "ledger_final_nao_confirmado")
    report.update({
        "action": "applied_032_033",
        "production_changed": True,
        "migration_count_after": 33,
        "restore_trial_rerun_successfully": True,
        "provider_messages_sent": False,
        "api_restarted": False,
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["team"])
    parser.add_argument("--backup", required=True, help="Backup folder name only")
    parser.add_argument("--stage", required=True, help="Stage folder name only")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        report = run(args.backup, args.stage, apply=args.apply)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception:
        print(json.dumps({
            "target": "team", "action": "stopped",
            "reason": "preflight_ou_migration_reprovado",
            "production_may_have_changed": bool(args.apply),
            "provider_messages_sent": False, "api_restarted": False,
            "next_action": "verificar_ledger_e_logs_locais_sem_repetir_as_cegas",
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
