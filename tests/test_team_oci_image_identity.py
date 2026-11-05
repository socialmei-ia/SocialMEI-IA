"""OCI handoff tests: positive image/attestation chain and tampering."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'tools/team-oci-image-identity.py'
spec = importlib.util.spec_from_file_location('oci_image_identity', MODULE)
oci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oci)
SHA = 'a' * 40
OCI_INDEX = 'application/vnd.oci.image.index.v1+json'
OCI_MANIFEST = 'application/vnd.oci.image.manifest.v1+json'
OCI_CONFIG = 'application/vnd.oci.image.config.v1+json'
OCI_EMPTY = 'application/vnd.oci.empty.v1+json'


class OciImageIdentityTests(unittest.TestCase):
    def bundle(self, broken=None, *, direct=False, empty=False):
        blobs = {}

        def blob(value, media_type):
            raw = (json.dumps(value, separators=(',', ':')).encode()
                   if not isinstance(value, bytes) else value)
            digest = 'sha256:' + hashlib.sha256(raw).hexdigest()
            blobs['blobs/sha256/' + digest[7:]] = raw
            return {'mediaType': media_type, 'digest': digest, 'size': len(raw)}

        refs, rows, expected = [], [], {}
        for service in ('team-api', 'team-gateway'):
            tag = f'socialmei-v33/{service}:{SHA}'
            labels = {'org.opencontainers.image.revision':
                      '0' * 40 if broken == 'revision' and service == 'team-api' else SHA}
            config = blob({'config': {'Labels': labels},
                           'architecture': 'arm64' if broken == 'platform' else 'amd64',
                           'os': 'linux'}, OCI_CONFIG)
            layer = blob(b'fixture compressed layer for ' + service.encode(),
                         'application/vnd.oci.image.layer.v1.tar+gzip')
            manifest = blob({'schemaVersion': 2, 'mediaType': OCI_MANIFEST,
                             'config': config, 'layers': [layer]}, OCI_MANIFEST)
            att_config = blob({} if empty else {'kind': 'attestation'},
                              OCI_EMPTY if empty else OCI_CONFIG)
            if empty:
                att_config['data'] = 'e30=' if broken != 'embedded' else 'e10='
            if broken == 'empty-executable':
                manifest = blob({'schemaVersion': 2, 'mediaType': OCI_MANIFEST,
                                 'config': att_config, 'layers': [layer]}, OCI_MANIFEST)
            att_layer = blob(b'fixture in-toto payload', 'application/vnd.in-toto+json')
            att_value = {'schemaVersion': 2, 'mediaType': OCI_MANIFEST,
                         'config': att_config, 'layers': [att_layer]}
            if empty:
                att_value.update(artifactType='application/vnd.docker.attestation.manifest.v1+json',
                                 subject={**manifest})
                if broken == 'subject':
                    att_value['subject']['digest'] = 'sha256:' + '0' * 64
                if broken == 'artifact-type':
                    att_value['artifactType'] = 'application/unknown'
            att_manifest = blob(att_value, OCI_MANIFEST)
            att_ref = (manifest['digest'] if broken != 'attestation' or
                       service != 'team-api' else 'sha256:' + '0' * 64)
            image_index = blob({
                'schemaVersion': 2, 'mediaType': OCI_INDEX,
                'manifests': [
                    {**manifest, 'platform': {'os': 'linux', 'architecture': 'amd64'}},
                    {**att_manifest,
                     'platform': {'os': 'unknown', 'architecture': 'unknown'},
                     'annotations': {'vnd.docker.reference.type': 'attestation-manifest',
                                     'vnd.docker.reference.digest': att_ref}},
                ]}, OCI_INDEX)
            reference = manifest if direct else image_index
            refs.append({**reference, 'annotations': {
                'io.containerd.image.name': 'docker.io/' + tag,
                'org.opencontainers.image.ref.name': SHA}})
            expected[tag] = {'tag': tag, 'image_id': reference['digest']}
            rows.append({'RepoTags': [tag],
                         'Config': 'blobs/sha256/' + config['digest'][7:],
                         'Layers': ['blobs/sha256/' + layer['digest'][7:]]})
        if broken == 'receipt':
            expected[rows[0]['RepoTags'][0]]['image_id'] = 'sha256:' + '0' * 64
        if broken == 'manifest':
            rows[0]['Layers'] = []
        if broken == 'layer':
            blobs[rows[0]['Layers'][0]] = b'corrupted layer bytes'
        if broken == 'index':
            blobs['blobs/sha256/' + refs[0]['digest'][7:]] += b' '
        if broken == 'config':
            name = rows[0]['Config']
            blobs[name] = blobs[name].replace(b'linux', b'other')
        if broken == 'size':
            refs[0]['size'] += 1
        if broken == 'tag':
            refs[0]['annotations']['io.containerd.image.name'] += '-wrong'
        root = {'schemaVersion': 2, 'mediaType': OCI_INDEX, 'manifests': refs}
        with tempfile.TemporaryDirectory() as folder:
            archive_path = Path(folder) / 'images.tar.gz'
            with tarfile.open(archive_path, 'w:gz') as tar:
                for name, content in {
                    **blobs, 'index.json': json.dumps(root).encode(),
                    'oci-layout': b'{"imageLayoutVersion":"1.0.0"}',
                    'manifest.json': json.dumps(rows).encode(),
                }.items():
                    item = tarfile.TarInfo(name)
                    item.size = len(content)
                    tar.addfile(item, io.BytesIO(content))
            with tarfile.open(archive_path, 'r:gz') as tar:
                by_name = {member.name: member for member in tar.getmembers()}
                oci.verify_oci_archive_identity(tar, by_name, rows, expected, SHA)

    def test_valid_oci_index_with_attestations(self):
        self.bundle()

    def test_valid_direct_manifest_uses_config_platform(self):
        self.bundle(direct=True)

    def test_valid_empty_attestation_config_and_subject(self):
        self.bundle(empty=True)

    def test_empty_config_cannot_be_executable(self):
        with self.assertRaises(RuntimeError):
            self.bundle('empty-executable', empty=True)

    def test_empty_attestation_requires_matching_embedded_data(self):
        with self.assertRaises(RuntimeError):
            self.bundle('embedded', empty=True)

    def test_empty_attestation_requires_matching_subject(self):
        with self.assertRaises(RuntimeError):
            self.bundle('subject', empty=True)

    def test_empty_attestation_requires_reviewed_artifact_type(self):
        with self.assertRaises(RuntimeError):
            self.bundle('artifact-type', empty=True)

    def test_direct_manifest_rejects_tampering_and_other_platforms(self):
        for broken in ('receipt', 'manifest', 'layer', 'index', 'revision',
                       'config', 'platform', 'size', 'tag'):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError):
                self.bundle(broken, direct=True)

    def test_index_rejects_config_platform_mismatch(self):
        with self.assertRaises(RuntimeError):
            self.bundle('platform')

    def test_rejects_wrong_image_id(self):
        with self.assertRaises(RuntimeError):
            self.bundle('receipt')

    def test_rejects_tampered_oci_index(self):
        with self.assertRaises(RuntimeError):
            self.bundle('index')

    def test_rejects_attestation_link_to_another_image(self):
        with self.assertRaises(RuntimeError):
            self.bundle('attestation')

    def test_rejects_changed_config_revision(self):
        with self.assertRaises(RuntimeError):
            self.bundle('revision')

    def test_rejects_docker_manifest_mismatch(self):
        with self.assertRaises(RuntimeError):
            self.bundle('manifest')

    def test_rejects_layer_blob_tampering(self):
        with self.assertRaises(RuntimeError):
            self.bundle('layer')


if __name__ == '__main__':
    unittest.main()
