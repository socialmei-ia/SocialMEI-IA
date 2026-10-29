#!/usr/bin/env python3
"""Restore a real Team backup into an owned, offline PostgreSQL 16 container.

Opt-in only; NEVER connect to, restart, migrate or query the live Team DB.
No host ports, no network, no Docker Compose, no live credentials or messages.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import subprocess
import time

BACKUPS = Path("/home/ubuntu/socialmei-backups")
IMAGE = "postgres:16-alpine"
LABEL = "socialmei.team.backup_restore_trial"
NAMES = ("equipe.dump", "configuracao.tar.gz", "conteudo.txt")
VERSION_032 = "032_whatsapp_bot_conversations.sql"
VERSION_033 = "033_provider_sentiment_jobs.sql"
LEDGER_QUERY = "SELECT COALESCE(json_agg(version ORDER BY version),'[]'::json) FROM socialmei.schema_migrations;"
COUNTS_QUERY = """CREATE TEMP TABLE _restore_counts (name text PRIMARY KEY, n bigint);
DO $plpgsql$
DECLARE t record; n bigint;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='socialmei' LOOP
    EXECUTE format('SELECT COUNT(*) FROM %I.%I', 'socialmei', t.tablename) INTO n;
    INSERT INTO _restore_counts VALUES(t.tablename, n);
  END LOOP;
END
$plpgsql$;
SELECT COALESCE(json_object_agg(name,n ORDER BY name),'{}'::json) FROM _restore_counts;
"""


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def private_dir(folder):
    require(folder.is_dir() and not folder.is_symlink(), "diretorio_invalido")
    info = folder.stat()
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "permissoes_privadas_invalidas")


def regular_private(path):
    require(path.is_file() and not path.is_symlink(), "arquivo_privado_invalido")
    info = path.stat()
    require(info.st_uid == os.geteuid() and not stat.S_IMODE(info.st_mode) & 0o077,
            "permissoes_arquivo_invalidas")


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def backup_receipt(name):
    require(re.fullmatch(r"team-auto-\d{8}-\d{6}-[a-f0-9]{6}", name), "nome_backup_invalido")
    private_dir(BACKUPS)
    folder = BACKUPS / name
    private_dir(folder)
    regular_private(folder / "concluido.json")
    receipt = json.loads((folder / "concluido.json").read_text())
    require(receipt.get("formato") == "socialmei-team-backup"
            and receipt.get("workspace") == "team", "recibo_invalido")
    hashes = receipt.get("sha256")
    require(isinstance(hashes, dict) and set(hashes) == set(NAMES), "inventario_backup_invalido")
    for item in NAMES:
        file = folder / item
        regular_private(file)
        require(re.fullmatch("[0-9a-f]{64}", hashes[item])
                and checksum(file) == hashes[item], "hash_backup_divergente")
    require((folder / "equipe.dump").stat().st_size > 128, "dump_vazio")
    return folder


def stage_receipt(name):
    require(re.fullmatch(r"team-v33-[a-f0-9]{12}", name), "nome_stage_invalido")
    folder = BACKUPS / name
    private_dir(folder)
    regular_private(folder / "stage-receipt.json")
    receipt = json.loads((folder / "stage-receipt.json").read_text())
    sha = receipt.get("candidate_sha")
    require(isinstance(sha, str) and re.fullmatch("[0-9a-f]{40}", sha)
            and sha.startswith(name[len("team-v33-"):]), "recibo_stage_invalido")
    require(receipt.get("stage_clean") is True
            and receipt.get("checkout_original_preservado") is True
            and receipt.get("deployment_executed") is False,
            "stage_nao_aprovado")
    source = folder / "source"
    require(source.is_dir() and not source.is_symlink(), "fonte_stage_ausente")
    names = sorted(path.name for path in (source / "database/migrations").glob("*.sql"))
    require(len(names) == 33 and len(set(names)) == 33, "migrations_nao_revisadas")
    require(all(re.fullmatch(r"\d{3}_[a-z0-9_]+\.sql", x)
                and x[:3] == f"{i:03}" for i, x in enumerate(names, 1)),
            "migrations_nao_revisadas")
    require(names[-2:] == [VERSION_032, VERSION_033], "migrations_nao_revisadas")
    for migration in names[-2:]:
        file = source / "database/migrations" / migration
        require(file.is_file() and not file.is_symlink(), "migration_invalida")
        require(checksum(file) == receipt.get("new_migration_sha256", {}).get(migration),
                "hash_migration_divergente")
    return source, names, sha


def command(args, *, input_text=None, timeout=30):
    """Never show stdout/stderr or an exception originating in a subprocess."""
    try:
        outcome = subprocess.run(args, input=input_text, text=True,
                                 capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("comando_indisponivel") from None
    require(outcome.returncode == 0, "comando_falhou")
    return outcome.stdout


def docker(*args, **kwargs):
    require(Path("/var/run/docker.sock").is_socket(), "docker_local_indisponivel")
    return command(["docker", "--host=unix:///var/run/docker.sock", *args], **kwargs)


def json_query(container, sql):
    raw = docker("exec", "-i", container, "psql", "-X", "-U", "restore_trial",
                 "-d", "restore_trial", "-v", "ON_ERROR_STOP=1", "-At",
                 input_text=sql, timeout=60)
    rows = [line.strip() for line in raw.splitlines() if line.strip().startswith(("[", "{"))]
    require(len(rows) == 1, "consulta_restore_invalida")
    return json.loads(rows[0])


def disk_memory_preflight(dump_size):
    free = shutil.disk_usage("/").free
    require(free >= max(4 * 1024 ** 3, 8 * dump_size), "espaco_insuficiente")
    try:
        mem = next(line for line in Path("/proc/meminfo").read_text().splitlines()
                   if line.startswith("MemAvailable:"))
        available = int(mem.split()[1]) * 1024
    except (OSError, StopIteration, ValueError):
        raise RuntimeError("memoria_indisponivel") from None
    require(available >= 512 * 1024 ** 2, "memoria_insuficiente")


def validate_trial(inspect, name, volume, label):
    require(isinstance(inspect, list) and len(inspect) == 1, "trial_inspect_invalido")
    instance = inspect[0]
    cfg = instance.get("Config") or {}
    host = instance.get("HostConfig") or {}
    networks = instance.get("NetworkSettings") or {}
    mounts = instance.get("Mounts") or []
    require(cfg.get("Labels", {}).get(LABEL) == label
            and instance.get("Name") == "/" + name, "trial_identidade_invalida")
    require(host.get("NetworkMode") == "none"
            and not host.get("PortBindings")
            and not (networks.get("Ports") or {}), "trial_rede_invalida")
    require(any(m.get("Type") == "volume" and m.get("Name") == volume
                and m.get("Destination") == "/var/lib/postgresql/data"
                for m in mounts), "trial_volume_invalido")
    require(host.get("Privileged") is not True, "trial_privilegio_invalido")


def restore_sql(sql):
    require(isinstance(sql, dict), "counts_invalido")
    require(all(isinstance(k, str) and re.fullmatch("[a-z][a-z0-9_]*", k)
                and type(v) is int and v >= 0 for k, v in sql.items()), "counts_invalido")
    return sql


class Rehearsal:
    def __init__(self):
        self.token = secrets.token_hex(9)
        self.name = "socialmei-restore-" + self.token
        self.volume = "socialmei-restore-data-" + self.token
        self.created_volume = False
        self.created_container = False
        self.cleaned = False

    def assert_owned_container(self):
        data = json.loads(docker("inspect", "--type", "container", self.name))
        validate_trial(data, self.name, self.volume, self.token)

    def assert_owned_volume(self):
        entries = json.loads(docker("volume", "inspect", self.volume))
        require(len(entries) == 1 and entries[0].get("Labels", {}).get(LABEL) == self.token
                and entries[0].get("Name") == self.volume, "volume_identidade_invalida")

    def start(self, dump, migrations):
        docker("image", "inspect", IMAGE)
        docker("volume", "create", "--label", LABEL + "=" + self.token, self.volume)
        self.created_volume = True
        self.assert_owned_volume()
        docker(
            "run", "-d", "--pull", "never", "--name", self.name,
            "--label", LABEL + "=" + self.token,
            "--network", "none", "--memory", "512m", "--memory-swap", "512m",
            "--cpus", "1", "--pids-limit", "128", "--security-opt", "no-new-privileges",
            "-e", "POSTGRES_USER=restore_trial", "-e", "POSTGRES_DB=restore_trial",
            "-e", "POSTGRES_HOST_AUTH_METHOD=trust",
            "--mount", f"type=volume,src={self.volume},dst=/var/lib/postgresql/data",
            "--mount", f"type=bind,src={dump},dst=/backup/equipe.dump,readonly",
            "--mount", f"type=bind,src={migrations},dst=/candidate/migrations,readonly",
            IMAGE, timeout=45,
        )
        self.created_container = True
        self.assert_owned_container()
        for _ in range(80):
            result = command(
                ["docker", "--host=unix:///var/run/docker.sock", "exec", self.name,
                 "pg_isready", "-h", "/var/run/postgresql", "-U", "restore_trial",
                 "-d", "restore_trial"],
                timeout=3,
            ) if False else None
            # Poll without printing status or logs from the temporary server.
            try:
                docker("exec", self.name, "pg_isready", "-h", "/var/run/postgresql",
                       "-U", "restore_trial", "-d", "restore_trial", timeout=3)
                break
            except RuntimeError:
                time.sleep(.5)
        else:
            raise RuntimeError("postgres_temporario_indisponivel")

    def cleanup(self):
        errors = []
        if self.created_container:
            try:
                self.assert_owned_container()
                docker("rm", "-f", "-v", self.name, timeout=35)
            except RuntimeError:
                errors.append("container")
        if self.created_volume:
            try:
                self.assert_owned_volume()
                docker("volume", "rm", self.volume, timeout=35)
            except RuntimeError:
                errors.append("volume")
        self.cleaned = not errors
        return errors

    def execute(self, backup, source, versions):
        dump = backup / "equipe.dump"
        self.start(dump, source / "database/migrations")
        docker("exec", self.name, "pg_restore",
               "-U", "restore_trial", "-d", "restore_trial",
               "--no-owner", "--no-privileges", "--single-transaction",
               "--exit-on-error", "/backup/equipe.dump", timeout=270)
        existing = json_query(self.name, LEDGER_QUERY)
        require(existing == versions[:31], "ledger_restaurado_incompativel")
        before = restore_sql(json_query(self.name, COUNTS_QUERY))
        require("schema_migrations" in before and len(before) >= 10, "schema_restaurado_incompleto")
        steps = "BEGIN;\nSET LOCAL lock_timeout='5s';\nSET LOCAL statement_timeout='90s';\n"
        for name in versions[-2:]:
            sql_file = source / "database/migrations" / name
            steps += sql_file.read_text() + "\n"
            steps += (
                "INSERT INTO socialmei.schema_migrations(version) VALUES ('"
                + name + "');\n"
            )
        steps += "COMMIT;\n"
        docker("exec", "-i", self.name, "psql", "-X", "-U", "restore_trial",
               "-d", "restore_trial", "-v", "ON_ERROR_STOP=1", "-q",
               input_text=steps, timeout=140)
        final_versions = json_query(self.name, LEDGER_QUERY)
        require(final_versions == versions, "ledger_033_incompativel")
        after = restore_sql(json_query(self.name, COUNTS_QUERY))
        require(all(after.get(k) == v for k, v in before.items()),
                "dados_originais_alterados")
        new_tables = {"wa_bot_access", "wa_bot_conversations", "me_provider_sentiment_jobs"}
        require(new_tables.issubset(after), "tabelas_032_033_incompletas")
        return {
            "restore_verified": True,
            "migration_032_033_rehearsed": True,
            "original_table_count": len(before),
            "original_rowcount_fingerprint": hashlib.sha256(
                json.dumps(before, sort_keys=True).encode()
            ).hexdigest(),
            "original_rowcounts_preserved": True,
            "migration_ledger": 33,
            "production_modified": False,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    parser.add_argument("--backup", required=True, help="Backup folder name only; no paths")
    parser.add_argument("--stage", required=True, help="Stage folder name only; no paths")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    report = {"mode": "isolated_restore_rehearsal",
              "production_modified": False, "provider_messages_sent": False}
    trial = Rehearsal()
    try:
        backup = backup_receipt(args.backup)
        source, versions, sha = stage_receipt(args.stage)
        disk_memory_preflight((backup / "equipe.dump").stat().st_size)
        require(args.run, "execucao_requer_run")
        report.update(trial.execute(backup, source, versions))
        report["candidate_sha"] = sha
    except Exception:
        report["restore_verified"] = False
        report["error"] = "validacao_interrompida_sem_alterar_producao"
    finally:
        try:
            problems = trial.cleanup()
        except Exception:
            problems = ["cleanup"]
        report["isolated_cleanup_verified"] = not problems
        if problems:
            report["owned_resource_names_for_manual_cleanup"] = [
                trial.name, trial.volume,
            ]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("restore_verified") or not report["isolated_cleanup_verified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
