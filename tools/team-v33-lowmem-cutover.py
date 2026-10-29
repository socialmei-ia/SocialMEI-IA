#!/usr/bin/env python3
"""One-off, low-memory Team v33 migration after the operator-confirmed restore.

This does NOT repeat the heavy 512 MiB restore, or change Docker / APIs / Caddy.
The prior successful restore is *operator evidence*, not cryptographic proof.
--inspect is read-only. --apply makes a FRESH database backup first, then uses
the unchanged guarded transaction from team-v33-migrate-guarded.py.

Strictly limited to the observed AWS checkout, backup, stage and proof fingerprint.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

ROOT = Path("/home/ubuntu/socialmei-team")
BACKUPS = Path("/home/ubuntu/socialmei-backups")
HELPER = Path(__file__).with_name("team-v33-migrate-guarded.py")
ORIGINAL_BACKUP = "team-auto-20261028-234141-5dc482"
STAGE = "team-v33-c19d44b6ef6b"
STAGED_SHA = "c19d44b6ef6b8f125e6cafe60a7adfc0477cf454"
LIVE_BASE_SHA = "6f4c8e1795cbb2e9074845edd9ac099a8ea3925b"
RESTORE_FINGERPRINT = "c0ace386cc88f2ea96ad1180e21a59b536e32026a40740d2f8bca81908490e15"
MIGRATIONS = (
    "032_whatsapp_bot_conversations.sql",
    "033_provider_sentiment_jobs.sql",
)


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def local(args, *, cwd=None, timeout=30):
    try:
        r = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("comando_indisponivel") from None
    require(r.returncode == 0, "comando_falhou")
    return r.stdout


def load_guard():
    require(HELPER.is_file() and not HELPER.is_symlink(),
            "migrador_protegido_ausente")
    spec = importlib.util.spec_from_file_location("team_v33_migrator_lowmem", HELPER)
    require(spec is not None and spec.loader is not None, "migrador_protegido_invalido")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checkout_guard():
    require(ROOT.is_dir() and not ROOT.is_symlink(), "checkout_ausente")
    require(
        local(["git", "-C", str(ROOT), "rev-parse", "HEAD"]).strip()
        == LIVE_BASE_SHA,
        "checkout_foi_alterado",
    )
    status = local(
        ["git", "-C", str(ROOT), "status", "--porcelain=v1",
         "--untracked-files=all"]
    ).splitlines()
    require(status == [" M deploy/team/Caddyfile"], "checkout_hotfix_inesperado")
    require((ROOT / "tools/team-maintenance.py").is_file(),
            "rotina_de_backup_ausente")


def memory_for_ddl():
    """No secondary PG container; only enough headroom for the existing DB."""
    free_disk = shutil.disk_usage("/").free
    require(free_disk >= 2 * 1024**3, "disco_insuficiente")
    try:
        available = next(
            int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
            if line.startswith("MemAvailable:")
        ) * 1024
    except (OSError, ValueError, StopIteration):
        raise RuntimeError("memoria_indisponivel") from None
    require(available >= 128 * 1024**2, "memoria_insuficiente_para_sql")


def preflight(migrator, fingerprint):
    require(fingerprint == RESTORE_FINGERPRINT, "prova_de_restore_nao_confirmada")
    checkout_guard()
    helper, old_backup, source, names, sha, ledger, pending = migrator.check_inputs(
        ORIGINAL_BACKUP, STAGE
    )
    require(sha == STAGED_SHA and tuple(pending) == MIGRATIONS,
            "versao_ou_ledger_incompativel")
    migrator.runtime_safety()
    require(not any(migrator.live_new_tables().values()), "tabelas_sem_ledger")
    memory_for_ddl()
    return helper, old_backup, source, names, sha, ledger


def fresh_backup(migrator):
    # Existing documented backup procedure. Does not restart or modify APIs.
    output = local(
        ["python3", "tools/team-maintenance.py", "backup"],
        cwd=ROOT, timeout=300,
    )
    expected = "Backup da equipe concluído e índice conferido:"
    lines = [x.strip() for x in output.splitlines() if x.strip().startswith(expected)]
    require(len(lines) == 1, "backup_fresco_sem_recibo")
    path = Path(lines[0][len(expected):].strip())
    require(path.parent == BACKUPS and re.fullmatch(
        r"team-auto-\d{8}-\d{6}-[a-f0-9]{6}", path.name
    ), "backup_fresco_caminho_invalido")
    helper = migrator.restore_module()
    verified = helper.backup_receipt(path.name)
    require(verified == path, "backup_fresco_invalido")
    require(0 <= time.time() - (path / "concluido.json").stat().st_mtime <= 900,
            "backup_fresco_expirado")
    return path.name


def apply_with_prior_restore(fingerprint, *, apply=False):
    out = {
        "mode": "low_memory_v33_reviewed_cutover",
        "prior_restore_is_operator_attestation": True,
        "production_changed": False,
        "provider_messages_sent": False,
        "api_restarted": False,
        "phase": "preflight",
    }
    stage = "preflight"
    try:
        migrator = load_guard()
        _helper, _backup, source, names, sha, ledger = preflight(
            migrator, fingerprint
        )
        out.update({
            "stage_sha": sha,
            "production_migrations_before": len(ledger),
            "old_backup_integrity_verified": True,
        })
        if not apply:
            out["action"] = "read_only_preflight_success"
            return out, 0
        stage = "fresh_backup"
        out["phase"] = stage
        name = fresh_backup(migrator)
        out["fresh_backup_name"] = name
        out["fresh_backup_integrity_verified"] = True
        stage = "revalidate_before_transaction"
        out["phase"] = stage
        checkout_guard()
        migrator.runtime_safety()
        require(migrator.live_ledger() == names[:31],
                "ledger_mudou_antes_de_aplicar")
        require(not any(migrator.live_new_tables().values()),
                "tabelas_mudaram_antes_de_aplicar")
        memory_for_ddl()
        stage = "transaction"
        out["phase"] = stage
        migrator.pgsql(migrator.guarded_sql(source, names),
                       write=True, timeout=180)
        stage = "post_commit"
        out["phase"] = stage
        require(migrator.live_ledger() == names, "ledger_final_nao_confirmado")
        require(all(migrator.live_new_tables().values()),
                "tabelas_finais_nao_confirmadas")
        out.update({
            "action": "migrations_032_033_applied",
            "production_changed": True,
            "production_migrations_after": 33,
            "phase": "completed",
        })
        return out, 0
    except Exception:
        out.update({
            "action": "stopped",
            "error_code": "operacao_bloqueada_ou_falhou",
            "phase": stage,
            "production_change_possible": stage in {"transaction", "post_commit"},
            "next_action": "consultar_ledger_read_only_nao_repetir_apply",
        })
        return out, 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["team"])
    parser.add_argument("--prior-restore-fingerprint", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    report, status = apply_with_prior_restore(
        args.prior_restore_fingerprint, apply=args.apply
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(status)


if __name__ == "__main__":
    main()
