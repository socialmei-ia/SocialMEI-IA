"""Real tar/JSON/hash fixtures; no Docker, images, credentials or network."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('functional038_rollback_images', ROOT / 'tools/team-functional038-rollback-images.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
SHA = 'a' * 40


class RollbackImageIdentityTests(unittest.TestCase):
    def fixture(self, kind='direct', broken=None):
        blobs, rows, references, expected = {}, [], [], {}
        def blob(value, media_type):
            raw = value if isinstance(value, bytes) else json.dumps(value, separators=(',', ':')).encode()
            digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
            blobs['blobs/sha256/' + digest[7:]] = raw
            return {'mediaType': media_type, 'digest': digest, 'size': len(raw)}
        for service in ('team-api', 'team-gateway'):
            target = service == 'team-api'
            tag = f'socialmei-v33/{service}:{SHA}'
            config_object = {'os': 'linux', 'architecture': 'amd64', 'config': {'Cmd': [service], 'Labels': {
                'org.opencontainers.image.revision': 'b' * 40 if broken == 'revision' and target else SHA}}}
            if target and broken == 'platform': config_object['architecture'] = 'arm64'
            if target and broken == 'os': config_object['os'] = 'windows'
            config_bytes = json.dumps(config_object).encode()
            if target and broken == 'duplicate-json':
                config_bytes = config_bytes[:-1] + b',"os":"linux"}'
            config = blob(config_bytes, helper.CONFIG)
            layer = blob(('fictional layer ' + service).encode(),
                         'application/vnd.in-toto+json' if broken == 'layer-type' and target
                         else 'application/vnd.oci.image.layer.v1.tar+gzip')
            layer_descriptor = copy.deepcopy(layer)
            if broken == 'layer-size' and target: layer_descriptor['size'] += 1
            manifest_object = {'schemaVersion': 2, 'mediaType': helper.MANIFEST,
                               'config': config, 'layers': [layer_descriptor]}
            manifest = blob(manifest_object, helper.MANIFEST)
            reference = copy.deepcopy(manifest)
            if kind == 'index':
                reference = blob({'schemaVersion': 2, 'mediaType': helper.INDEX, 'manifests': [
                    {**manifest, 'platform': {'os': 'linux', 'architecture': 'amd64'}}]}, helper.INDEX)
            reference['annotations'] = {'io.containerd.image.name': 'docker.io/' + tag,
                                        'org.opencontainers.image.ref.name': SHA}
            if kind == 'direct-platform': reference['platform'] = {'os': 'linux', 'architecture': 'amd64'}
            if target and broken == 'reference-platform': reference['platform'] = {'os': 'linux', 'architecture': 'arm64'}
            if target and broken == 'reference-type': reference['mediaType'] = 'unreviewed/type'
            if target and broken == 'tag': reference['annotations']['io.containerd.image.name'] += '-other'
            if target and broken == 'ref-source': reference['annotations']['org.opencontainers.image.ref.name'] = 'b' * 40
            references.append(reference)
            expected[service] = {'tag': tag, 'image_id': reference['digest']}
            rows.append({'RepoTags': [tag], 'Config': 'blobs/sha256/' + config['digest'][7:],
                         'Layers': ['blobs/sha256/' + layer['digest'][7:]]})
            if target and broken in ('manifest-bitflip', 'config-bitflip', 'layer-bitflip'):
                descriptor = {'manifest-bitflip': manifest, 'config-bitflip': config, 'layer-bitflip': layer}[broken]
                name = 'blobs/sha256/' + descriptor['digest'][7:]
                raw = blobs[name]
                blobs[name] = bytes([raw[0] ^ 1]) + raw[1:]
            if kind == 'classic': expected[service]['image_id'] = config['digest']
        if broken == 'receipt': expected['team-api']['image_id'] = 'sha256:' + '0' * 64
        if broken == 'docker-config': rows[0]['Config'] = rows[1]['Config']
        if broken == 'docker-layers': rows[0]['Layers'] = []
        if broken == 'duplicate-tag': rows[1]['RepoTags'] = rows[0]['RepoTags']
        if broken == 'duplicate-reference': references[1] = references[0]
        if broken == 'reference-size': references[0]['size'] += 1
        content = {**blobs, 'manifest.json': json.dumps(rows).encode()}
        if kind != 'classic':
            content.update({'index.json': json.dumps({'schemaVersion': 2, 'mediaType': helper.INDEX,
                                                      'manifests': references}).encode(),
                            'oci-layout': b'{"imageLayoutVersion":"1.0.0"}'})
        if broken == 'traversal': content['../unexpected'] = b'refuse'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'rollback.tar'
            with tarfile.open(path, 'w') as archive:
                for name, raw in content.items():
                    member = tarfile.TarInfo(name); member.size = len(raw)
                    archive.addfile(member, io.BytesIO(raw))
                if broken == 'duplicate-member':
                    member = tarfile.TarInfo('index.json'); member.size = len(content['index.json'])
                    archive.addfile(member, io.BytesIO(content['index.json']))
            helper.verify_archive_config_digests(path, expected, SHA, 'bundle')

    def test_valid_direct_manifest(self):
        self.fixture()

    def test_valid_direct_manifest_with_matching_platform(self):
        self.fixture(kind='direct-platform')

    def test_established_index_path_still_verifies(self):
        self.fixture(kind='index')

    def test_established_classic_path_still_verifies(self):
        self.fixture(kind='classic')

    def test_rejects_wrong_full_manifest_digest_or_size(self):
        for broken in ('receipt', 'reference-size', 'manifest-bitflip'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)

    def test_rejects_config_byte_tampering_and_source_mismatch(self):
        for broken in ('config-bitflip', 'revision', 'ref-source'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)

    def test_rejects_layer_digest_size_or_type_mismatch(self):
        for broken in ('layer-bitflip', 'layer-size', 'layer-type'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)

    def test_rejects_other_platform_and_reference_config_disagreement(self):
        for broken in ('platform', 'os', 'reference-platform'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)

    def test_rejects_docker_config_or_layer_disagreement(self):
        for broken in ('docker-config', 'docker-layers'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)

    def test_rejects_tag_duplicates_and_unknown_reference_type(self):
        for broken in ('tag', 'duplicate-tag', 'duplicate-reference', 'reference-type'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)

    def test_rejects_traversal_duplicate_tar_member_and_duplicate_json_key(self):
        for broken in ('traversal', 'duplicate-member', 'duplicate-json'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError): self.fixture(broken=broken)


if __name__ == '__main__':
    unittest.main()
