#!/usr/bin/env python3
"""Inspect a Team backup, or explicitly restore 033->035 into owned offline resources.

Never connects to the live database. --run creates only a temporary PostgreSQL
container/volume with network=none, using the existing private restore safeguards.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re


def load(name, filename):
    path = Path(__file__).with_name(filename)
    if not path.is_file() or path.is_symlink():
        raise RuntimeError('helper_de_release_ausente')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = load('release_restore_safety', 'team-v33-restore-rehearsal.py')
profile = load('release_restore_profile', 'team-release-profile.py')


def stage_source(name, expected_sha):
    legacy.require(re.fullmatch(r'[0-9a-f]{40}', expected_sha) is not None, 'sha_invalido')
    legacy.require(name == 'team-v33-' + expected_sha[:12], 'stage_invalido')
    folder = legacy.BACKUPS / name
    legacy.private_dir(legacy.BACKUPS)
    legacy.private_dir(folder)
    legacy.regular_private(folder / 'stage-receipt.json')
    receipt = json.loads((folder / 'stage-receipt.json').read_text())
    source = folder / 'source'
    legacy.require(source.is_dir() and not source.is_symlink(), 'fonte_stage_invalida')
    legacy.require(receipt.get('candidate_sha') == expected_sha
                   and receipt.get('stage_source') == str(source)
                   and receipt.get('stage_clean') is True
                   and receipt.get('checkout_original_preservado') is True
                   and receipt.get('deployment_executed') is False
                   and receipt.get('release_profile') == '035', 'recibo_stage_invalido')
    legacy.require(legacy.command(['git', '-C', str(source), 'rev-parse', 'HEAD']).strip() == expected_sha,
                   'fonte_stage_trocada')
    legacy.require(not legacy.command(['git', '-C', str(source), 'status', '--porcelain']).strip(),
                   'fonte_stage_modificada')
    files = sorted((source / 'database/migrations').glob('*.sql'))
    legacy.require(all(p.is_file() and not p.is_symlink() for p in files), 'migration_invalida')
    checked = profile.verify([p.name for p in files], lambda name: (source / 'database/migrations' / name).read_bytes())
    legacy.require(checked['profile'] == '035', 'perfil_035_obrigatorio')
    profile.rehearsal(receipt.get('migration_rehearsal'), expected_sha)
    return source, [p.name for p in files]


class ReleaseRestore(legacy.Rehearsal):
    def execute(self, backup, source, versions):
        self.start(backup / 'equipe.dump', source / 'database/migrations')
        legacy.docker('exec', self.name, 'pg_restore', '-U', 'restore_trial', '-d', 'restore_trial',
                      '--no-owner', '--no-privileges', '--single-transaction', '--exit-on-error',
                      '/backup/equipe.dump', timeout=270)
        baseline = legacy.json_query(self.name, legacy.LEDGER_QUERY)
        legacy.require(baseline == versions[:33], 'backup_deve_conter_ledger_033_exato')
        before = legacy.restore_sql(legacy.json_query(self.name, legacy.COUNTS_QUERY))
        legacy.require('schema_migrations' in before and len(before) >= 10, 'backup_incompleto')
        legacy.require(not {'agenda_reminders', 'wa_human_replies'}.intersection(before),
                       'backup_033_com_schema_divergente')
        steps = "BEGIN; SET LOCAL lock_timeout='5s'; SET LOCAL statement_timeout='90s';\n"
        for name in versions[33:]:
            steps += (source / 'database/migrations' / name).read_text() + '\n'
            steps += "INSERT INTO socialmei.schema_migrations(version) VALUES ('" + name + "');\n"
        steps += 'COMMIT;\n'
        legacy.docker('exec', '-i', self.name, 'psql', '-X', '-U', 'restore_trial', '-d', 'restore_trial',
                      '-v', 'ON_ERROR_STOP=1', '-q', input_text=steps, timeout=140)
        legacy.require(legacy.json_query(self.name, legacy.LEDGER_QUERY) == versions, 'ledger_035_invalido')
        after = legacy.restore_sql(legacy.json_query(self.name, legacy.COUNTS_QUERY))
        legacy.require(all(after.get(k) == v for k, v in before.items() if k != 'schema_migrations'),
                       'contagens_originais_alteradas')
        legacy.require(after.get('agenda_reminders') == 0 and after.get('wa_human_replies') == 0,
                       'novas_tabelas_incompativeis')
        return {'restore_verified': True, 'migration_ledger': 35, 'original_rowcounts_preserved': True,
                'original_rowcount_fingerprint': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['team'], required=True)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--stage', required=True)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    report = {'profile': '035', 'restore_verified': False, 'production_modified': False,
              'provider_messages_sent': False, 'source_sha': args.expected_sha}
    trial = None
    try:
        source, versions = stage_source(args.stage, args.expected_sha)
        backup = legacy.backup_receipt(args.backup)
        report['backup_sha256'] = legacy.checksum(backup / 'equipe.dump')
        if args.run:
            legacy.disk_memory_preflight((backup / 'equipe.dump').stat().st_size)
            trial = ReleaseRestore()
            report.update(trial.execute(backup, source, versions))
        else:
            report['mode'] = 'inspection_only'
    except Exception:
        report['error_code'] = 'release_restore_blocked_details_suppressed'
    finally:
        if trial is not None:
            try:
                report['isolated_cleanup_verified'] = not trial.cleanup()
            except Exception:
                report['isolated_cleanup_verified'] = False
            if report['isolated_cleanup_verified'] is not True:
                report['owned_resources_for_cleanup'] = [trial.name, trial.volume]
    print(json.dumps(report, indent=2))
    if 'error_code' in report or (args.run and (not report['restore_verified'] or not report.get('isolated_cleanup_verified'))):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
