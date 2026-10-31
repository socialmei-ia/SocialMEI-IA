#!/usr/bin/env python3
"""Import SHA-pinned CI-built Team v33 Docker images without changing containers.

The input is a GitHub Actions artifact ZIP containing the two images, a SHA256
manifest and the exact expected image identities. No server build is needed.
--inspect checks bytes only. --apply performs only docker image load; it never
changes Compose, running containers, gateways, databases or provider flags.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import shutil
import subprocess
import tempfile
import tarfile
import zipfile

EXPECTED_SHA = "c19d44b6ef6b8f125e6cafe60a7adfc0477cf454"
SOURCE = Path("/home/ubuntu/socialmei-backups/team-v33-c19d44b6ef6b/source")
BACKUPS = Path("/home/ubuntu/socialmei-backups")
NAMES = {"images.tar.gz", "image-receipt.json", "SHA256SUMS"}
SERVICES = ("team-api", "team-gateway")


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def command(argv, timeout=90):
    try:
        result = subprocess.run(argv, text=True, capture_output=True,
                                check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("comando_indisponivel") from None
    require(result.returncode == 0, "comando_falhou")
    return result.stdout


def docker(*args, timeout=90):
    require(Path("/var/run/docker.sock").is_socket(), "docker_local_indisponivel")
    return command(["docker", "--host=unix:///var/run/docker.sock", *args],
                   timeout=timeout)


def valid_stage(expected_sha=EXPECTED_SHA):
    require(re.fullmatch(r"[0-9a-f]{40}", str(expected_sha)) is not None,
            "source_sha_invalido")
    # Historical candidate keeps its previous, immutable staging location.
    # New CI candidates use the exact private stage path created by the
    # reviewed team-v33-stage.py script, without touching the live checkout.
    source = (SOURCE if expected_sha == EXPECTED_SHA
              else BACKUPS / ("team-v33-" + expected_sha[:12]) / "source")
    require(source.is_dir() and not source.is_symlink(), "stage_ausente")
    require(command(["git", "-C", str(source), "rev-parse", "HEAD"]).strip()
            == expected_sha, "source_sha_divergente")
    require(not command(
        ["git", "-C", str(source), "status", "--porcelain=v1", "--untracked-files=all"]
    ).strip(), "source_modificado")
    if expected_sha != EXPECTED_SHA:
        receipt_file = source.parent / "stage-receipt.json"
        require(receipt_file.is_file() and not receipt_file.is_symlink()
                and receipt_file.stat().st_size <= 65536,
                "recibo_do_stage_ausente")
        try:
            receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError, OSError):
            raise RuntimeError("recibo_do_stage_invalido") from None
        require(
            isinstance(receipt, dict)
            and receipt.get("candidate_sha") == expected_sha
            and receipt.get("stage_source") == str(source)
            and receipt.get("stage_clean") is True
            and receipt.get("checkout_original_preservado") is True
            and receipt.get("deployment_executed") is False
            and receipt.get("docker_commands_executed") is False
            and receipt.get("provider_messages_sent") is False
            and isinstance(receipt.get("migration_plan"), dict)
            and receipt["migration_plan"].get("source_reviewed") is True
            and receipt["migration_plan"].get("migration_apply_executed") is False
            and receipt.get("candidate_branch") in {
                "feat/whatsapp-bot-readonly-preview-20261030",
                "feat/team-release-candidate-stage-20261030",
            },
            "recibo_do_stage_invalido",
        )


def read_bundle(path, expected_sha=EXPECTED_SHA):
    require(re.fullmatch(r"[0-9a-f]{40}", str(expected_sha)) is not None,
            "source_sha_invalido")
    require(not path.is_symlink(), "pacote_simbolico_proibido")
    path = path.resolve(strict=True)
    require(path.is_file() and
            (path == Path("/home/ubuntu/socialmei-v33-images.zip") or
             path.parent == BACKUPS), "arquivo_de_imagens_fora_da_pasta_autorizada")
    require(1_000 <= path.stat().st_size <= 1024**3,
            "tamanho_de_pacote_invalido")
    with tempfile.TemporaryDirectory(prefix="team-v33-verify-") as temp_dir:
        image_archive = Path(temp_dir) / "images.tar.gz"
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            require({entry.filename for entry in entries} == NAMES
                    and len(entries) == 3, "pacote_com_entradas_inesperadas")
            require(all(not entry.is_dir() and
                        stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFLNK
                        and 0 < entry.file_size <= 1024**3
                        for entry in entries), "pacote_com_arquivos_invalidos")
            hashes = {}
            for entry in entries:
                hash_value = hashlib.sha256()
                with archive.open(entry) as stream:
                    if entry.filename == "images.tar.gz":
                        with image_archive.open("xb") as image_file:
                            for chunk in iter(lambda: stream.read(1024**2), b""):
                                hash_value.update(chunk)
                                image_file.write(chunk)
                    else:
                        for chunk in iter(lambda: stream.read(1024**2), b""):
                            hash_value.update(chunk)
                hashes[entry.filename] = hash_value.hexdigest()
            checksum_text = archive.read("SHA256SUMS").decode("utf-8")
            match = [
                re.fullmatch(r"([0-9a-f]{64})\s+([a-zA-Z0-9._-]+)", line)
                for line in checksum_text.strip().splitlines()
            ]
            require(len(match) == 2 and all(m for m in match),
                    "manifesto_sha256_invalido")
            expected = {m[2]: m[1] for m in match}
            require(set(expected) == NAMES - {"SHA256SUMS"}
                    and all(hashes[name] == checksum for name, checksum in expected.items()),
                    "sha256_do_pacote_divergente")
            receipt = json.loads(archive.read("image-receipt.json"))
            require(receipt.get("source_sha") == expected_sha
                    and set(receipt.get("images", {})) == set(SERVICES),
                    "origem_das_imagens_divergente")
            for service in SERVICES:
                entry = receipt["images"][service]
                require(isinstance(entry, dict) and entry.get("tag") ==
                        f"socialmei-v33/{service}:{expected_sha}"
                        and re.fullmatch("sha256:[0-9a-f]{64}",
                                         str(entry.get("image_id", ""))),
                        "imagem_de_recibo_invalida")
            verify_archive_config_digests(image_archive, receipt["images"], expected_sha,
                                          "bundle")
            return receipt


def verify_archive_config_digests(image_archive, expected_images, expected_sha, context):
    """Verify tag -> manifest row -> exact SHA-256 config bytes and source label."""
    expected = {entry["tag"]: entry for entry in expected_images.values()}
    with tarfile.open(image_archive, "r:*") as archive:
        members = archive.getmembers()
        require(0 < len(members) <= 10000
                and all(not member.issym() and not member.islnk()
                        and "\\" not in member.name
                        and not PurePosixPath(member.name).is_absolute()
                        and ".." not in PurePosixPath(member.name).parts
                        and (member.isfile() or member.isdir())
                        for member in members),
                "arquivo_de_imagem_invalido")
        by_name = {member.name: member for member in members}
        require(len(by_name) == len(members), "arquivo_de_imagem_duplicado")
        manifests = [member for member in members
                     if member.name == "manifest.json" and member.isfile()]
        require(len(manifests) == 1 and manifests[0].size <= 8 * 1024**2,
                "manifesto_de_imagem_invalido")
        manifest_stream = archive.extractfile(manifests[0])
        rows = json.load(manifest_stream)
        require(isinstance(rows, list) and len(rows) == len(expected),
                "manifesto_de_imagem_divergente")
        seen = set()
        for row in rows:
            require(isinstance(row, dict) and isinstance(row.get("RepoTags"), list)
                    and len(row["RepoTags"]) == 1,
                    "tag_de_manifesto_invalida")
            tag = row["RepoTags"][0]
            require(tag in expected and tag not in seen
                    and isinstance(row.get("Config"), str),
                    "tag_de_manifesto_divergente")
            seen.add(tag)
            config_name = row["Config"]
            config_member = by_name.get(config_name)
            require(config_member is not None and config_member.isfile()
                    and config_member.size <= 32 * 1024**2,
                    "config_de_manifesto_invalido")
            config_stream = archive.extractfile(config_member)
            config_bytes = config_stream.read(32 * 1024**2 + 1)
            digest_error = ("tag_de_imagem_config_digest_diverge"
                            if context == "tag" else "bundle_config_digest_diverge")
            origin_error = ("tag_de_imagem_config_origem_diverge"
                            if context == "tag" else "bundle_config_origem_diverge")
            require(len(config_bytes) == config_member.size
                    and hashlib.sha256(config_bytes).hexdigest()
                    == expected[tag]["image_id"].removeprefix("sha256:"),
                    digest_error)
            config = json.loads(config_bytes)
            labels = (config.get("config") or {}).get("Labels") or {}
            require(labels.get("org.opencontainers.image.revision") == expected_sha,
                    origin_error)
        require(seen == set(expected), "tags_de_imagem_incompletas")


def local_image_status(receipt, expected_sha=EXPECTED_SHA):
    require(re.fullmatch(r"[0-9a-f]{40}", str(expected_sha)) is not None,
            "source_sha_invalido")
    found = {}
    for service in SERVICES:
        details = receipt["images"][service]
        try:
            objects = json.loads(docker("image", "inspect", details["tag"]))
        except RuntimeError:
            found[service] = False
            continue
        require(len(objects) == 1
                and details["tag"] in (objects[0].get("RepoTags") or [])
                and (objects[0].get("Config") or {}).get("Labels", {}).get(
                    "org.opencontainers.image.revision") == expected_sha,
                "tag_de_imagem_ja_existe_mas_diverge")
        fd, archive_path = tempfile.mkstemp(prefix="team-image-verify-", suffix=".tar")
        os.close(fd)
        try:
            docker("image", "save", "-o", archive_path, details["tag"], timeout=360)
            verify_archive_config_digests(
                Path(archive_path), {service: details}, expected_sha, "tag"
            )
        finally:
            Path(archive_path).unlink(missing_ok=True)
        found[service] = True
    return found


def execute(bundle, *, apply=False, expected_sha=EXPECTED_SHA):
    require(re.fullmatch(r"[0-9a-f]{40}", str(expected_sha)) is not None,
            "source_sha_invalido")
    valid_stage(expected_sha=expected_sha)
    receipt = read_bundle(bundle, expected_sha=expected_sha)
    before = local_image_status(receipt, expected_sha=expected_sha)
    report = {
        "mode": "image_archive_inspection" if not apply else "image_archive_import",
        "candidate_sha": expected_sha,
        "bundle_sha256_verified": True,
        "image_identity_verified": True,
        "images_present_before": before,
        "production_container_changed": False,
        "database_changed": False,
        "provider_messages_sent": False,
    }
    if not apply:
        report["action"] = "inspection_passed"
        return report
    if all(before.values()):
        report["action"] = "images_already_verified"
        report["images_present_after"] = before
        return report
    free = shutil.disk_usage("/").free
    require(free >= 4 * 1024**3, "disco_insuficiente")
    available_kib = next(
        (int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
         if line.startswith("MemAvailable:")), 0,
    )
    require(available_kib >= 384 * 1024, "memoria_insuficiente_para_importacao")
    with tempfile.TemporaryDirectory(prefix="team-v33-image-load-", dir=BACKUPS) as dir_name:
        staging = Path(dir_name)
        staging.chmod(0o700)
        image_file = staging / "images.tar.gz"
        with zipfile.ZipFile(bundle) as archive:
            with archive.open("images.tar.gz") as source, image_file.open("xb") as dest:
                shutil.copyfileobj(source, dest, 1024**2)
        image_file.chmod(0o600)
        docker("load", "-i", str(image_file), timeout=360)
    after = local_image_status(receipt, expected_sha=expected_sha)
    require(all(after.values()), "imagens_carregadas_mas_identidade_diverge")
    report["images_present_after"] = after
    report["action"] = "images_loaded_without_container_recreation"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--source-sha", default=EXPECTED_SHA,
                        help="Require this exact 40-character source commit from the receipt")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = execute(args.bundle, apply=args.apply,
                         expected_sha=args.source_sha)
    except Exception:
        print(json.dumps({
            "status": "stopped", "error": "falha_de_verificacao_ou_importacao",
            "production_container_changed": False,
            "database_changed": False,
            "next_action": "conferir_pacote_e_imagens_sem_recriar_containers",
        }))
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
