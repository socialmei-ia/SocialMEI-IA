#!/usr/bin/env python3
"""Back up only the isolated destination; never switches production connections."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import shutil
import secrets
import re
import stat
from urllib.parse import urlsplit, unquote, parse_qsl

ROOT = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
NAME = 'socialmei-postgres-relocation-20261112'


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def select_approved040_root(path):
    """Explicit private opt-in; the existing historical timer retains its default."""
    global ROOT
    path = Path(path).absolute()
    if (not path.is_dir() or any(parent.is_symlink() or (parent / '.git').exists()
                               for parent in (path, *path.parents))):
        raise RuntimeError('approved_backup_root_invalid')
    config = path / 'destination.private.json'
    if config.is_symlink() or not config.is_file():
        raise RuntimeError('approved_backup_config_invalid')
    private_ownership(path, config)
    values = json.loads(config.read_text())
    if (values.get('backup_target_approved') is not True
            or values.get('container') != NAME
            or values.get('database') != 'socialmei_candidate040_20261114'
            or values.get('admin_user') != 'relocation_admin'
            or (values.get('schema'), values.get('source')) not in (
                ('040', 'approved_schema040_destination'), ('041', 'approved_schema041_destination'))
            or type(values.get('current_production_backup')) is not bool):
        raise RuntimeError('approved_backup_target_mismatch')
    receipt = Path(values.get('restore_receipt_file', ''))
    if not receipt.is_file() or any(item.is_symlink() for item in (receipt, *receipt.parents)):
        raise RuntimeError('approved_backup_restore_receipt_missing')
    private_ownership(receipt.parent, receipt)
    verified = json.loads(receipt.read_text())
    expected_hash = values.get('validated_backup_sha256')
    legacy_restore = (values.get('schema') == '040' and verified.get('independent_restore_equal') is True
                      and verified.get('comparison', {}).get('equal') is True
                      and verified.get('sha256') == expected_hash)
    # Consume the existing isolated rehearsal's native receipt. Integrity-only
    # comparisons against an older baseline must never qualify as source equality.
    current_restore = (verified.get('restoration_verified') is True
                       and verified.get('profile') == values['schema']
                       and verified.get('verification_mode') == 'full_comparison'
                       and verified.get('source_contents_compared') is True
                       and verified.get('archive_integrity_verified') is True
                       and verified.get('owned_cleanup_verified') is True
                       and verified.get('production_mutation') is False
                       and verified.get('dump_sha256') == expected_hash)
    if (not (legacy_restore or current_restore)
            or re.fullmatch(r'[0-9a-f]{64}', str(expected_hash)) is None):
        raise RuntimeError('approved_backup_restore_not_verified')
    ROOT = path
    return values


def private_ownership(folder, file):
    if os.name == 'nt':
        return  # POSIX ownership is checked on the actual Linux operational host.
    owners = (0, os.getuid())
    if (folder.stat().st_mode & 0o077 or file.stat().st_mode & 0o077
            or file.stat().st_uid not in owners):
        raise RuntimeError('approved_backup_config_not_private')
    for parent in (folder, *folder.parents):
        metadata = parent.stat()
        # A root-owned sticky /tmp cannot rename another owner's private child.
        sticky_root = metadata.st_uid == 0 and metadata.st_mode & stat.S_ISVTX
        if metadata.st_uid not in owners or metadata.st_mode & 0o022 and not sticky_root:
            raise RuntimeError('approved_backup_parent_not_trusted')


def _private_checkpoint(path, value):
    if path.is_symlink():
        raise RuntimeError('external_checkpoint_symlink')
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8) + '.partial')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    if os.name != 'nt':
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def upload_external_versioned(localdump, receipt, config, client):
    """Upload a verified artifact with explicit provenance; resume uncertain PUT by HEAD.

    Caller owns authorization and single-flight scheduling. Private checkpoint
    is persisted before PUT. An uncertain missing object never triggers a PUT
    retry; matching HEAD is reconciled and read back at its immutable VersionId.
    No bucket/configuration creation or production access occurs here.
    """
    path = Path(localdump)
    checkpoint_path = path.with_suffix('.external.private.json')
    if (any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file()
            or path.suffix != '.dump' or checkpoint_path.is_symlink()):
        raise RuntimeError('external_artifact_invalid')
    size = path.stat().st_size
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    checksum = digest.hexdigest()
    if (not 0 < size <= 5 * 1024**3 or receipt.get('sha256') != checksum
            or receipt.get('bytes') != size or receipt.get('archive_index_verified') is not True
            or receipt.get('source') not in ('isolated_historical_destination', 'approved_schema040_destination',
                                              'approved_schema041_destination')
            or type(receipt.get('current_production_backup')) is not bool
            or (receipt.get('source') == 'isolated_historical_destination'
                and receipt.get('current_production_backup') is not False)):
        raise RuntimeError('external_artifact_receipt_invalid')
    endpoint = urlsplit(client.meta.endpoint_url)
    if endpoint.scheme != 'https' or not endpoint.hostname or endpoint.username or endpoint.password:
        raise RuntimeError('external_https_required')
    expected_endpoint = 's3.sa-east-1.amazonaws.com'
    if (endpoint.hostname != expected_endpoint
            or endpoint.netloc.lower() not in (expected_endpoint, expected_endpoint + ':443')
            or endpoint.path not in ('', '/') or endpoint.query or endpoint.fragment):
        raise RuntimeError('external_aws_endpoint_required')
    bucket = config.get('bucket')
    owner = config.get('expected_bucket_owner')
    if not isinstance(bucket, str) or not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', bucket):
        raise RuntimeError('external_bucket_invalid')
    if not isinstance(owner, str) or not re.fullmatch(r'\d{12}', owner):
        raise RuntimeError('external_expected_owner_required')
    common = {'Bucket': bucket, 'ExpectedBucketOwner': owner}
    try:
        versioning = client.get_bucket_versioning(**common)
        encryption = client.get_bucket_encryption(**common)
        block = client.get_public_access_block(**common)['PublicAccessBlockConfiguration']
        ownership = client.get_bucket_ownership_controls(**common)
    except Exception:
        raise RuntimeError('external_bucket_security_unavailable') from None
    algorithms = [rule.get('ApplyServerSideEncryptionByDefault', {}).get('SSEAlgorithm')
                  for rule in encryption.get('ServerSideEncryptionConfiguration', {}).get('Rules', [])]
    if (versioning.get('Status') != 'Enabled' or algorithms != ['AES256']
            or any(block.get(k) is not True for k in
                   ('BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'))
            or ownership.get('OwnershipControls', {}).get('Rules') != [{'ObjectOwnership': 'BucketOwnerEnforced'}]):
        raise RuntimeError('external_bucket_security_invalid')
    key = 'postgres-relocation/' + checksum + '.dump'
    identity = {'sha256': checksum, 'bytes': size, 'key': key,
                'storage_sha256': hashlib.sha256((bucket + ':' + owner).encode()).hexdigest()}
    checkpoint = None
    if checkpoint_path.exists():
        try:
            checkpoint = json.loads(checkpoint_path.read_text())
        except Exception:
            raise RuntimeError('external_checkpoint_invalid') from None
        if any(checkpoint.get(k) != v for k, v in identity.items()):
            raise RuntimeError('external_checkpoint_identity_mismatch')
    checkpoint = checkpoint or dict(identity, phase='prepared')
    obj_args = dict(common, Key=key)
    pinned = checkpoint.get('version_id')
    try:
        obj = client.head_object(**obj_args, **({'VersionId': pinned} if pinned else {}))
    except Exception as error:
        code = str(getattr(error, 'response', {}).get('Error', {}).get('Code', ''))
        if code not in ('404', 'NoSuchKey', 'NotFound'):
            raise RuntimeError('external_head_unavailable') from None
        if checkpoint['phase'] != 'prepared':
            raise RuntimeError('external_uncertain_object_missing') from None
        checkpoint['phase'] = 'put_uncertain'
        _private_checkpoint(checkpoint_path, checkpoint)
        try:
            with path.open('rb') as stream:
                uploaded = client.put_object(**obj_args, Body=stream, IfNoneMatch='*',
                    ServerSideEncryption='AES256', Metadata={'sha256': checksum})
        except Exception:
            raise RuntimeError('external_put_uncertain_reconcile_required') from None
        version = uploaded.get('VersionId')
        if not isinstance(version, str) or not version or version == 'null':
            raise RuntimeError('external_version_missing')
        checkpoint.update(version_id=version, phase='uploaded')
        _private_checkpoint(checkpoint_path, checkpoint)
        try:
            obj = client.head_object(**obj_args)
        except Exception:
            raise RuntimeError('external_head_unavailable') from None
    version = obj.get('VersionId')
    if not isinstance(version, str) or not version or version == 'null':
        raise RuntimeError('external_version_missing')
    if checkpoint.get('version_id') and version != checkpoint['version_id']:
        raise RuntimeError('external_version_changed')
    if (obj.get('ContentLength') != size or obj.get('Metadata', {}).get('sha256') != checksum
            or obj.get('ServerSideEncryption') != 'AES256'):
        raise RuntimeError('external_existing_object_mismatch')
    checkpoint.update(version_id=version, phase='readback_pending')
    _private_checkpoint(checkpoint_path, checkpoint)
    body = None
    try:
        fetched = client.get_object(**obj_args, VersionId=version)
        body = fetched['Body']
        if (fetched.get('VersionId') != version or fetched.get('ContentLength') != size
                or fetched.get('ServerSideEncryption') != 'AES256'):
            raise RuntimeError('external_readback_metadata_invalid')
        readback_hash = hashlib.sha256()
        readback_size = 0
        for chunk in body.iter_chunks(chunk_size=1024 * 1024):
            readback_hash.update(chunk)
            readback_size += len(chunk)
        if readback_size != size or readback_hash.hexdigest() != checksum:
            raise RuntimeError('external_backup_readback_invalid')
    except Exception:
        raise RuntimeError('external_backup_readback_invalid') from None
    finally:
        if body is not None:
            body.close()
    checkpoint.update(phase='verified')
    _private_checkpoint(checkpoint_path, checkpoint)
    return dict(receipt, external_uploaded=True, external_version_id=version,
                external_object_sha256=checksum)


def consistent_export(config, folder, stamp):
    """Export through the reviewed helper, in the source container's namespace."""
    image = config.get('export_helper_image_id', '')
    profile = config.get('schema', '040')
    if profile not in ('040', '041'):
        raise RuntimeError('consistent_export_profile_not_reviewed')
    dsn = config.get('export_source_dsn', '')
    try:
        target = urlsplit(dsn)
        valid = (target.scheme in ('postgres', 'postgresql') and target.hostname == '127.0.0.1'
                 and target.port in (None, 5432) and target.username and target.password
                 and unquote(target.path[1:]) == config['database'] and not target.fragment
                 and parse_qsl(target.query) == [('sslmode', 'disable')])
    except (TypeError, ValueError):
        valid = False
    if not valid or re.fullmatch(r'sha256:[0-9a-f]{64}', image) is None:
        raise RuntimeError('consistent_export_private_configuration_required')
    def docker(*args, timeout=30, env=None):
        result = subprocess.run(['docker', *args], capture_output=True, text=True,
                                check=True, timeout=timeout, env=env)
        return result.stdout
    source = json.loads(docker('inspect', NAME))[0]
    if source['Name'] != '/' + NAME or not source['State']['Running']:
        raise RuntimeError('consistent_export_source_not_running')
    if json.loads(docker('image', 'inspect', image))[0]['Id'] != image:
        raise RuntimeError('consistent_export_image_mismatch')
    directory = folder / ('export-' + stamp)
    directory.mkdir(mode=0o700)
    owner = directory.stat()
    token = secrets.token_hex(12); name = 'socialmei-backup040-export-' + token
    network = 'container:' + source['Id']
    identity = hashlib.sha256(json.dumps(['127.0.0.1', 5432, config['database']]).encode()).hexdigest()
    env = dict(os.environ, SOCIALMEI_EXPORT_SOURCE_DSN=dsn,
               SOCIALMEI_EXPORT_SOURCE_FINGERPRINT=identity)
    try:
        docker('create', '--name', name, '--label', 'socialmei.backup040-export=' + token,
               '--user', str(owner.st_uid) + ':' + str(owner.st_gid),
               '--network', network, '--read-only', '--cap-drop', 'ALL',
               '--security-opt', 'no-new-privileges', '--memory', '256m', '--cpus', '0.5',
               '--pids-limit', '64', '--restart', 'no',
               '--mount', 'type=bind,src=' + str(directory) + ',dst=/artifacts',
               '-e', 'SOCIALMEI_EXPORT_SOURCE_DSN', '-e', 'SOCIALMEI_EXPORT_SOURCE_FINGERPRINT', image,
               '--run', '--approved-data-export', '--isolated-loopback', '--profile', profile,
               '--output-directory', '/artifacts/export', env=env)
        # No credentials in argv. A timeout never starts another helper.
        output = docker('start', '-a', name, timeout=180)
        receipt = json.loads(output)
        if not (receipt.get('source_export_succeeded') is True and receipt.get('shared_snapshot') is True
                and receipt.get('profile') == profile and receipt.get('sequence_state_unchanged_during_export') is True
                and receipt.get('source_database_fingerprint') == identity):
            raise RuntimeError('consistent_export_receipt_invalid')
        exported = directory / 'export'
        dump, manifest = exported / 'source.dump', exported / 'source-manifest.private.json'
        if (dump.is_symlink() or manifest.is_symlink()
                or file_sha256(dump) != receipt['dump_sha256']
                or file_sha256(manifest) != receipt['manifest_sha256']):
            raise RuntimeError('consistent_export_artifact_mismatch')
        destination = folder / ('destination-' + stamp + '.dump')
        destination_manifest = destination.with_suffix('.manifest.private.json')
        if destination.exists() or destination_manifest.exists():
            raise RuntimeError('consistent_export_destination_exists')
        manifest.rename(destination_manifest)
        dump.rename(destination)
        return destination, destination_manifest
    finally:
        # Only this invocation's labeled helper may be removed, never the source.
        owned = json.loads(docker('inspect', name))[0]
        if (owned['Config']['Labels'].get('socialmei.backup040-export') != token
                or owned['HostConfig']['NetworkMode'] != network):
            raise RuntimeError('consistent_export_cleanup_ownership_mismatch')
        docker('rm', '-f', name)


def backup(config=None, *, with_manifest=False):
    if config is None:
        config = json.loads((ROOT / 'destination.private.json').read_text())
    provenance = current_database_provenance(config)
    if with_manifest and not (config.get('current_production_backup') is True and provenance):
        raise RuntimeError('consistent_export_current_database_required')
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise RuntimeError('insufficient_backup_disk_space')
    folder = ROOT / 'backups'
    folder.mkdir(mode=0o700, exist_ok=True)
    storage = client = None
    s3_config = ROOT / 's3-backup.private.json'
    if s3_config.exists():
        import boto3
        storage = json.loads(s3_config.read_text())
        client = boto3.client('s3', region_name='sa-east-1')
        # Only new explicit pending receipts, never bulk-send old historical dumps.
        for pending in sorted(folder.glob('destination-*.json')):
            if pending.name.endswith('.external.private.json'):
                continue
            if pending.is_symlink():
                raise RuntimeError('external_pending_receipt_symlink')
            previous = json.loads(pending.read_text())
            if (previous.get('external_upload_requested') is True
                    and previous.get('external_uploaded') is False):
                recovered = upload_external_versioned(pending.with_suffix('.dump'), previous, storage, client)
                _private_checkpoint(pending, recovered)
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + secrets.token_hex(4)
    path = folder / ('destination-' + stamp + '.dump')
    manifest_path = None
    if with_manifest:
        path, manifest_path = consistent_export(config, folder, stamp)
    else:
        write_dump(config, path)
    receipt = {'created_at_utc': stamp, 'dump_path': str(path), 'bytes': path.stat().st_size,
               'sha256': file_sha256(path),
               'source': config.get('source', 'isolated_historical_destination'),
               'current_production_backup': config.get('current_production_backup', False),
               'external_uploaded': False, 'archive_index_verified': True, 'cutover_authorized': False}
    receipt.update(provenance)
    if manifest_path is not None:
        receipt.update(manifest_path=str(manifest_path), manifest_sha256=file_sha256(manifest_path),
                       shared_snapshot=True, sequence_state_unchanged_during_export=True)
    receipt['external_upload_requested'] = storage is not None
    receipt_path = path.with_suffix('.json')
    _private_checkpoint(receipt_path, receipt)
    if storage is not None:
        receipt = upload_external_versioned(path, receipt, storage, client)
    _private_checkpoint(receipt_path, receipt)
    print(json.dumps(receipt))


def write_dump(config, path):
    partial = path.with_suffix('.dump.partial')
    with partial.open('xb') as stream:
        os.chmod(partial, 0o600)
        result = subprocess.run(['docker', 'exec', NAME, 'pg_dump', '-U', config['admin_user'],
            '-d', config['database'], '--format=custom', '--no-owner', '--no-acl'],
            stdout=stream, stderr=subprocess.PIPE, timeout=120)
        stream.flush()
        os.fsync(stream.fileno())
    if result.returncode:
        raise RuntimeError('destination_backup_failed')
    with partial.open('rb') as stream:
        checked = subprocess.run(['docker', 'exec', '-i', NAME, 'pg_restore', '--list'],
                                 stdin=stream, capture_output=True, timeout=30)
    if checked.returncode:
        raise RuntimeError('destination_backup_index_invalid')
    if path.exists():
        raise RuntimeError('destination_backup_path_exists')
    partial.rename(path)


def current_database_provenance(config):
    """Verify metadata before export; this does not certify a restoration."""
    if config.get('current_production_backup') is not True:
        return {}
    if (config.get('backup_target_approved') is not True
            or config.get('container') != NAME
            or config.get('database') != 'socialmei_candidate040_20261114'
            or config.get('admin_user') != 'relocation_admin'
            or (config.get('schema'), config.get('source')) not in (
                ('040', 'approved_schema040_destination'), ('041', 'approved_schema041_destination'))):
        raise RuntimeError('current_backup_target_not_approved')
    query = (
        "BEGIN READ ONLY; SET LOCAL statement_timeout = '3s'; "
        "SELECT json_build_object('database', current_database(), "
        "'server_version_num', current_setting('server_version_num')::integer, "
        "'versions', array_agg(substring(version FROM '^[0-9]+')::integer "
        "ORDER BY version)) FROM socialmei.schema_migrations; ROLLBACK;"
    )
    try:
        result = subprocess.run(
            ['docker', 'exec', NAME, 'psql', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
             '-U', config['admin_user'], '-d', config['database'], '-c', query],
            capture_output=True, text=True, timeout=15, check=True)
        actual = json.loads(result.stdout)
        if (actual.get('database') != config['database']
                or actual.get('versions') != list(range(1, int(config['schema']) + 1))
                or type(actual.get('server_version_num')) is not int
                or not 170000 <= actual['server_version_num'] < 180000):
            raise ValueError('metadata mismatch')
    except (subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        raise RuntimeError('current_backup_metadata_not_verified') from None
    return {'database': actual['database'], 'container': NAME, 'schema': int(config['schema']),
            'server_version_num': actual['server_version_num'],
            'metadata_verified_before_export': True, 'restore_verified': False}


def install_schedule():
    script = ROOT / 'tools/aws-postgres-backup.py'
    if not script.is_file() or not (ROOT / 'restore-validation-receipt.json').is_file():
        raise RuntimeError('validated_destination_or_backup_script_missing')
    validation = json.loads((ROOT / 'restore-validation-receipt.json').read_text())
    if validation.get('comparison', {}).get('equal') is not True or validation.get('foreign_key_violations') != 0:
        raise RuntimeError('destination_validation_failed')
    service = Path('/etc/systemd/system/socialmei-postgres-relocation-backup.service')
    timer = service.with_suffix('.timer')
    if service.exists() or timer.exists():
        raise RuntimeError('backup_schedule_already_exists')
    service.write_text('[Unit]\nDescription=Backup isolated SocialMEI PostgreSQL relocation\n'
        'After=docker.service\nRequires=docker.service\n'
        '[Service]\nType=oneshot\nUser=root\nUMask=0077\n'
        'ExecStart=/usr/bin/python3 ' + str(script) + ' --run backup\n'
        'NoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\n'
        'ReadWritePaths=' + str(ROOT) + '\nMemoryMax=96M\nTimeoutStartSec=180\n')
    timer.write_text('[Unit]\nDescription=Hourly isolated SocialMEI PostgreSQL backup\n'
                     '[Timer]\nOnCalendar=hourly\nRandomizedDelaySec=180\nPersistent=true\n'
                     '[Install]\nWantedBy=timers.target\n')
    for command in (['systemctl', 'daemon-reload'],
                    ['systemctl', 'enable', '--now', timer.name],
                    ['systemctl', 'start', service.name]):
        subprocess.run(command, check=True, capture_output=True, timeout=180)
    print(json.dumps({'hourly_backup_timer_enabled': True, 'first_run_succeeded': True,
                      'automatic_s3_upload_configured': (ROOT / 's3-backup.private.json').exists(),
                      'source': 'isolated_historical_destination'}))


def prepare_external():
    import boto3
    session = boto3.Session(region_name='sa-east-1')
    client = session.client('s3')
    config = ROOT / 's3-backup.private.json'
    if config.exists():
        raise RuntimeError('external_storage_already_prepared')
    try:
        account = session.client('sts').get_caller_identity()['Account']
        name = 'socialmei-db-relocation-' + account + '-sa-east-1'
        client.create_bucket(Bucket=name, CreateBucketConfiguration={'LocationConstraint': 'sa-east-1'},
                             ObjectOwnership='BucketOwnerEnforced')
        client.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
            'BlockPublicAcls': True, 'IgnorePublicAcls': True,
            'BlockPublicPolicy': True, 'RestrictPublicBuckets': True})
        client.put_bucket_encryption(Bucket=name, ServerSideEncryptionConfiguration={
            'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
        client.put_bucket_versioning(Bucket=name, VersioningConfiguration={'Status': 'Enabled'})
        client.put_bucket_policy(Bucket=name, Policy=json.dumps({'Version': '2012-10-17', 'Statement': [{
            'Sid': 'DenyInsecureTransport', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
            'Resource': ['arn:aws:s3:::' + name, 'arn:aws:s3:::' + name + '/*'],
            'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}))
        config.write_text(json.dumps({'bucket': name, 'expected_bucket_owner': account}))
        os.chmod(config, 0o600)
        print(json.dumps({'external_storage_prepared': True, 'public_access_blocked': True}))
    except Exception as error:
        code = getattr(error, 'response', {}).get('Error', {}).get('Code', '')
        reason = 'aws_permission_denied' if code in ('AccessDenied', 'AccessDeniedException', 'UnauthorizedOperation') else 'external_storage_unavailable'
        print(json.dumps({'external_storage_prepared': False, 'reason': reason,
                          'no_backup_uploaded': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true', required=True)
    parser.add_argument('--config-root', type=Path,
                        help='Explicit private, approved schema040 backup target; backup stage only')
    parser.add_argument('--with-manifest', action='store_true', help='Use approved schema040 shared-snapshot helper')
    parser.add_argument('stage', choices=['backup', 'prepare-external', 'install-schedule'])
    args = parser.parse_args()
    try:
        verified_config = None
        if args.with_manifest and (args.config_root is None or args.stage != 'backup'):
            raise RuntimeError('consistent_export_requires_explicit_backup_root')
        if args.config_root is not None:
            if args.stage != 'backup':
                raise RuntimeError('explicit_root_cannot_install_or_create_resources')
            verified_config = select_approved040_root(args.config_root)
        if args.stage == 'backup':
            backup(config=verified_config, with_manifest=args.with_manifest)
        else:
            {'prepare-external': prepare_external, 'install-schedule': install_schedule}[args.stage]()
    except Exception:
        raise SystemExit('Isolated backup unavailable; private configuration required.') from None
