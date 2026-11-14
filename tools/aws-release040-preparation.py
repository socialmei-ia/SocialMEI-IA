#!/usr/bin/env python3
"""Local preparation only. No AWS clients, subprocesses, deploy, transfer or apply mode."""
import argparse
from decimal import Decimal
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRICE_URL = 'https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/sa-east-1/index.csv'
TARGETS = ('t3.medium', 't3a.medium')
REQUIRED = (
    'architecture_x86_64_verified', 'ebs_root_verified', 'all_state_volumes_preserved',
    'target_offered_in_current_az', 'ena_and_hvm_verified', 'no_unmanaged_autoscaling_controller',
    'elastic_ip_or_dns_rollback_verified', 'external_backup_restoration_verified',
    'waha_n8n_sessions_and_private_mounts_preserved', 'writers_and_responders_pause_plan_reviewed',
    'autostart_and_single_responder_recovery_reviewed', 'rollback_original_instance_type_reviewed',
)


def permission_matrix():
    return {
        'sts_identity': {'status': 'previous_authentication_documented', 'not_an_admin_grant': True},
        'ec2:DescribeInstances': {'status': 'previous_denial_documented', 'retry_without_grant_change': False},
        'ec2:DescribeInstanceTypes': {'status': 'denied_in_single_readonly_probe',
                                     'error_code': 'UnauthorizedOperation', 'sdk_retries': 0},
        's3:ListAllMyBuckets': {'status': 'previous_denial_summarized', 'required_for_prefix_backup': False},
        's3:CreateBucket': {'status': 'previous_denial_summarized', 'retry_without_grant_change': False},
        'ec2_other_describe_and_s3_configuration': {
            'status': 'not_individually_proven',
            'reason': 'Earlier sequential calls can stop at the first denial; do not infer blanket denial.'},
        'pricing_catalog': {'status': 'public_aws_catalog_available_without_account_credentials'},
        'billing_discounts_and_credits': {'status': 'not_verified', 'cost_explorer_not_called': True},
    }


def quote_prices(data):
    if data.get('source') != PRICE_URL:
        raise ValueError('official_price_source_required')
    rates = data.get('rates', {})
    result = {}
    for kind in ('t3.small', *TARGETS):
        row = rates[kind]
        if (row.get('Instance Type') != kind or row.get('Operating System') != 'Linux'
                or row.get('Tenancy') != 'Shared' or row.get('Location') != 'South America (Sao Paulo)'
                or row.get('vCPU') != '2' or row.get('Memory') != ('2 GiB' if kind == 't3.small' else '4 GiB')):
            raise ValueError('price_product_mismatch')
        hourly = Decimal(row['hourly_usd'])
        if not hourly.is_finite() or not 0 < hourly < 10:
            raise ValueError('invalid_rate')
        result[kind] = {'vcpu': 2, 'memory_gib': 2 if kind == 't3.small' else 4,
                        'hourly_usd': str(hourly), 'monthly_730_hours_usd': str(hourly * 730),
                        'effective_date': row.get('EffectiveDate')}
    for kind in TARGETS:
        delta = Decimal(result[kind]['monthly_730_hours_usd']) - Decimal(result['t3.small']['monthly_730_hours_usd'])
        result[kind]['increment_over_t3_small_usd'] = str(delta)
    return {'source': PRICE_URL, 'retrieved_at_utc': data.get('retrieved_at_utc'), 'rates': result,
            'excludes': ['EBS', 'snapshots', 'public IPv4', 'CPU surplus credits', 'S3 storage/requests',
                         'taxes', 'currency conversion', 'account discounts/credits']}


def preparation(inventory=None, prices=None, target='t3.medium'):
    if target not in TARGETS:
        raise ValueError('unreviewed_instance_type')
    inventory = inventory or {}
    # No arbitrary input fields, addresses, IDs, paths or credentials are emitted.
    checks = {key: inventory.get(key) is True for key in REQUIRED}
    original = inventory.get('instance_type')
    if original not in ('t3.small', 't3.medium', 't3a.medium'):
        original = 'unverified'
    checks['original_instance_type_verified'] = original != 'unverified'
    return {
        'mode': 'local_preparation_only', 'region': 'sa-east-1',
        'execution_supported': False, 'authorization_granted': False,
        'permission_evidence': permission_matrix(),
        's3': {'template': 'deploy/team/postgres-backup-bucket.cloudformation.json',
               'runtime_iam': 'deploy/team/postgres-backup-iam.example.json',
               'private': True, 'encryption': 'AES256', 'versioned': True,
               'retained_on_delete_or_replace': True, 'automatic_deletion_configured': False,
               'bootstrap_separate_from_runtime_role': True,
               'bootstrap_actions': ['s3:CreateBucket', 's3:PutBucketOwnershipControls',
                   's3:PutBucketPublicAccessBlock', 's3:PutEncryptionConfiguration',
                   's3:PutBucketVersioning', 's3:PutBucketPolicy', 's3:PutBucketTagging'],
               'bootstrap_actions_scope': 'S3 actions only; not proof of permission and not a CloudFormation grant',
               'cloudformation_review_path': ['cloudformation:ValidateTemplate', 'cloudformation:GetTemplateSummary',
                   'cloudformation:CreateChangeSet', 'cloudformation:DescribeChangeSet',
                   'cloudformation:ExecuteChangeSet', 'cloudformation:DescribeStacks'],
               'verification_actions': ['s3:GetBucketLocation', 's3:GetBucketOwnershipControls',
                   's3:GetBucketPublicAccessBlock', 's3:GetEncryptionConfiguration',
                   's3:GetBucketVersioning', 's3:GetBucketPolicyStatus'],
               'activation_gates': ['approved_unique_bucket_and_costs', 'bootstrap_admin_permission',
                   'private_properties_verified', 'runtime_prefix_policy_attached',
                   'explicit_real_data_transfer_authorization', 'version_pinned_readback_and_restore']},
        'resize': {'original_type': original, 'proposed_type': target, 'memory_gib': 4,
                   'preferred_same_family': target == 't3.medium', 'arm_images_not_approved': True,
                   'checks': checks, 'technical_gates_passed': all(checks.values()),
                   'blockers': [key for key, value in checks.items() if not value],
                   'separate_required_authorizations': ['budget', 'downtime_stop_start', 'any_new_EBS_snapshot',
                                                        'instance_attribute_change'],
                   'sequence': ['capture_private_instance_volumes_network_and_restart_manifest',
                       'verify_current_external_backup_and_approved_volume_recovery_point',
                       'pause_writers_and_single_responders_under_approved_maintenance',
                       'graceful_stop_no_force_no_terminate', 'change_only_existing_instance_type',
                       'start_and_verify_EBS_mounts_ENI_SG_IP_DNS_before_resume',
                       'verify_private_services_and_identity_without_enabling_new_responders',
                       'resume_existing_owners_once_and_measure_load'],
                   'rollback': ['approved_graceful_stop', 'restore_original_instance_type_only',
                       'start_same_instance_with_same_current_volumes_and_network',
                       'verify_mounts_sessions_queues_DNS_and_single_responder_before_resume'],
                   'forbidden': ['force_stop', 'terminate', 'detach_or_replace_volumes',
                       'restore_old_data_over_new_writes', 'change_database_connection',
                       'apply_migrations', 'rebuild_or_deploy_release', 'unapproved_DNS_or_EIP_change']},
        'prices': quote_prices(prices) if prices else {'verified': False},
        'owner_minimum_actions': ['approve_bucket_and_existing_backup_role',
            'grant_or_delegate_bucket_bootstrap_and_prefix_runtime_permissions',
            'grant_readonly_EC2_inventory_if_missing', 'confirm_billing_credits_and_resize_budget',
            'approve_maintenance_after_preservation_and_rollback_gates',
            'authorize_real_backup_transfer_and_restore_test_separately'],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, help='Private, reviewed technical checklist; never commit raw AWS config')
    parser.add_argument('--prices', type=Path, help='Sanitized public AWS pricing receipt')
    parser.add_argument('--target', choices=TARGETS, default='t3.medium')
    args = parser.parse_args(argv)
    try:
        inventory = json.loads(args.inventory.read_text(encoding='utf-8-sig')) if args.inventory else None
        prices = json.loads(args.prices.read_text(encoding='utf-8-sig')) if args.prices else None
        print(json.dumps(preparation(inventory, prices, args.target), indent=2))
    except Exception:
        raise SystemExit('local_preparation_failed_check_private_inputs') from None


if __name__ == '__main__':
    main()
