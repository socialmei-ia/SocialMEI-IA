"""Security boundaries of an unapplied IAM example; never calls AWS."""
import json
from pathlib import Path
import unittest

POLICY = Path(__file__).resolve().parents[1] / 'deploy/team/postgres-backup-iam.example.json'


class BackupIAMProposalTests(unittest.TestCase):
    def test_only_approved_prefix_and_nondestructive_backup_actions(self):
        statements = json.loads(POLICY.read_text())['Statement']
        allowed = {'s3:ListBucket', 's3:PutObject', 's3:GetObject',
                   's3:GetObjectVersion', 's3:GetBucketVersioning', 's3:GetEncryptionConfiguration',
                   's3:GetBucketPublicAccessBlock', 's3:GetBucketOwnershipControls'}
        found = set()
        for statement in statements:
            actions = statement['Action']
            actions = [actions] if isinstance(actions, str) else actions
            found.update(actions)
            self.assertEqual(statement['Effect'], 'Allow')
            self.assertTrue(set(actions) <= allowed)
            resource = statement['Resource']
            self.assertTrue(resource.startswith('arn:aws:s3:::REPLACE_WITH_APPROVED_BUCKET'))
            if set(actions) <= {'s3:GetBucketVersioning', 's3:GetEncryptionConfiguration',
                                's3:GetBucketPublicAccessBlock', 's3:GetBucketOwnershipControls'}:
                self.assertEqual(resource, 'arn:aws:s3:::REPLACE_WITH_APPROVED_BUCKET')
            elif 's3:ListBucket' not in actions:
                self.assertTrue(resource.endswith('/postgres-relocation/*'))
            else:
                self.assertEqual(statement['Condition']['StringLike']['s3:prefix'],
                                 ['postgres-relocation', 'postgres-relocation/*'])
        self.assertEqual(found, allowed)

    def test_every_request_requires_tls_and_no_creation_or_deletion_is_granted(self):
        statements = json.loads(POLICY.read_text())['Statement']
        for statement in statements:
            self.assertEqual(statement['Condition']['Bool']['aws:SecureTransport'], 'true')
            self.assertNotIn('Delete', str(statement['Action']))
            self.assertNotIn('Create', str(statement['Action']))


if __name__ == '__main__':
    unittest.main()
