#!/usr/bin/env python3
"""Read-only diagnosis following a stopped Team 032/033 migration attempt.

Checks *actual* database state and preflight gates. It never applies SQL,
starts/stops containers, accesses credentials, or prints private records.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess

MIGRATOR = Path(__file__).with_name("team-v33-migrate-guarded.py")
VERSION_032 = "032_whatsapp_bot_conversations.sql"
VERSION_033 = "033_provider_sentiment_jobs.sql"
LABEL = "socialmei.team.backup_restore_trial"

# Only diagnostic phase identifiers and enumerated error codes are displayed.
KNOWN_CODES = frozenset({
    "helper_de_restauracao_ausente", "helper_de_restauracao_invalido",
    "comando_indisponivel", "comando_falhou", "docker_local_indisponivel",
    "nome_backup_invalido", "diretorio_invalido", "permissoes_privadas_invalidas",
    "arquivo_privado_invalido", "permissoes_arquivo_invalidas",
    "recibo_invalido", "inventario_backup_invalido", "hash_backup_divergente",
    "dump_vazio", "nome_stage_invalido", "recibo_stage_invalido",
    "stage_nao_aprovado", "fonte_stage_ausente", "fonte_stage_foi_trocada",
    "fonte_stage_modificada", "migrations_nao_revisadas", "migration_invalida",
    "hash_migration_divergente", "migrations_de_fonte_invalidas",
    "ledger_producao_indisponivel", "ledger_producao_invalido",
    "estado_tabelas_indisponivel", "estado_tabelas_invalido",
    "container_invalido", "container_nao_saudavel", "porta_interna_exposta",
    "api_nao_saudavel", "banco_nao_saudavel", "rede_banco_ambigua",
    "banco_na_rede_de_automacao", "autenticacao_desligada",
    "waha_ingress_ativo_bloqueia_migracao",
    "provedor_ativo_bloqueia_migracao", "ledger_nao_e_prefixo",
    "baseline_nao_revisada", "ledger_033_sem_tabelas",
    "tabelas_novas_sem_ledger", "espaco_insuficiente",
    "memoria_insuficiente", "memoria_indisponivel",
})


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def load_migrator():
    require(MIGRATOR.is_file() and not MIGRATOR.is_symlink(),
            "helper_de_restauracao_ausente")
    spec = importlib.util.spec_from_file_location("team_v33_migration_gate", MIGRATOR)
    require(spec is not None and spec.loader is not None,
            "helper_de_restauracao_invalido")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checked(out, name, fn):
    try:
        value = fn()
        out["checks"][name] = "ok"
        return value
    except Exception as exc:
        msg = str(exc) if isinstance(exc, RuntimeError) else ""
        out["checks"][name] = msg if msg in KNOWN_CODES else "erro_interno_sanitizado"
        return None


def orphan_counts():
    """Read-only Docker metadata; never list resource names or secret labels."""
    result = []
    for args in (
        ("ps", "-aq", "--filter", f"label={LABEL}"),
        ("volume", "ls", "-q", "--filter", f"label={LABEL}"),
    ):
        try:
            response = subprocess.run(
                ["docker", "--host=unix:///var/run/docker.sock", *args],
                capture_output=True, text=True, check=False, timeout=12,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"available": False}
        if response.returncode != 0:
            return {"available": False}
        result.append(len([x for x in response.stdout.splitlines() if x.strip()]))
    return {
        "available": True,
        "owned_temporary_containers": result[0],
        "owned_temporary_volumes": result[1],
    }


def inspect(backup_name, stage_name):
    out = {
        "mode": "read_only_after_stopped_migration",
        "production_write_attempted_by_diagnostic": False,
        "provider_messages_sent_by_diagnostic": False,
        "api_restarted_by_diagnostic": False,
        "checks": {},
    }
    migrator = checked(out, "load_code", load_migrator)
    if migrator is None:
        out["decision"] = "diagnostico_incompleto_sem_modificacoes"
        return out
    helper = checked(out, "load_restore_helper", migrator.restore_module)
    if helper is not None:
        backup = checked(out, "backup_integrity",
                         lambda: helper.backup_receipt(backup_name))
        stage = checked(out, "stage_integrity",
                        lambda: helper.stage_receipt(stage_name))
    else:
        backup = stage = None
    ledger = checked(out, "production_ledger", migrator.live_ledger)
    tables = checked(out, "production_new_tables", migrator.live_new_tables)
    checked(out, "runtime_health_and_disabled_providers", migrator.runtime_safety)
    out["temporary_restore_resources"] = orphan_counts()

    if backup is not None:
        checked(out, "restore_resource_capacity",
                lambda: helper.disk_memory_preflight(
                    (backup / "equipe.dump").stat().st_size
                ))
    if stage is not None:
        source, names, sha = stage
        out["staged_candidate_sha"] = sha
        out["source_migrations"] = len(names)
        out["stage_matches_reviewed_033"] = (
            len(names) == 33
            and names[-2:] == [VERSION_032, VERSION_033]
        )
    if ledger is not None:
        out["production_migration_count"] = len(ledger)
        out["production_ledger_tail"] = (
            int(ledger[-1][:3]) if ledger and re.fullmatch(r"\d{3}_.+\.sql", ledger[-1])
            else None
        )
        if stage is not None:
            names = stage[1]
            out["production_ledger_matches_stage_prefix"] = (
                ledger == names[:len(ledger)]
            )
    if tables is not None:
        out["new_tables_present"] = tables
        out["all_033_tables_present"] = all(tables.values())
        out["no_033_tables_present"] = not any(tables.values())

    errors = [name for name, status in out["checks"].items() if status != "ok"]
    if errors:
        out["decision"] = "corrigir_bloqueio_sem_repetir_apply"
        out["failing_phases"] = errors
    elif ledger is not None and stage is not None:
        if ledger == stage[1][:31] and tables is not None and not any(tables.values()):
            out["decision"] = "schema_031_confirmado_diagnosticar_falha_durante_apply"
        elif ledger == stage[1] and tables is not None and all(tables.values()):
            out["decision"] = "schema_033_confirmado_nao_reaplicar"
        else:
            out["decision"] = "drift_exige_revisao_sem_reaplicar"
    else:
        out["decision"] = "diagnostico_incompleto_sem_modificacoes"
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    parser.add_argument("--backup", required=True)
    parser.add_argument("--stage", required=True)
    args = parser.parse_args()
    report = inspect(args.backup, args.stage)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["decision"] not in {
        "schema_031_confirmado_diagnosticar_falha_durante_apply",
        "schema_033_confirmado_nao_reaplicar",
    }:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
