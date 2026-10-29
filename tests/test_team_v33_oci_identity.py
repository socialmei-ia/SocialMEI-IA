"""Classic config digest versus containerd OCI identities, with actual tar bytes."""
import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('v33_oci_importer', Path(__file__).resolve().parents[1] / 'tools/team-v33-import-images.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def digest(value):
    return 'sha256:' + hashlib.sha256(value).hexdigest()


class OciIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.path = self.folder / 'image.tar'
        self.tag = 'socialmei-v33/team-api:' + module.EXPECTED_SHA
        self.layer = b'synthetic uncompressed filesystem bytes'
        self.config = {'os': 'linux', 'architecture': 'amd64',
                       'rootfs': {'type': 'layers', 'diff_ids': [digest(self.layer)]}}

    def archive(self, *, index=False, corrupt=False, wrong_diff=False, missing=False, duplicate=False):
        files = {}
        def blob(value, media=None):
            raw = json.dumps(value, sort_keys=True).encode() if isinstance(value, dict) else value
            identity = digest(raw)
            files['blobs/sha256/' + identity[7:]] = raw
            return {'digest': identity, 'size': len(raw), 'mediaType': media or 'application/vnd.oci.image.config.v1+json'}
        config = copy.deepcopy(self.config)
        if wrong_diff:
            config['rootfs']['diff_ids'] = ['sha256:' + '0' * 64]
        c = blob(config)
        layer = blob(gzip.compress(self.layer), 'application/vnd.oci.image.layer.v1.tar+gzip')
        m = blob({'schemaVersion': 2, 'config': c, 'layers': [layer]}, 'application/vnd.oci.image.manifest.v1+json')
        root = m
        if index:
            child = dict(m, platform={'os': 'linux', 'architecture': 'amd64'})
            root = blob({'schemaVersion': 2, 'manifests': [child]}, 'application/vnd.oci.image.index.v1+json')
        config_name = 'blobs/sha256/' + c['digest'][7:]
        layer_name = 'blobs/sha256/' + layer['digest'][7:]
        files['manifest.json'] = json.dumps([{'Config': config_name, 'RepoTags': [self.tag], 'Layers': [layer_name]}]).encode()
        if corrupt:
            files[layer_name] = b'corrupted but present'
        if missing:
            del files[config_name]
        with tarfile.open(self.path, 'w:') as archive:
            for name, raw in files.items():
                info = tarfile.TarInfo(name); info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
            if duplicate:
                raw = files['manifest.json']; info = tarfile.TarInfo('manifest.json'); info.size = len(raw)
                archive.addfile(info, io.BytesIO(raw))
        return c['digest'], root['digest'], root['mediaType'], m['digest']

    def test_classic_config_receipt_matches_local_manifest(self):
        expected, local, _, _ = self.archive()
        self.assertNotEqual(expected, local)
        module.verify_oci_identity(self.path, expected, local, self.tag)

    def test_classic_config_receipt_matches_local_index(self):
        expected, local, _, _ = self.archive(index=True)
        module.verify_oci_identity(self.path, expected, local, self.tag)

    def test_index_receipt_can_resolve_same_local_manifest(self):
        _, expected, _, local = self.archive(index=True)
        module.verify_oci_identity(self.path, expected, local, self.tag)

    def test_bad_receipt_layer_bytes_diff_ids_missing_config_and_duplicate_refused(self):
        for options in ({'corrupt': True}, {'wrong_diff': True}, {'missing': True}, {'duplicate': True}):
            with self.subTest(options=options):
                expected, local, _, _ = self.archive(**options)
                with self.assertRaises(RuntimeError):
                    module.verify_oci_identity(self.path, expected, local, self.tag)
        expected, local, _, _ = self.archive()
        with self.assertRaises(RuntimeError):
            module.verify_oci_identity(self.path, 'sha256:' + '0' * 64, local, self.tag)

    def test_local_oci_status_uses_read_only_save_not_load(self):
        expected, local, media, _ = self.archive()
        fixture = self.path.read_bytes()
        receipt = {'images': {s: {'tag': self.tag, 'image_id': expected} for s in module.SERVICES}}
        row = {'Id': local, 'Descriptor': {'digest': local, 'mediaType': media},
               'Config': {'Labels': {'org.opencontainers.image.revision': module.EXPECTED_SHA}}}
        commands = []
        def docker(*args, **kwargs):
            commands.append(args)
            if args[:2] == ('image', 'save'):
                Path(args[3]).write_bytes(fixture)
                return ''
            return json.dumps([row])
        with patch.object(module, 'BACKUPS', self.folder), patch.object(module, 'docker', side_effect=docker):
            self.assertTrue(all(module.local_image_status(receipt).values()))
        self.assertEqual(sum(args[:2] == ('image', 'save') for args in commands), 2)
        self.assertFalse(any('load' in args for args in commands))
        self.assertFalse(list(self.folder.glob('team-v33-identity-*')))

    def test_classic_local_id_needs_no_export(self):
        expected, _, _, _ = self.archive()
        receipt = {'images': {s: {'tag': self.tag, 'image_id': expected} for s in module.SERVICES}}
        row = {'Id': expected, 'Config': {'Labels': {'org.opencontainers.image.revision': module.EXPECTED_SHA}}}
        with patch.object(module, 'docker', return_value=json.dumps([row])) as docker:
            self.assertTrue(all(module.local_image_status(receipt).values()))
            self.assertTrue(all(call.args[:2] == ('image', 'inspect') for call in docker.call_args_list))
