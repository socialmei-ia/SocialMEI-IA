"""Strict OCI identity verification for the offline SocialMEI image handoff."""
import base64
import binascii
import hashlib
import json
import re


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def verify_oci_archive_identity(archive, by_name, rows, expected, expected_sha):
    """Bind Docker tags to OCI manifests/indices, configs, layers and attestations."""
    layout_member = by_name.get("oci-layout")
    index_member = by_name.get("index.json")
    require(layout_member is not None and index_member is not None
            and layout_member.isfile() and index_member.isfile(),
            "oci_layout_incompleto")

    def read_json_member(name, limit):
        member = by_name.get(name)
        require(member is not None and member.isfile() and 0 < member.size <= limit,
                "oci_blob_ausente_ou_invalido")
        with archive.extractfile(member) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) == member.size, "oci_blob_incompleto")
        try:
            return json.loads(raw), raw
        except (ValueError, UnicodeError, TypeError):
            raise RuntimeError("oci_json_invalido") from None

    def verify_descriptor(descriptor, media_type, *, json_limit=8 * 1024**2):
        require(isinstance(descriptor, dict)
                and descriptor.get("mediaType") == media_type
                and re.fullmatch(r"sha256:[0-9a-f]{64}",
                                 str(descriptor.get("digest", ""))) is not None
                and type(descriptor.get("size")) is int
                and 0 < descriptor["size"] <= max(json_limit, 1024**3),
                "oci_descritor_invalido")
        blob_name = "blobs/sha256/" + descriptor["digest"][7:]
        member = by_name.get(blob_name)
        require(member is not None and member.isfile()
                and member.size == descriptor["size"],
                "oci_blob_ausente_ou_invalido")
        digest = hashlib.sha256()
        raw = bytearray() if json_limit else None
        with archive.extractfile(member) as stream:
            for chunk in iter(lambda: stream.read(1024**2), b""):
                digest.update(chunk)
                if raw is not None:
                    require(len(raw) + len(chunk) <= json_limit,
                            "oci_blob_grande_demais")
                    raw.extend(chunk)
        require("sha256:" + digest.hexdigest() == descriptor["digest"],
                "oci_blob_digest_diverge")
        if "data" in descriptor:
            try:
                embedded = base64.b64decode(descriptor["data"], validate=True)
            except (ValueError, TypeError, binascii.Error):
                raise RuntimeError("oci_dado_embutido_invalido") from None
            require(len(embedded) == descriptor["size"]
                    and "sha256:" + hashlib.sha256(embedded).hexdigest()
                        == descriptor["digest"], "oci_dado_embutido_diverge")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError, TypeError):
            raise RuntimeError("oci_json_invalido") from None

    layout, _ = read_json_member("oci-layout", 1024)
    require(isinstance(layout, dict) and
            layout.get("imageLayoutVersion") == "1.0.0", "oci_layout_invalido")
    root, _ = read_json_member("index.json", 8 * 1024**2)
    require(isinstance(root, dict) and root.get("schemaVersion") == 2
            and root.get("mediaType") == "application/vnd.oci.image.index.v1+json"
            and isinstance(root.get("manifests"), list)
            and len(root["manifests"]) == len(expected), "oci_indice_invalido")

    require(isinstance(rows, list) and len(rows) == len(expected)
            and all(isinstance(row, dict)
                    and isinstance(row.get("RepoTags"), list)
                    and len(row["RepoTags"]) == 1
                    and isinstance(row["RepoTags"][0], str)
                    and isinstance(row.get("Config"), str)
                    and isinstance(row.get("Layers"), list)
                    for row in rows), "oci_manifesto_docker_invalido")
    rows_by_tag = {row["RepoTags"][0]: row for row in rows}
    require(len(rows_by_tag) == len(rows) and set(rows_by_tag) == set(expected),
            "oci_tags_divergentes")
    seen = set()
    for reference in root["manifests"]:
        require(isinstance(reference, dict)
                and isinstance(reference.get("annotations"), dict),
                "oci_referencia_invalida")
        name = reference["annotations"].get("io.containerd.image.name")
        tag = name.removeprefix("docker.io/") if isinstance(name, str) else None
        require(tag in expected and tag not in seen
                and name == "docker.io/" + tag
                and reference["annotations"].get("org.opencontainers.image.ref.name")
                    == expected_sha
                and reference.get("digest") == expected[tag]["image_id"],
                "oci_tag_ou_identidade_divergente")
        seen.add(tag)
        direct = reference.get("mediaType") == "application/vnd.oci.image.manifest.v1+json"
        if direct:
            # A single-platform export need not contain an intermediate image index.
            children = [reference]
        else:
            image_index = verify_descriptor(
                reference, "application/vnd.oci.image.index.v1+json")
            require(isinstance(image_index, dict)
                    and image_index.get("schemaVersion") == 2
                    and image_index.get("mediaType") ==
                        "application/vnd.oci.image.index.v1+json"
                    and isinstance(image_index.get("manifests"), list)
                    and 1 <= len(image_index["manifests"]) <= 8,
                    "oci_indice_de_imagem_invalido")
            children = image_index["manifests"]
        executable = []
        attestations = []
        for child in children:
            require(isinstance(child, dict)
                    and (direct or isinstance(child.get("platform"), dict)),
                    "oci_plataforma_invalida")
            manifest = verify_descriptor(
                child, "application/vnd.oci.image.manifest.v1+json")
            require(isinstance(manifest, dict)
                    and manifest.get("schemaVersion") == 2
                    and manifest.get("mediaType") ==
                        "application/vnd.oci.image.manifest.v1+json"
                    and isinstance(manifest.get("layers"), list)
                    and isinstance(manifest.get("config"), dict),
                    "oci_manifesto_invalido")
            config_type = manifest["config"].get("mediaType")
            require(config_type in {"application/vnd.oci.image.config.v1+json",
                                    "application/vnd.oci.empty.v1+json"},
                    "oci_config_tipo_invalido")
            config = verify_descriptor(manifest["config"], config_type)
            require(isinstance(config, dict), "oci_config_invalida")
            platform = child.get("platform", config if direct else {})
            runnable = platform.get("os") == "linux" and platform.get("architecture") == "amd64"
            for layer in manifest["layers"]:
                layer_types = {
                    "application/vnd.oci.image.layer.v1.tar+gzip",
                    "application/vnd.oci.image.layer.v1.tar",
                    "application/vnd.oci.image.layer.v1.tar+zstd",
                } if runnable else {"application/vnd.in-toto+json"}
                require(isinstance(layer, dict) and layer.get("mediaType") in layer_types,
                        "oci_layer_tipo_invalido")
                verify_descriptor(layer, layer["mediaType"], json_limit=0)
            if runnable:
                require(config_type == "application/vnd.oci.image.config.v1+json"
                        and config.get("os") == "linux"
                        and config.get("architecture") == "amd64"
                        and not manifest.get("artifactType")
                        and not manifest.get("subject"), "oci_config_plataforma_invalida")
                require(not child.get("annotations", {}).get(
                    "vnd.docker.reference.type"), "oci_execucao_marcada_como_atestacao")
                executable.append((child, manifest, config))
            elif platform.get("os") == "unknown" and platform.get("architecture") == "unknown":
                require(not direct and isinstance(child.get("annotations"), dict)
                        and child["annotations"].get("vnd.docker.reference.type")
                            == "attestation-manifest", "oci_atestacao_invalida")
                if config_type == "application/vnd.oci.empty.v1+json":
                    # OCI 1.1 empty descriptors are metadata, never runnable configs.
                    require(config == {} and manifest["config"].get("size") == 2
                            and manifest.get("artifactType") ==
                                "application/vnd.docker.attestation.manifest.v1+json"
                            and isinstance(manifest.get("subject"), dict),
                            "oci_atestacao_vazia_invalida")
                attestations.append((child, manifest))
            else:
                raise RuntimeError("oci_plataforma_nao_revisada")
        require(len(executable) == 1, "oci_imagem_executavel_ambigua")
        runnable, manifest, config = executable[0]
        for attestation, att_manifest in attestations:
            require(attestation["annotations"].get("vnd.docker.reference.digest")
                    == runnable["digest"], "oci_atestacao_origem_divergente")
            subject = att_manifest.get("subject")
            if subject is not None:
                require(isinstance(subject, dict)
                        and all(subject.get(key) == runnable.get(key)
                                for key in ("mediaType", "digest", "size")),
                        "oci_atestacao_subject_divergente")
        row = rows_by_tag[tag]
        config_digest = manifest["config"]["digest"]
        require(row.get("Config") == "blobs/sha256/" + config_digest[7:]
                and ["blobs/sha256/" + layer["digest"][7:]
                     for layer in manifest["layers"]] == row.get("Layers"),
                "oci_manifesto_docker_divergente")
        labels = (config.get("config") or {}).get("Labels") or {}
        require(labels.get("org.opencontainers.image.revision") == expected_sha,
                "oci_config_origem_diverge")
    require(seen == set(expected), "oci_imagens_incompletas")
