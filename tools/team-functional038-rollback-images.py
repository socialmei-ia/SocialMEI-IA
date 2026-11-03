"""Strict rollback-only image identity, including Docker29 direct OCI manifests.

Classic Docker archives and OCI image-index archives keep the established
verifier. This helper does not load, rewrite or retag an image archive.
"""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

INDEX = 'application/vnd.oci.image.index.v1+json'
MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
CONFIG = 'application/vnd.oci.image.config.v1+json'
LAYERS = {
    'application/vnd.oci.image.layer.v1.tar',
    'application/vnd.oci.image.layer.v1.tar+gzip',
    'application/vnd.oci.image.layer.v1.tar+zstd',
}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def parse_json(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'rollback_json_duplicate_key')
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (UnicodeError, ValueError, TypeError):
        raise RuntimeError('rollback_json_invalid') from None


def established_verifier(image_archive, expected_images, expected_sha, context):
    filename = Path(__file__).with_name('team-v33-import-images.py')
    require(filename.is_file() and not filename.is_symlink(), 'rollback_established_verifier_missing')
    spec = importlib.util.spec_from_file_location('functional038_established_image_verifier', filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_archive_config_digests(image_archive, expected_images, expected_sha, context)


def verify_archive_config_digests(image_archive, expected_images, expected_sha, context):
    require(re.fullmatch(r'[a-f0-9]{40}', str(expected_sha)) is not None,
            'rollback_source_sha_invalid')
    require(isinstance(expected_images, dict) and 1 <= len(expected_images) <= 2
            and all(isinstance(image, dict) and isinstance(image.get('tag'), str)
                    and re.fullmatch(r'sha256:[a-f0-9]{64}', str(image.get('image_id'))) is not None
                    for image in expected_images.values()), 'rollback_expected_images_invalid')
    expected = {image['tag']: image for image in expected_images.values()}
    require(len(expected) == len(expected_images), 'rollback_duplicate_expected_tag')
    with tarfile.open(image_archive, 'r:*') as archive:
        members = archive.getmembers()
        require(0 < len(members) <= 10000
                and all((member.isfile() or member.isdir())
                        and not member.issym() and not member.islnk()
                        and '\\' not in member.name and '\x00' not in member.name
                        and not PurePosixPath(member.name).is_absolute()
                        and '..' not in PurePosixPath(member.name).parts
                        and 0 <= member.size <= 1024**3 for member in members),
                'rollback_archive_member_invalid')
        by_name = {member.name: member for member in members}
        require(len(by_name) == len(members), 'rollback_archive_duplicate_member')

        def raw_member(name, limit):
            member = by_name.get(name)
            require(member is not None and member.isfile() and 0 < member.size <= limit,
                    'rollback_blob_missing_or_invalid')
            with archive.extractfile(member) as stream:
                raw = stream.read(limit + 1)
            require(len(raw) == member.size, 'rollback_blob_incomplete')
            return raw

        if 'index.json' not in by_name and 'oci-layout' not in by_name:
            return established_verifier(image_archive, expected_images, expected_sha, context)
        layout = parse_json(raw_member('oci-layout', 1024))
        require(isinstance(layout, dict) and layout.get('imageLayoutVersion') == '1.0.0',
                'rollback_oci_layout_invalid')
        root = parse_json(raw_member('index.json', 8 * 1024**2))
        require(isinstance(root, dict) and root.get('schemaVersion') == 2
                and root.get('mediaType') == INDEX and isinstance(root.get('manifests'), list)
                and len(root['manifests']) == len(expected), 'rollback_oci_root_invalid')
        references = root['manifests']
        require(all(isinstance(reference, dict) for reference in references),
                'rollback_oci_reference_invalid')
        types = {reference.get('mediaType') for reference in references}
        if types == {INDEX}:
            return established_verifier(image_archive, expected_images, expected_sha, context)
        require(types == {MANIFEST}, 'rollback_oci_reference_type_unreviewed')
        rows = parse_json(raw_member('manifest.json', 8 * 1024**2))
        require(isinstance(rows, list) and len(rows) == len(expected)
                and all(isinstance(row, dict) and isinstance(row.get('RepoTags'), list)
                        and len(row['RepoTags']) == 1 and isinstance(row['RepoTags'][0], str)
                        and isinstance(row.get('Config'), str) and isinstance(row.get('Layers'), list)
                        and all(isinstance(layer, str) for layer in row['Layers']) for row in rows),
                'rollback_docker_manifest_invalid')
        by_tag = {row['RepoTags'][0]: row for row in rows}
        require(len(by_tag) == len(rows) and set(by_tag) == set(expected), 'rollback_docker_tags_diverge')

        def descriptor_blob(descriptor, media_type, json_limit=8 * 1024**2):
            require(isinstance(descriptor, dict) and descriptor.get('mediaType') == media_type
                    and re.fullmatch(r'sha256:[a-f0-9]{64}', str(descriptor.get('digest'))) is not None
                    and type(descriptor.get('size')) is int and 0 < descriptor['size'] <= 1024**3,
                    'rollback_oci_descriptor_invalid')
            filename = 'blobs/sha256/' + descriptor['digest'][7:]
            member = by_name.get(filename)
            require(member is not None and member.isfile() and member.size == descriptor['size'],
                    'rollback_oci_blob_size_or_presence_diverge')
            digest = hashlib.sha256()
            raw = bytearray() if json_limit else None
            count = 0
            with archive.extractfile(member) as stream:
                for chunk in iter(lambda: stream.read(1024**2), b''):
                    count += len(chunk)
                    digest.update(chunk)
                    if raw is not None:
                        require(len(raw) + len(chunk) <= json_limit, 'rollback_oci_json_too_large')
                        raw.extend(chunk)
            require(count == member.size and 'sha256:' + digest.hexdigest() == descriptor['digest'],
                    'rollback_oci_blob_digest_diverge')
            return parse_json(bytes(raw)) if raw is not None else None

        seen = set()
        for reference in references:
            annotations = reference.get('annotations')
            require(isinstance(annotations, dict), 'rollback_oci_reference_annotations_invalid')
            name = annotations.get('io.containerd.image.name')
            tag = name.removeprefix('docker.io/') if isinstance(name, str) else None
            require(tag in expected and tag not in seen and name == 'docker.io/' + tag
                    and annotations.get('org.opencontainers.image.ref.name') == expected_sha
                    and reference.get('digest') == expected[tag]['image_id'],
                    'rollback_oci_tag_or_full_manifest_identity_diverge')
            seen.add(tag)
            manifest = descriptor_blob(reference, MANIFEST)
            require(isinstance(manifest, dict) and manifest.get('schemaVersion') == 2
                    and manifest.get('mediaType') == MANIFEST and isinstance(manifest.get('config'), dict)
                    and isinstance(manifest.get('layers'), list), 'rollback_oci_manifest_invalid')
            config = descriptor_blob(manifest['config'], CONFIG, 32 * 1024**2)
            require(isinstance(config, dict) and config.get('os') == 'linux'
                    and config.get('architecture') == 'amd64' and isinstance(config.get('config'), dict),
                    'rollback_oci_config_platform_invalid')
            platform = reference.get('platform')
            if platform is not None:
                require(isinstance(platform, dict) and set(platform) <= {'os', 'architecture', 'variant'}
                        and platform.get('os') == config['os']
                        and platform.get('architecture') == config['architecture']
                        and platform.get('variant', '') == config.get('variant', ''),
                        'rollback_oci_reference_platform_diverge')
            require(not annotations.get('vnd.docker.reference.type'), 'rollback_oci_direct_attestation_refused')
            labels = config['config'].get('Labels')
            require(isinstance(labels, dict) and labels.get('org.opencontainers.image.revision') == expected_sha,
                    'rollback_oci_source_revision_diverge')
            for layer in manifest['layers']:
                require(isinstance(layer, dict) and layer.get('mediaType') in LAYERS,
                        'rollback_oci_layer_type_unreviewed')
                descriptor_blob(layer, layer['mediaType'], json_limit=0)
            row = by_tag[tag]
            require(row['Config'] == 'blobs/sha256/' + manifest['config']['digest'][7:]
                    and row['Layers'] == ['blobs/sha256/' + layer['digest'][7:] for layer in manifest['layers']],
                    'rollback_docker_oci_config_or_layers_diverge')
        require(seen == set(expected), 'rollback_oci_images_incomplete')
