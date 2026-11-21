"""Plan local retention only. Never deletes archives or contacts external storage.

Deletion needs a separate approved executor after offsite restore evidence.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path


def checksum(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def retention(folder, now=None):
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('private_backup_directory_required')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('aware_timestamp_required')
    records = []; blocked = []
    for path in sorted(folder.glob('destination-*.json')):
        if path.name.endswith(('.external.private.json', '.restore.private.json')):
            continue
        dump = path.with_suffix('.dump')
        try:
            if path.is_symlink() or dump.is_symlink() or not dump.is_file():
                raise ValueError('unsafe_artifact')
            receipt = json.loads(path.read_text())
            stamp = datetime.strptime(receipt['created_at_utc'][:16], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            if (receipt.get('database') != 'socialmei_candidate040_20261114'
                    or receipt.get('schema') != 40 or receipt.get('current_production_backup') is not True
                    or receipt.get('metadata_verified_before_export') is not True
                    or receipt.get('archive_index_verified') is not True
                    or receipt.get('bytes') != dump.stat().st_size
                    or receipt.get('sha256') != checksum(dump) or stamp > now):
                raise ValueError('unverified_backup')
            records.append((stamp, path, receipt))
        except (OSError, ValueError, TypeError, KeyError):
            blocked.append({'receipt': path.name, 'action': 'preserve_unverified'})
    records.sort(key=lambda row: (row[0], row[1].name), reverse=True)
    keep = set(path.name for _, path, _ in records[:24])
    days = set(); weeks = set()
    for stamp, path, _ in records:
        day = stamp.date(); week = stamp.isocalendar()[:2]
        if now - stamp <= timedelta(days=14) and day not in days:
            keep.add(path.name); days.add(day)
        if now - stamp <= timedelta(weeks=8) and week not in weeks:
            keep.add(path.name); weeks.add(week)
    rows = []
    for stamp, path, receipt in records:
        # Never release the only independent recovery copy on a boolean alone.
        proof = path.with_suffix('.restore.private.json')
        restored = False
        if proof.is_file() and not proof.is_symlink():
            try:
                evidence = json.loads(proof.read_text())
                restored = (evidence.get('sha256') == receipt['sha256']
                            and evidence.get('independent_restore_equal') is True
                            and evidence.get('comparison', {}).get('equal') is True
                            and evidence.get('external_version_id') == receipt.get('external_version_id')
                            and isinstance(evidence.get('external_version_id'), str)
                            and bool(evidence['external_version_id']))
            except (OSError, ValueError, TypeError):
                pass
        external = receipt.get('external_uploaded') is True and restored
        action = 'keep_retention' if path.name in keep else (
            'eligible_after_approval' if external else 'keep_external_restore_unproven')
        rows.append({'receipt': path.name, 'dump_sha256': receipt['sha256'], 'bytes': receipt['bytes'],
                     'action': action})
    return {'mode': 'plan_only', 'files_deleted': 0,
            'policy': {'latest': 24, 'daily_days': 14, 'weekly_weeks': 8},
            'records': rows, 'blocked': blocked}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(retention(args.directory)))
