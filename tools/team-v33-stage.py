#!/usr/bin/env python3
"""Stage the reviewed SocialMEI Team 033 source in an isolated Git worktree.

Never touches the dirty live checkout or applies migrations. No Docker rebuild,
provider calls, activation, deploy, reset, stash, cleanup, or secret output.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path("/home/ubuntu/socialmei-team")
BACKUPS = Path("/home/ubuntu/socialmei-backups")
RELEASE_REF = "refs/heads/release/socialmei-functional-integrations-20261026"
TRACKED_REF = "refs/remotes/origin/release/socialmei-functional-integrations-20261026"
DB_CONTAINER = "socialmei-team-team-postgres-1"
MIGRATION_032 = "032_whatsapp_bot_conversations.sql"
MIGRATION_033 = "033_provider_sentiment_jobs.sql"
REVIEWED_MIGRATIONS = (
    "001_initial_socialmei_schema.sql",
    "002_shared_crm_foundation.sql",
    "003_client_contract.sql",
    "004_client_import.sql",
    "005_shared_catalog.sql",
    "006_shared_sales.sql",
    "007_shared_finance.sql",
    "008_workspace_transfer.sql",
    "009_shared_channel_foundation.sql",
    "010_account_authentication.sql",
    "011_crm_workspace_links.sql",
    "012_instagram_simulation.sql",
    "013_workspace_profile_sync.sql",
    "014_message_enrichment.sql",
    "015_content_preparation.sql",
    "016_opportunity_lifecycle.sql",
    "017_integration_setup.sql",
    "018_instagram_provider_lab.sql",
    "019_instagram_persistent_oauth.sql",
    "020_instagram_durable_webhook.sql",
    "021_instagram_direct_outbox.sql",
    "022_opportunity_planning.sql",
    "023_waha_durable_ingress.sql",
    "024_account_recovery.sql",
    "025_session_management.sql",
    "026_recovery_delivery_queue.sql",
    "027_instagram_image_publications.sql",
    "028_instagram_temporary_media.sql",
    "029_workspace_pdf_knowledge.sql",
    "030_whatsapp_catalog_access.sql",
    "031_report_viewer_role.sql",
    "032_whatsapp_bot_conversations.sql",
    "033_provider_sentiment_jobs.sql",
)
READ_ONLY_SQL = (
    "BEGIN READ ONLY; "
    "SELECT COALESCE(json_agg(version ORDER BY version), '[]'::json) "
    "FROM socialmei.schema_migrations; ROLLBACK;"
)


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def invoke(argv, *, stdin=None, timeout=30, binary=False):
    """Return the output privately; never expose subprocess stdout/stderr in errors."""
    try:
        result = subprocess.run(
            argv, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=not binary, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("comando_indisponivel") from None
    require(result.returncode == 0, "comando_falhou")
    return result.stdout


def git(root, *args, **kw):
    return invoke(["git", "-C", str(root), *args], **kw)


def candidate(sha):
    require(isinstance(sha, str) and re.fullmatch("[0-9a-f]{40}", sha), "sha_invalido")
    return sha


def dirty_summary(raw):
    """Status only; never emit paths other than an allowlisted local Caddy hotfix."""
    require(isinstance(raw, bytes), "git_status_invalido")
    chunks = raw.split(b"\x00")
    entries = []
    index = 0
    while index < len(chunks) and chunks[index]:
        current = chunks[index]
        require(len(current) >= 4 and current[2:3] == b" ", "git_status_invalido")
        status = current[:2]
        name = current[3:]
        index += 1
        # Porcelain -z emits an additional pathname for a rename or copy.
        if b"R" in status or b"C" in status:
            require(index < len(chunks) and bool(chunks[index]), "git_status_invalido")
            index += 1
        entries.append((status, name))
    caddy = (
        len(entries) == 1
        and entries[0][0] in (b" M", b"M ", b"MM")
        and entries[0][1] == b"deploy/team/Caddyfile"
    )
    return {
        "tracked_changes": sum(status != b"??" for status, _ in entries),
        "untracked_files": sum(status == b"??" for status, _ in entries),
        "only_caddy_hotfix": caddy,
        "file_paths_redacted": True,
    }


def reviewed_source(names):
    require(isinstance(names, list), "origem_invalida")
    require(len(names) == 33, "origem_migrations_nao_revisada")
    require(names == list(REVIEWED_MIGRATIONS), "origem_migrations_nao_revisada")
    for i, name in enumerate(names, 1):
        require(re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", name), "origem_migrations_nao_revisada")
        require(name[:3] == f"{i:03}", "origem_migrations_nao_revisada")
    require(names[-2:] == [MIGRATION_032, MIGRATION_033], "origem_migrations_nao_revisada")
    return names


def plan(versions, names):
    require(isinstance(versions, list) and all(isinstance(v, str) for v in versions), "ledger_invalido")
    require(versions == names[:len(versions)], "ledger_fora_da_ordem")
    require(31 <= len(versions) <= 33, "ledger_base_incompativel")
    return {
        "installed": len(versions),
        "pending": names[len(versions):],
        "source_reviewed": True,
        "migration_apply_executed": False,
        "backup_created": False,
        "restore_verified": False,
    }


def private_root(path):
    require(path.is_absolute() and not path.is_symlink(), "pasta_privada_invalida")
    if not path.exists():
        path.mkdir(mode=0o700, parents=False)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(), "pasta_privada_invalida")
    require(stat.S_IMODE(info.st_mode) == 0o700, "pasta_privada_invalida")
    return path


def source_migrations(root, sha):
    paths = git(root, "ls-tree", "-r", "--name-only", sha, "database/migrations/")
    names = [p.removeprefix("database/migrations/") for p in paths.splitlines() if p.endswith(".sql")]
    return reviewed_source(names)


def read_ledger():
    output = invoke([
        "docker", "exec", "-i", DB_CONTAINER, "sh", "-c",
        'exec psql -X -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At'
    ], stdin=READ_ONLY_SQL, timeout=25)
    lines = [line.strip() for line in output.splitlines() if line.strip().startswith("[")]
    require(len(lines) == 1, "ledger_indisponivel")
    try:
        return json.loads(lines[0])
    except (ValueError, TypeError):
        raise RuntimeError("ledger_indisponivel") from None


def trusted_remote(root):
    origin = git(root, "remote", "get-url", "origin").strip()
    return bool(re.fullmatch(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"socialmei-ia/SocialMEI-IA(?:\.git)?", origin
    ))


def ensure_git_object(root, sha):
    require(trusted_remote(root), "remote_nao_confiavel")
    # Refresh the remote tracking ref for ancestry verification. Only Git
    # metadata changes; the live checkout and its hotfixes remain untouched.
    git(root, "fetch", "--no-tags", "origin",
        "+" + RELEASE_REF + ":" + TRACKED_REF, timeout=90)
    require(git(root, "cat-file", "-t", sha).strip() == "commit", "sha_nao_disponivel")
    # The pinned object must belong to the intended upstream release lineage.
    git(root, "merge-base", "--is-ancestor", sha, TRACKED_REF)
    require(git(root, "rev-parse", sha + "^{commit}").strip() == sha, "sha_nao_disponivel")


def git_audit(root):
    head = git(root, "rev-parse", "HEAD").strip()
    require(re.fullmatch(r"[0-9a-f]{40}", head), "checkout_invalido")
    raw = git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", binary=True)
    return {
        "head": head,
        "dirty": dirty_summary(raw),
        "status_digest": hashlib.sha256(raw).hexdigest(),
    }


def stage(root, backup, sha, *, name=None):
    candidate(sha)
    require(root == ROOT, "checkout_nao_autorizado")
    require(root.exists() and root.is_dir() and not root.is_symlink(), "checkout_invalido")
    private_root(backup)
    before = git_audit(root)
    ensure_git_object(root, sha)
    names = source_migrations(root, sha)
    schema = plan(read_ledger(), names)
    name = name or "team-v33-" + sha[:12]
    require(re.fullmatch(r"team-v33-[a-z0-9-]{8,42}", name), "nome_da_pasta_invalido")
    folder = backup / name
    require(not folder.exists() and not folder.is_symlink(), "pasta_de_stage_ja_existe")
    folder.mkdir(mode=0o700)
    source = folder / "source"
    # Does not modify the user's tracked or untracked files in ROOT.
    git(root, "worktree", "add", "--detach", "--lock", str(source), sha, timeout=90)
    require(git(source, "rev-parse", "HEAD").strip() == sha, "worktree_incompativel")
    require(not git(source, "status", "--porcelain=v1", "--untracked-files=all").strip(), "worktree_nao_limpo")
    for private in (".env.team", ".env", "deploy/team/private/waha-registry.json"):
        require(not (source / private).exists(), "dados_privados_detectados_no_stage")
    after = git_audit(root)
    require(after == before, "checkout_local_modificado_inesperadamente")
    hashes = {
        name: hashlib.sha256(
            git(root, "show", f"{sha}:database/migrations/{name}", binary=True)
        ).hexdigest() for name in names[-2:]
    }
    report = {
        "candidate_sha": sha,
        "checkout_original_sha": before["head"],
        "checkout_original_preservado": True,
        "checkout_original_dirty": before["dirty"],
        "stage_source": str(source),
        "stage_clean": True,
        "migration_plan": schema,
        "new_migration_sha256": hashes,
        "deployment_executed": False,
        "docker_commands_executed": False,
        "provider_messages_sent": False,
        "next_stage": "backup_restauravel_e_preparacao_privada_da_release",
    }
    receipt = folder / "stage-receipt.json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(receipt, flags, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return report


def inspect(root=ROOT):
    require(root == ROOT and root.is_dir() and not root.is_symlink(), "checkout_invalido")
    before = git_audit(root)
    report = {
        "mode": "somente_leitura", "checkout_original_sha": before["head"],
        "checkout_dirty": before["dirty"], "deployment_executed": False,
        "staging_executed": False, "original_status_preserved": True,
        "migrations": {"read_only": True, "installed": None, "last_prefix": None},
    }
    versions = read_ledger()
    require(isinstance(versions, list) and all(
        isinstance(x, str) and re.fullmatch(r"[0-9]{3}_[a-z0-9_]+\.sql", x)
        for x in versions), "ledger_indisponivel")
    report["migrations"]["installed"] = len(versions)
    report["migrations"]["last_prefix"] = int(versions[-1][:3]) if versions else None
    require(git_audit(root) == before, "checkout_local_modificado_inesperadamente")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=["team"])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--stage", action="store_true")
    parser.add_argument("--candidate-sha")
    args = parser.parse_args()
    if args.stage:
        if not args.candidate_sha:
            parser.error("--candidate-sha obrigatório para --stage")
        report = stage(ROOT, BACKUPS, args.candidate_sha)
    else:
        require(not args.candidate_sha, "--candidate-sha apenas em --stage")
        report = inspect()
    # Only controlled, sanitized report fields. No raw git status or docker output.
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Etapa interrompida de forma segura. Nenhum container/banco/servico foi alterado.") from None
