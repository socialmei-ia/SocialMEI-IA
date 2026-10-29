#!/usr/bin/env python3
"""Import SHA-pinned CI-built Team v33 Docker images without changing containers.

The input is a GitHub Actions artifact ZIP containing the two images, a SHA256
manifest and the exact expected image identities. No server build is needed.
--inspect verifies bytes and present local identities. --apply may load missing
images; it never
changes Compose, running containers, gateways, databases or provider flags.
"""
import argparse
import gzip
import tarfile
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


def read_bundle(path):
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
        require(receipt.get("source_sha") == EXPECTED_SHA
                and set(receipt.get("images", {})) == set(SERVICES),
                "origem_das_imagens_divergente")
        for service in SERVICES:
            entry = receipt["images"][service]
            require(isinstance(entry, dict) and entry.get("tag") ==
                    f"socialmei-v33/{service}:{EXPECTED_SHA}"
                    and re.fullmatch("sha256:[0-9a-f]{64}",
                                     str(entry.get("image_id", ""))),
                    "imagem_de_recibo_invalida")
    return receipt


def verify_oci_identity(path, expected_id, local_id, tag):
    """Bind a local OCI descriptor to the receipt config and uncompressed layers.

    Docker's classic store reports a config digest as Id; containerd reports
    a manifest/index digest. The hashes differ but must describe identical bytes.
    No extraction, registry lookup or trust in revision labels is involved.
    """
    with tarfile.open(path, 'r:') as archive:
        members = {}
        hashes = {}
        total = 0
        for member in archive:
            name = member.name.removeprefix('./')
            if member.isdir():
                continue
            require(member.isfile() and name not in members
                    and len(members) < 10000 and member.size <= 4 * 1024**3,
                    'arquivo_de_imagem_invalido')
            total += member.size
            require(total <= 4 * 1024**3, 'arquivo_de_imagem_excede_limite')
            members[name] = member
            value = hashlib.sha256()
            with archive.extractfile(member) as stream:
                for chunk in iter(lambda: stream.read(1024**2), b''):
                    value.update(chunk)
            hashes[name] = 'sha256:' + value.hexdigest()

        def document(name):
            require(name in members and members[name].size <= 2 * 1024**2,
                    'metadados_da_imagem_invalidos')
            return json.load(archive.extractfile(members[name]))

        def descriptor(desc):
            require(isinstance(desc, dict) and re.fullmatch(
                'sha256:[0-9a-f]{64}', str(desc.get('digest', ''))),
                'descriptor_invalido')
            name = 'blobs/sha256/' + desc['digest'][7:]
            require(name in members and hashes[name] == desc['digest']
                    and members[name].size == desc.get('size'),
                    'descriptor_divergente')
            return name

        def image_manifest(identity, depth=0):
            require(depth <= 4 and re.fullmatch('sha256:[0-9a-f]{64}', identity),
                    'identidade_oci_invalida')
            name = 'blobs/sha256/' + identity[7:]
            require(name in members and hashes[name] == identity,
                    'manifesto_oci_ausente')
            value = document(name)
            require(isinstance(value, dict), 'manifesto_oci_invalido')
            if 'manifests' in value:
                children = [item for item in value['manifests']
                            if isinstance(item, dict) and item.get('platform', {}).get('os') == 'linux'
                            and item.get('platform', {}).get('architecture') == 'amd64']
                require(len(children) == 1, 'plataforma_oci_ambigua')
                descriptor(children[0])
                return image_manifest(children[0]['digest'], depth + 1)
            config_name = descriptor(value.get('config'))
            layers = value.get('layers')
            require(isinstance(layers, list), 'camadas_oci_invalidas')
            return config_name, [descriptor(item) for item in layers]

        config_name, layers = image_manifest(local_id)
        config_id = hashes[config_name]
        if expected_id != config_id:
            require(image_manifest(expected_id) == (config_name, layers),
                    'identidade_de_recibo_divergente')
        config = document(config_name)
        require(config.get('os') == 'linux' and config.get('architecture') == 'amd64',
                'plataforma_de_configuracao_invalida')
        rootfs = config.get('rootfs') or {}
        require(rootfs.get('type') == 'layers' and isinstance(rootfs.get('diff_ids'), list)
                and len(rootfs['diff_ids']) == len(layers), 'rootfs_divergente')
        manifests = document('manifest.json')
        rows = [row for row in manifests if isinstance(row, dict)
                and tag in (row.get('RepoTags') or [])]
        require(len(rows) == 1 and rows[0].get('Config') == config_name
                and rows[0].get('Layers') == layers, 'tag_de_arquivo_divergente')
        expanded_total = 0
        for name, diff_id in zip(layers, rootfs['diff_ids']):
            with archive.extractfile(members[name]) as stream:
                prefix = stream.read(2)
            with archive.extractfile(members[name]) as raw:
                stream = gzip.GzipFile(fileobj=raw) if prefix == b'\x1f\x8b' else raw
                value = hashlib.sha256()
                size = 0
                try:
                    for chunk in iter(lambda: stream.read(1024**2), b''):
                        size += len(chunk)
                        expanded_total += len(chunk)
                        require(size <= 4 * 1024**3 and expanded_total <= 4 * 1024**3,
                                'camada_expandida_excede_limite')
                        value.update(chunk)
                finally:
                    if stream is not raw:
                        stream.close()
                require('sha256:' + value.hexdigest() == diff_id,
                        'conteudo_de_camada_divergente')


def local_image_status(receipt):
    found = {}
    for service in SERVICES:
        details = receipt["images"][service]
        try:
            objects = json.loads(docker("image", "inspect", details["tag"]))
        except RuntimeError:
            found[service] = False
            continue
        require(len(objects) == 1 and (objects[0].get("Config") or {}).get("Labels", {}).get(
                    "org.opencontainers.image.revision") == EXPECTED_SHA,
                "tag_de_imagem_ja_existe_mas_diverge")
        row = objects[0]
        if row.get('Id') != details['image_id']:
            desc = row.get('Descriptor') or {}
            require(desc.get('digest') == row.get('Id') and desc.get('mediaType') in (
                'application/vnd.oci.image.manifest.v1+json',
                'application/vnd.oci.image.index.v1+json'), 'tag_de_imagem_ja_existe_mas_diverge')
            require(shutil.disk_usage('/').free >= 4 * 1024**3,
                    'disco_insuficiente_para_validar_identidade')
            with tempfile.TemporaryDirectory(prefix='team-v33-identity-', dir=BACKUPS) as folder:
                path = Path(folder) / 'image.tar'
                docker('image', 'save', '-o', str(path), details['tag'], timeout=360)
                verify_oci_identity(path, details['image_id'], row['Id'], details['tag'])
            # A concurrent retag cannot borrow a proof from an earlier image.
            current = json.loads(docker('image', 'inspect', details['tag']))
            require(len(current) == 1 and current[0].get('Id') == row['Id'],
                    'imagem_alterada_durante_validacao')
        found[service] = True
    return found


def execute(bundle, *, apply=False):
    valid_stage()
    receipt = read_bundle(bundle)
    before = local_image_status(receipt)
    report = {
        "mode": "image_archive_inspection" if not apply else "image_archive_import",
        "candidate_sha": EXPECTED_SHA,
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
    after = local_image_status(receipt)
    require(all(after.values()), "imagens_carregadas_mas_identidade_diverge")
    report["images_present_after"] = after
    report["action"] = "images_loaded_without_container_recreation"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["team"], required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = execute(args.bundle, apply=args.apply)
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
