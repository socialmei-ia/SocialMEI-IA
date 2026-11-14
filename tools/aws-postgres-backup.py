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
from urllib.parse import urlsplit

ROOT = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
NAME = 'socialmei-postgres-relocation-20261112'


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
    """Upload only a verified historical artifact; resume uncertain PUT by HEAD.

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
            or receipt.get('source') != 'isolated_historical_destination'
            or receipt.get('current_production_backup') is not False):
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


def backup():
    config = json.loads((ROOT / 'destination.private.json').read_text())
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
    receipt = {'created_at_utc': stamp, 'dump_path': str(path), 'bytes': path.stat().st_size,
               'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'source': 'isolated_historical_destination', 'current_production_backup': False,
               'external_uploaded': False, 'archive_index_verified': True, 'cutover_authorized': False}
    receipt['external_upload_requested'] = storage is not None
    receipt_path = path.with_suffix('.json')
    _private_checkpoint(receipt_path, receipt)
    if storage is not None:
        receipt = upload_external_versioned(path, receipt, storage, client)
    _private_checkpoint(receipt_path, receipt)
    print(json.dumps(receipt))


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
    parser.add_argument('stage', choices=['backup', 'prepare-external', 'install-schedule'])
    args = parser.parse_args()
    try:
        {'backup': backup, 'prepare-external': prepare_external, 'install-schedule': install_schedule}[args.stage]()
    except Exception:
        raise SystemExit('Isolated backup unavailable; private configuration required.') from None
