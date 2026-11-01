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


class OciImageIdentityTests(unittest.TestCase):
    def bundle(self, broken=None):
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
                           'architecture': 'amd64', 'os': 'linux'}, OCI_CONFIG)
            layer = blob(b'fixture compressed layer for ' + service.encode(),
                         'application/vnd.oci.image.layer.v1.tar+gzip')
            manifest = blob({'schemaVersion': 2, 'mediaType': OCI_MANIFEST,
                             'config': config, 'layers': [layer]}, OCI_MANIFEST)
            att_config = blob({'kind': 'attestation'}, OCI_CONFIG)
            att_layer = blob(b'fixture in-toto payload', 'application/vnd.in-toto+json')
            att_manifest = blob({'schemaVersion': 2, 'mediaType': OCI_MANIFEST,
                                 'config': att_config, 'layers': [att_layer]}, OCI_MANIFEST)
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
            refs.append({**image_index, 'annotations': {
                'io.containerd.image.name': 'docker.io/' + tag,
                'org.opencontainers.image.ref.name': SHA}})
            expected[tag] = {'tag': tag, 'image_id': image_index['digest']}
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
