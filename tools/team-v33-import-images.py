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
import re
import stat
import shutil
import subprocess
import tempfile
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


def valid_stage():
    require(SOURCE.is_dir() and not SOURCE.is_symlink(), "stage_ausente")
    require(command(["git", "-C", str(SOURCE), "rev-parse", "HEAD"]).strip()
            == EXPECTED_SHA, "source_sha_divergente")
    require(not command(
        ["git", "-C", str(SOURCE), "status", "--porcelain=v1", "--untracked-files=all"]
    ).strip(), "source_modificado")


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
    return receipt


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
        require(len(objects) == 1 and objects[0].get("Id") == details["image_id"]
                and (objects[0].get("Config") or {}).get("Labels", {}).get(
                    "org.opencontainers.image.revision") == expected_sha,
                "tag_de_imagem_ja_existe_mas_diverge")
        found[service] = True
    return found


def execute(bundle, *, apply=False, expected_sha=EXPECTED_SHA):
    require(re.fullmatch(r"[0-9a-f]{40}", str(expected_sha)) is not None,
            "source_sha_invalido")
    valid_stage()
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
