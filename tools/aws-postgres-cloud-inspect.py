#!/usr/bin/env python3
"""Read-only AWS capacity/security/backup discovery with sanitized errors."""
import json
from pathlib import Path
import boto3


def inspect():
    result = {}
    session = boto3.Session(region_name='sa-east-1')
    try:
        ec2 = session.client('ec2')
        instances = ec2.describe_instances(Filters=[{'Name': 'ip-address', 'Values': ['54.94.213.7']}])
        instance = instances['Reservations'][0]['Instances'][0]
        result['ec2'] = {key: instance.get(key) for key in ('InstanceType', 'Monitoring', 'EbsOptimized')}
        volumes = [x['Ebs']['VolumeId'] for x in instance['BlockDeviceMappings'] if 'Ebs' in x]
        result['volumes'] = [{k: v.get(k) for k in ('Size', 'VolumeType', 'Iops', 'Throughput', 'Encrypted')}
                              for v in ec2.describe_volumes(VolumeIds=volumes)['Volumes']]
        groups = ec2.describe_security_groups(GroupIds=[g['GroupId'] for g in instance['SecurityGroups']])
        result['security_groups'] = [{
            'postgres_public': any(r.get('FromPort', 0) <= 5432 <= r.get('ToPort', 65535) and
                any(x.get('CidrIp') == '0.0.0.0/0' for x in r.get('IpRanges', [])) for r in g['IpPermissions']),
            'ingress_rule_count': len(g['IpPermissions'])} for g in groups['SecurityGroups']]
    except Exception as error:
        result['ec2'] = {'available': False, 'error_type': type(error).__name__}
    s3 = session.client('s3')
    try:
        buckets = s3.list_buckets()['Buckets']
        result['buckets'] = []
        for b in buckets:
            name = b['Name']
            row = {'name': name}
            for action, key in (('get_public_access_block', 'public_access'),
                                ('get_bucket_encryption', 'encryption'),
                                ('get_bucket_versioning', 'versioning')):
                try:
                    value = getattr(s3, action)(Bucket=name)
                    value.pop('ResponseMetadata', None)
                    row[key] = value
                except Exception:
                    row[key] = {'available': False}
            result['buckets'].append(row)
    except Exception as error:
        result['buckets'] = {'available': False, 'error_type': type(error).__name__}
    receipt = Path('/home/ubuntu/.socialmei-instagram-86cdd5b/backup/backup-receipt.json')
    if receipt.is_file():
        data = json.loads(receipt.read_text())
        # Only technical keys; never print backup source/configuration.
        result['backup_receipt'] = {k: v for k, v in data.items() if k in
            ('sha256', 'dump_sha256', 'dump_bytes', 'schema', 'counts', 'restored_counts',
             'created_at', 'backup_at', 'status', 'verified', 'restore_verified', 'tables', 'rows')}
        result['backup_receipt_keys'] = sorted(data)
    return result


if __name__ == '__main__':
    print(json.dumps(inspect(), indent=2))
