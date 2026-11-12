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

ROOT = Path('/home/ubuntu/.socialmei-postgres-relocation-20261112')
NAME = 'socialmei-postgres-relocation-20261112'


def backup():
    config = json.loads((ROOT / 'destination.private.json').read_text())
    if shutil.disk_usage(ROOT).free < 2 * 1024**3:
        raise RuntimeError('insufficient_backup_disk_space')
    folder = ROOT / 'backups'
    folder.mkdir(mode=0o700, exist_ok=True)
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
    s3_config = ROOT / 's3-backup.private.json'
    if s3_config.exists():
        import boto3
        storage = json.loads(s3_config.read_text())
        client = boto3.client('s3', region_name='sa-east-1')
        key = 'postgres-relocation/' + path.name
        client.upload_file(str(path), storage['bucket'], key, ExtraArgs={
            'ServerSideEncryption': 'AES256', 'Metadata': {'sha256': receipt['sha256']}})
        obj = client.head_object(Bucket=storage['bucket'], Key=key)
        body = client.get_object(Bucket=storage['bucket'], Key=key)['Body']
        remote_hash = hashlib.sha256()
        try:
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                remote_hash.update(chunk)
        finally:
            body.close()
        receipt['external_uploaded'] = (obj['ContentLength'] == receipt['bytes']
            and remote_hash.hexdigest() == receipt['sha256'])
        if not receipt['external_uploaded']:
            raise RuntimeError('external_backup_readback_invalid')
    receipt_path = path.with_suffix('.json')
    receipt_path.write_text(json.dumps(receipt, indent=2))
    os.chmod(receipt_path, 0o600)
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
        config.write_text(json.dumps({'bucket': name}))
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
