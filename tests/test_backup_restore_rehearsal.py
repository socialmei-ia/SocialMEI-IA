"""Synthetic inputs and Docker fakes only; no database/archive/provider access."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('restore_runner', ROOT / 'tools/backup-restore-rehearsal.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
BACKUP_SPEC = importlib.util.spec_from_file_location('backup_gate', ROOT / 'tools/aws-postgres-backup.py')
backup_gate = importlib.util.module_from_spec(BACKUP_SPEC)
BACKUP_SPEC.loader.exec_module(backup_gate)


def manifest(profile=40):
    return {'manifest_version': 1, 'large_objects': 0, 'structure': {}, 'tables': [],
            'sequences': [], 'foreign_keys': [], 'effective_permissions': [],
            'migration_ledger': [{'schema': 'socialmei', 'versions': [f'{index:03}_synthetic.sql'
                                 for index in range(1, profile + 1)]}], 'valid': True}


def fixture(folder, profile=40):
    dump, expected, approval = [Path(folder) / name for name in ('synthetic.dump', 'manifest.json', 'approval.json')]
    dump.write_bytes(b'PGDMPsynthetic-only-not-an-archive')
    expected.write_text(json.dumps(manifest(profile)))
    data = {'explicit_authorization': True, 'scope': 'isolated_restore', 'production_mutation': False,
            'dump_sha256': runner.file_hash(dump), 'manifest_sha256': runner.file_hash(expected),
            'profile': f'{profile:03}', 'postgres_major': 17, 'postgres_image_id': 'sha256:' + 'a' * 64}
    approval.write_text(json.dumps(data))
    return dump, expected, approval


class RestoreRehearsalTests(unittest.TestCase):
    def test_portable_recovery_set_keeps_manifest_and_restore_proof_without_credentials_or_provider_io(self):
        with tempfile.TemporaryDirectory() as folder:
            files = fixture(folder); auth = json.loads(files[2].read_text())
            auth['private_sentinel'] = 'DO_NOT_COPY_CONFIGURATION'; files[2].write_text(json.dumps(auth))
            proof = Path(folder) / 'restore.private.json'
            result = dict(profile='040', dump_sha256=auth['dump_sha256'], manifest_sha256=auth['manifest_sha256'],
                restoration_verified=True, verification_mode='full_comparison', source_contents_compared=True,
                archive_integrity_verified=True, owned_cleanup_verified=True, production_mutation=False)
            proof.write_text(json.dumps(result)); output = Path(folder) / 'recovery.tar'
            with patch.object(runner.subprocess, 'run') as process:
                receipt = runner.package_recovery(*files, proof, output)
                process.assert_not_called()
            self.assertFalse(receipt['external_uploaded'])
            second = runner.package_recovery(*files, proof, Path(folder) / 'same-inputs.tar')
            self.assertEqual(second['sha256'], receipt['sha256'])
            inactive = Path(folder) / 'must-not-exist.tar'
            with patch.object(runner, 'package_recovery') as package, contextlib.redirect_stdout(io.StringIO()):
                runner.main(['--package-output', str(inactive)])
                package.assert_not_called()
            self.assertFalse(inactive.exists())

            with tarfile.open(output) as archive:
                self.assertEqual(archive.getnames(), receipt['files'])
                self.assertTrue(all(p.isfile() and p.mode == 0o600 for p in archive.getmembers()))
                index = archive.extractfile('recovery-index.private.json').read()
                self.assertNotIn(b'DO_NOT_COPY_CONFIGURATION', index)
            with self.assertRaises(ValueError): runner.package_recovery(*files, proof, output)
            self.assertTrue(output.exists())
            proof.write_text(json.dumps({**result, 'DATABASE_URL': 'private-sentinel'}))
            with self.assertRaises(ValueError):
                runner.package_recovery(*files, proof, Path(folder) / 'invalid-proof.tar')
            for field in ('owned_cleanup_verified', 'source_contents_compared', 'restoration_verified'):
                proof.write_text(json.dumps({**result, field: False}))
                target = Path(folder) / (field + '.tar')
                with self.assertRaises(ValueError): runner.package_recovery(*files, proof, target)
                self.assertFalse(target.exists())

    def test_external_version_binding_requires_the_exact_uploaded_bytes_and_approved_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            files = fixture(folder)
            auth = json.loads(files[2].read_text())
            receipt = Path(folder) / 'external.private.json'
            original = {'external_uploaded': True, 'sha256': auth['dump_sha256'],
                        'external_object_sha256': auth['dump_sha256'],
                        'bytes': files[0].stat().st_size, 'external_version_id': 'version-one'}
            def write(value):
                receipt.write_text(json.dumps(value))
                files[2].write_text(json.dumps({**auth, 'external_receipt_file': str(receipt),
                                               'external_receipt_sha256': runner.file_hash(receipt)}))
            write(original)
            self.assertEqual(runner.inputs(*files)[0]['_verified_external_version_id'], 'version-one')
            for key, value in [('external_uploaded', False), ('sha256', 'b' * 64),
                               ('external_object_sha256', 'b' * 64), ('bytes', 1),
                               ('external_version_id', 'null'), ('external_version_id', 'bad\nversion')]:
                with self.subTest(key=key), self.assertRaises(ValueError):
                    write({**original, key: value}); runner.inputs(*files)
            write(original)
            receipt.write_text(json.dumps({**original, 'external_version_id': 'replaced'}))
            with self.assertRaises(ValueError): runner.inputs(*files)

    def test_periodic_integrity_requires_explicit_mode_and_does_not_claim_source_equality(self):
        baseline = manifest()
        baseline['tables'] = [{'schema': 'socialmei', 'table': 'fixture', 'rows': 1, 'sha256': 'a' * 64}]
        baseline['sequences'] = [{'schema': 'socialmei', 'sequence': 'fixture_seq', 'definition': ['stable'], 'last_value': 1, 'is_called': True}]
        evolved = copy.deepcopy(baseline)
        evolved['tables'][0].update(rows=2, sha256='b' * 64)
        evolved['sequences'][0]['last_value'] = 2
        with self.assertRaises(ValueError):
            runner.verify_manifest(baseline, evolved)
        result = runner.verify_manifest(baseline, evolved, 'archive_integrity')
        self.assertFalse(result['source_contents_compared'])
        self.assertTrue(result['archive_integrity_verified'])
        self.assertEqual(result['restored_rows'], 2)
        for section, value in [('structure', {'changed': True}), ('tables', []),
                               ('migration_ledger', []), ('sequences', []), ('valid', False)]:
            with self.subTest(section=section), self.assertRaises(ValueError):
                runner.verify_manifest(baseline, {**evolved, section: value}, 'archive_integrity')

    def test_periodic_mode_rejects_unknown_modes_and_non040_profile(self):
        with tempfile.TemporaryDirectory() as folder:
            files = fixture(folder, 39)
            approval = json.loads(files[2].read_text())
            for mode in ('unknown', 'archive_integrity'):
                files[2].write_text(json.dumps({**approval, 'verification_mode': mode}))
                with self.assertRaises(ValueError):
                    runner.inputs(*files)

    def test_default_plan_and_rejection_of_remote_or_apply_flags(self):
        with patch.object(runner, 'run') as calls, contextlib.redirect_stdout(io.StringIO()):
            runner.main([])
        calls.assert_not_called()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            runner.main(['--dsn', 'postgresql://production/db'])

    def test_approval_hash_profile_and_scope_are_required_before_docker(self):
        with tempfile.TemporaryDirectory() as folder:
            dump, expected, approval = fixture(folder)
            original = json.loads(approval.read_text())
            for key, value in [('explicit_authorization', False), ('scope', 'production'),
                               ('dump_sha256', 'bad'), ('manifest_sha256', 'bad'),
                               ('profile', '041'), ('postgres_image_id', 'postgres:latest'),
                               ('validator_api_image_id', 'mutable:tag')]:
                with self.subTest(key=key), patch.object(runner, 'run') as calls:
                    approval.write_text(json.dumps({**original, key: value}))
                    with self.assertRaises(ValueError):
                        runner.rehearse(dump, expected, approval)
                    calls.assert_not_called()

    def test_038_039_040_inputs_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            for profile in (38, 39, 40):
                files = fixture(folder, profile)
                self.assertEqual(runner.inputs(*files)[0]['profile'], f'{profile:03}')
            files[0].write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                runner.inputs(*files)

    def test_cleanup_never_removes_an_unowned_container(self):
        obj = [{'Config': {'Labels': {'socialmei.isolated-restore': 'somebody-else'}},
                'HostConfig': {'NetworkMode': 'none'}}]
        with patch.object(runner, 'run', return_value=json.dumps(obj).encode()) as calls:
            with self.assertRaises(ValueError):
                runner.cleanup('docker', 'somebody-else', 'owned', 'none')
        self.assertEqual(calls.call_count, 1)

    def test_isolated_restore_and_mismatch_always_cleanup_both_owned_containers(self):
        for corrupt in (False, True):
            with self.subTest(corrupt=corrupt), tempfile.TemporaryDirectory() as folder:
                files = fixture(folder)
                auth = json.loads(files[2].read_text())
                external = Path(folder) / 'external.private.json'
                external.write_text(json.dumps({'external_uploaded': True,
                    'sha256': auth['dump_sha256'], 'external_object_sha256': auth['dump_sha256'],
                    'bytes': files[0].stat().st_size, 'external_version_id': 'version-one'}))
                files[2].write_text(json.dumps({**auth, 'external_receipt_file': str(external),
                                               'external_receipt_sha256': runner.file_hash(external)}))
                commands = []
                networks = {}
                labels = {}
                def command(docker, *args, **kwargs):
                    commands.append(args)
                    if args == ('context', 'inspect'):
                        return b'[{"Endpoints":{"docker":{"Host":"unix:///local.sock"}}}]'
                    if args[:2] == ('image', 'inspect'):
                        return json.dumps([{'Id': args[2]}]).encode()
                    if args[0] == 'create':
                        name = args[args.index('--name') + 1]
                        networks[name] = args[args.index('--network') + 1]
                        labels[name] = args[args.index('--label') + 1].split('=', 1)[1]
                        self.assertNotIn('--publish', args)
                        self.assertIn('--read-only', args)
                        return (('c' if name.endswith('-check') else 'b') * 64).encode()
                    if args[:2] == ('start', '-a'):
                        value = manifest()
                        if corrupt:
                            value['sequences'] = [{'last_value': 999}]
                        return json.dumps(value).encode()
                    if args[0] == 'inspect':
                        return json.dumps([{'Config': {'Labels': {'socialmei.isolated-restore': labels[args[1]]}},
                                            'HostConfig': {'NetworkMode': networks[args[1]]}}]).encode()
                    if args[0] == 'exec' and args[-2:] == ('postgres', '--version'):
                        return b'postgres (PostgreSQL) 17.11'
                    if args[0] == 'exec' and 'pg_isready' in args:
                        self.assertEqual(args[args.index('-h') + 1], '127.0.0.1')
                    return b''
                with patch.dict(runner.os.environ, {'DOCKER_HOST': ''}), patch.object(runner, 'run', side_effect=command):
                    if corrupt:
                        with self.assertRaises(ValueError):
                            runner.rehearse(*files)
                    else:
                        result = runner.rehearse(*files)
                        self.assertTrue(result['restoration_verified'])
                        self.assertTrue(result['owned_cleanup_verified'])
                        self.assertFalse(result['production_mutation'])
                        self.assertEqual(result['external_version_id'], 'version-one')
                        self.assertEqual(result['external_receipt_sha256'], runner.file_hash(external))
                        # The real rehearsal output feeds the activation gate
                        # directly, without a hand-edited conversion receipt.
                        root = Path(folder); os.chmod(root, 0o700)
                        proof = root / 'restore.private.json'
                        proof.write_text(json.dumps(result)); os.chmod(proof, 0o600)
                        config = {'backup_target_approved': True, 'container': backup_gate.NAME,
                                  'database': 'socialmei_candidate040_20261114',
                                  'admin_user': 'relocation_admin', 'schema': '040',
                                  'source': 'approved_schema040_destination',
                                  'current_production_backup': True,
                                  'restore_receipt_file': str(proof),
                                  'validated_backup_sha256': result['dump_sha256']}
                        target = root / 'destination.private.json'
                        target.write_text(json.dumps(config)); os.chmod(target, 0o600)
                        with patch.object(backup_gate, 'ROOT', backup_gate.ROOT):
                            self.assertEqual(backup_gate.select_approved040_root(root), config)
                self.assertEqual(sum(args[0] == 'rm' for args in commands), 2)


if __name__ == '__main__':
    unittest.main()
