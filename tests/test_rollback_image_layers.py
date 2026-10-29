"""Synthetic rollback archives; no Docker, network or production data."""
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    'rollback_image_layers', Path(__file__).resolve().parents[1] / 'tools/v25-release-publish.py')
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


def identity(data):
    return 'sha256:' + hashlib.sha256(data).hexdigest()


def fixture(oci=False, compressed=False, corrupt=False, wrong_diff=False):
    layer = io.BytesIO()
    with tarfile.open(fileobj=layer, mode='w:') as archive:
        info = tarfile.TarInfo('synthetic.txt')
        info.size = 7
        archive.addfile(info, io.BytesIO(b'fixture'))
    expanded = layer.getvalue()
    content = gzip.compress(expanded, mtime=0) if compressed else expanded
    config = json.dumps({'architecture': 'amd64', 'os': 'linux',
                         'rootfs': {'type': 'layers', 'diff_ids': [
                             identity(b'wrong') if wrong_diff else identity(expanded)]}}).encode()
    config_id = identity(config)
    config_name = 'blobs/sha256/' + config_id[7:] if oci else config_id[7:] + '.json'
    layer_name = 'blobs/sha256/' + identity(content)[7:] if oci else 'layer/layer.tar'
    entries = {config_name: config, layer_name: content}
    expected = config_id
    if oci:
        def blob(value):
            data = json.dumps(value).encode()
            descriptor = {'digest': identity(data), 'size': len(data)}
            entries['blobs/sha256/' + descriptor['digest'][7:]] = data
            return descriptor
        manifest = blob({'schemaVersion': 2,
                         'config': {'digest': config_id, 'size': len(config)},
                         'layers': [{'digest': identity(content), 'size': len(content)}]})
        manifest['platform'] = {'os': 'linux', 'architecture': 'amd64'}
        root = blob({'schemaVersion': 2, 'manifests': [manifest]})
        entries['index.json'] = json.dumps({'manifests': [root]}).encode()
        expected = root['digest']
    entries['manifest.json'] = json.dumps([{
        'Config': config_name, 'RepoTags': ['synthetic:rollback'], 'Layers': [layer_name]}]).encode()
    if corrupt:
        changed = bytearray(entries[layer_name])
        changed[len(changed) // 2] ^= 1
        entries[layer_name] = bytes(changed)
    return entries, expected


def save(path, entries, extra=None):
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        if extra is not None:
            archive.addfile(extra)


class RollbackLayerTests(unittest.TestCase):
    def test_valid_classic_and_oci_raw_and_gzip_layers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'images.tar.gz'
            for oci in (False, True):
                for compressed in (False, True):
                    with self.subTest(oci=oci, compressed=compressed):
                        entries, expected = fixture(oci, compressed)
                        save(path, entries)
                        publish.verify_image_archive(path, {'synthetic:rollback': expected})

    def test_changed_layer_bytes_cannot_borrow_valid_config_or_oci_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'images.tar.gz'
            for oci in (False, True):
                for compressed in (False, True):
                    with self.subTest(oci=oci, compressed=compressed):
                        entries, expected = fixture(oci, compressed, corrupt=True)
                        save(path, entries)
                        with self.assertRaises((RuntimeError, OSError, EOFError)):
                            publish.verify_image_archive(path, {'synthetic:rollback': expected})

    def test_valid_layer_bytes_must_match_config_diff_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'images.tar.gz'
            for oci in (False, True):
                with self.subTest(oci=oci):
                    entries, expected = fixture(oci, wrong_diff=True)
                    save(path, entries)
                    with self.assertRaises(RuntimeError):
                        publish.verify_image_archive(path, {'synthetic:rollback': expected})

    def test_symlink_entry_is_rejected_without_extracting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'images.tar.gz'
            entries, expected = fixture()
            link = tarfile.TarInfo('unsafe-link')
            link.type = tarfile.SYMTYPE
            link.linkname = '/outside'
            save(path, entries, link)
            with self.assertRaises(RuntimeError):
                publish.verify_image_archive(path, {'synthetic:rollback': expected})

    def test_directory_headers_count_towards_archive_entry_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'images.tar.gz'
            entries, expected = fixture()
            with tarfile.open(path, 'w:gz') as archive:
                for index in range(10001):
                    info = tarfile.TarInfo('directory-' + str(index))
                    info.type = tarfile.DIRTYPE
                    archive.addfile(info)
                for name, data in entries.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            with self.assertRaises(RuntimeError):
                publish.verify_image_archive(path, {'synthetic:rollback': expected})


if __name__ == '__main__':
    unittest.main()
