"""Offline safety/template/compatibility/pricing tests; no AWS or subprocess calls."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


prep = module('aws_prep', 'tools/aws-release040-preparation.py')
prices = module('aws_prices', 'tools/aws-public-instance-prices.py')


class AWSPreparationTests(unittest.TestCase):
    def test_bucket_is_private_encrypted_versioned_retained_without_deletion(self):
        template = json.loads((ROOT / 'deploy/team/postgres-backup-bucket.cloudformation.json').read_text())
        resources = template['Resources']
        self.assertEqual({r['Type'] for r in resources.values()}, {'AWS::S3::Bucket', 'AWS::S3::BucketPolicy'})
        bucket = resources['BackupBucket']
        self.assertEqual(bucket['DeletionPolicy'], 'Retain')
        self.assertEqual(bucket['UpdateReplacePolicy'], 'Retain')
        props = bucket['Properties']
        self.assertTrue(all(props['PublicAccessBlockConfiguration'].values()))
        self.assertEqual(props['VersioningConfiguration']['Status'], 'Enabled')
        self.assertEqual(props['OwnershipControls']['Rules'][0]['ObjectOwnership'], 'BucketOwnerEnforced')
        self.assertEqual(props['BucketEncryption']['ServerSideEncryptionConfiguration'][0]['ServerSideEncryptionByDefault']['SSEAlgorithm'], 'AES256')
        self.assertNotIn('LifecycleConfiguration', props)
        deny = resources['BackupBucketPolicy']['Properties']['PolicyDocument']['Statement'][0]
        self.assertEqual(deny['Effect'], 'Deny')
        self.assertEqual(deny['Condition']['Bool']['aws:SecureTransport'], 'false')

    def test_unknown_checks_never_become_authorized_or_ready(self):
        result = prep.preparation({'secret': 'private-credential', 'architecture_x86_64_verified': 'true'})
        self.assertFalse(result['execution_supported'])
        self.assertFalse(result['authorization_granted'])
        self.assertFalse(result['resize']['technical_gates_passed'])
        self.assertNotIn('private-credential', json.dumps(result))
        good = {key: True for key in prep.REQUIRED}
        self.assertFalse(prep.preparation(good)['resize']['technical_gates_passed'])
        good['instance_type'] = 't3.small'
        self.assertTrue(prep.preparation(good)['resize']['technical_gates_passed'])
        self.assertFalse(prep.preparation(good)['authorization_granted'])
        with self.assertRaises(ValueError):
            prep.preparation(good, target='t4g.medium')

    def test_exact_public_prices_and_no_false_billing_claims(self):
        data = json.loads((ROOT / 'docs/evidence/20261113-aws-instance-prices.json').read_text())
        quote = prep.quote_prices(data)
        self.assertEqual(quote['rates']['t3.medium']['monthly_730_hours_usd'], '49.0560000000')
        self.assertEqual(quote['rates']['t3a.medium']['monthly_730_hours_usd'], '44.1650000000')
        self.assertIn('account discounts/credits', quote['excludes'])
        with self.assertRaises(ValueError):
            prep.quote_prices({**data, 'source': 'unverified'})
        data['rates']['t3.medium']['hourly_usd'] = 'NaN'
        with self.assertRaises(ValueError):
            prep.quote_prices(data)

    def test_public_parser_ignores_reserved_and_wrong_os_and_currency(self):
        data = json.loads((ROOT / 'docs/evidence/20261113-aws-instance-prices.json').read_text())
        rows = []
        for row in data['rates'].values():
            rows.append({**row, 'PricePerUnit': row['hourly_usd'], 'TermType': 'OnDemand',
                         'Unit': 'Hrs', 'Currency': 'USD', 'CapacityStatus': 'Used', 'Pre Installed S/W': 'NA'})
        stream = io.StringIO()
        stream.write('"FormatVersion","v1.0"\n')
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerow({**rows[0], 'TermType': 'Reserved', 'PricePerUnit': '0.00001'})
        writer.writerow({**rows[0], 'Currency': 'BRL', 'PricePerUnit': '0.00001'})
        writer.writerows(rows)
        stream.seek(0)
        result = prices.parse(stream)
        self.assertEqual(result['t3.small']['hourly_usd'], '0.0336000000')
        with self.assertRaises(ValueError):
            prices.parse(io.StringIO('no header'))

    def test_permission_denial_is_not_extrapolated_to_untried_actions(self):
        matrix = prep.permission_matrix()
        self.assertEqual(matrix['ec2:DescribeInstances']['status'], 'previous_denial_documented')
        self.assertFalse(matrix['ec2:DescribeInstances']['retry_without_grant_change'])
        self.assertEqual(matrix['ec2_other_describe_and_s3_configuration']['status'], 'not_individually_proven')
        self.assertEqual(matrix['ec2:DescribeInstanceTypes']['error_code'], 'UnauthorizedOperation')

    def test_resize_policy_does_not_grant_arbitrary_instance_attribute_changes(self):
        policy = json.loads((ROOT / 'deploy/team/ec2-resize-iam.example.json').read_text())
        modify = next(row for row in policy['Statement'] if row['Action'] == 'ec2:ModifyInstanceAttribute')
        self.assertEqual(set(modify['Condition']['StringEquals']['ec2:Attribute/InstanceType']),
                         {'t3.small', 't3.medium', 't3a.medium'})
        self.assertNotIn('*', modify['Resource'])
        control = next(row for row in policy['Statement'] if isinstance(row['Action'], list))
        self.assertEqual(set(control['Action']), {'ec2:StopInstances', 'ec2:StartInstances'})


if __name__ == '__main__':
    unittest.main()
