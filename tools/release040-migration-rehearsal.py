#!/usr/bin/env python3
"""Opt-in 039 -> 040 rehearsal on disposable, network-none PostgreSQL 16 only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('release040_profile', ROOT / 'tools/team-release-profile.py')
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)

SEED = """
INSERT INTO socialmei.workspaces(id,slug,nome) VALUES
 (1001,'identity-rehearsal-a','Synthetic A'),(1002,'identity-rehearsal-b','Synthetic B');
INSERT INTO socialmei.users(id,email,nome) VALUES
 (2001,'identity-a@example.test','Synthetic A'),(2002,'identity-b@example.test','Synthetic B');
INSERT INTO socialmei.workspace_members(workspace_id,user_id,role) VALUES (1001,2001,'owner'),(1002,2002,'owner');
INSERT INTO socialmei.crm_clientes(id,workspace_id,nome) VALUES (3001,1001,'Synthetic client');
SELECT setval('socialmei.workspaces_id_seq',1002),setval('socialmei.users_id_seq',2002),setval('socialmei.crm_clientes_id_seq',3001);
"""

IDENTITY_SEED = """
INSERT INTO socialmei.auth_email_activation(user_id,email) VALUES(2001,'identity-a@example.test');
INSERT INTO socialmei.auth_identity_mail(id,purpose,user_id,email,token_hash)
 VALUES('00000000-0000-4000-8000-000000000001','verification',2001,'identity-a@example.test',repeat('a',64));
INSERT INTO socialmei.auth_identity_mail(id,purpose,workspace_id,created_by,email,role,token_hash)
 VALUES('00000000-0000-4000-8000-000000000002','invitation',1002,2002,'invite@example.test','viewer',repeat('b',64));
"""

CONTRACT = """
BEGIN;
SET LOCAL lock_timeout='3s'; SET LOCAL statement_timeout='15s';
CREATE FUNCTION pg_temp.expect_rejection(command text, expected text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE actual text;
BEGIN
 BEGIN EXECUTE command; EXCEPTION WHEN OTHERS THEN GET STACKED DIAGNOSTICS actual=RETURNED_SQLSTATE; END;
 IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'identity_constraint_rejection_missing: % expected %, got %',command,expected,actual; END IF;
END $$;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM socialmei.auth_email_activation) OR EXISTS(SELECT 1 FROM socialmei.auth_identity_mail)
 THEN RAISE EXCEPTION 'legacy_users_silently_activated'; END IF;
 IF (SELECT count(*) FROM pg_constraint WHERE conrelid IN ('socialmei.auth_email_activation'::regclass,'socialmei.auth_identity_mail'::regclass) AND contype='f' AND convalidated)<>4
 THEN RAISE EXCEPTION 'identity_fk_contract_invalid'; END IF;
 IF (SELECT count(*) FROM pg_indexes WHERE schemaname='socialmei' AND indexname IN ('ux_identity_verification_active','ux_identity_invitation_active','ix_identity_mail_pending'))<>3
 THEN RAISE EXCEPTION 'identity_partial_indexes_missing'; END IF;
END $$;
""" + IDENTITY_SEED + """
SELECT pg_temp.expect_rejection($q$INSERT INTO socialmei.auth_email_activation(user_id,email) VALUES(9999,'missing@example.test')$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET purpose='invalid'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET status='invalid'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET role='owner' WHERE purpose='invitation'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET role=NULL WHERE purpose='invitation'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET workspace_id=1001 WHERE purpose='verification'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET user_id=NULL WHERE purpose='verification'$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET created_by=9999 WHERE purpose='invitation'$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET workspace_id=9999 WHERE purpose='invitation'$q$,'23503');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET expires_at=created_at$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET token_hash=repeat('X',64)$q$,'23514');
SELECT pg_temp.expect_rejection($q$UPDATE socialmei.auth_identity_mail SET token_hash=repeat('a',64) WHERE purpose='invitation'$q$,'23505');
SELECT pg_temp.expect_rejection($q$INSERT INTO socialmei.auth_identity_mail(id,purpose,user_id,email) VALUES('00000000-0000-4000-8000-000000000003','verification',2001,'identity-a@example.test')$q$,'23505');
SELECT pg_temp.expect_rejection($q$INSERT INTO socialmei.auth_identity_mail(id,purpose,workspace_id,created_by,email,role) VALUES('00000000-0000-4000-8000-000000000004','invitation',1002,2002,'invite@example.test','viewer')$q$,'23505');
UPDATE socialmei.auth_identity_mail SET status='sent' WHERE purpose='verification';
SELECT pg_temp.expect_rejection($q$INSERT INTO socialmei.auth_identity_mail(id,purpose,user_id,email) VALUES('00000000-0000-4000-8000-000000000003','verification',2001,'identity-a@example.test')$q$,'23505');
UPDATE socialmei.auth_identity_mail SET status='uncertain' WHERE purpose='verification';
INSERT INTO socialmei.auth_identity_mail(id,purpose,user_id,email)
 VALUES('00000000-0000-4000-8000-000000000003','verification',2001,'identity-a@example.test');
DELETE FROM socialmei.users WHERE id=2001;
DELETE FROM socialmei.workspaces WHERE id=1002;
DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM socialmei.auth_email_activation) OR EXISTS(SELECT 1 FROM socialmei.auth_identity_mail)
 THEN RAISE EXCEPTION 'identity_cascade_contract_invalid'; END IF;
END $$;
ROLLBACK;
"""


def run(binary, *args, data=None):
    result = subprocess.run([str(binary), *map(str, args)], input=data, capture_output=True,
                            timeout=120, cwd=ROOT)
    if result.returncode:
        phase = next((name for name in ('psql', 'pg_restore', 'pg_dump', 'pg_isready') if name in args),
                     'migrator' if '/workspace/tools/team_migrate.py' in args else 'command')
        raise RuntimeError('rehearsal_' + phase + '_failed')
    return result.stdout


def local_docker(endpoint):
    return endpoint == 'unix:///var/run/docker.sock' or bool(re.fullmatch(
        r'npipe:///+\./pipe/(?:docker_engine|dockerDesktopLinuxEngine)', str(endpoint)))


def canonical_expression(value):
    nested = 'CHECK ((((octet_length(text) >= 1) AND (octet_length(text) <= 1000)) AND (length(btrim(text)) > 0)))'
    if value == nested:
        return 'CHECK (((octet_length(text) >= 1) AND (octet_length(text) <= 1000) AND (length(btrim(text)) > 0)))'
    literal = r"'(?:[^']|'')*'::character varying"
    return re.sub(r'\(ARRAY\[(' + literal + r'(?:,\s*' + literal + r')*)\]\)::text\[\]',
                  lambda match: 'ARRAY[' + re.sub('(' + literal + ')', r'(\1)::text', match[1]) + ']', value)


def canonical_schema(value):
    for row in value.get('constraints') or []:
        row[2] = canonical_expression(row[2])
    for row in value.get('indexes') or []:
        row['indexdef'] = canonical_expression(row['indexdef'])
    return value


def workspace_path(root, value):
    target = (root / value).resolve()
    profile.require(target != root and target.is_relative_to(root), 'artifact_outside_workspace')
    return target


def manifest(root):
    folder = root / 'database/migrations'
    files = sorted(folder.rglob('*.sql'))
    profile.require(folder.is_dir() and not folder.is_symlink()
                    and all(not item.is_symlink() for item in files), 'migration_path_invalid')
    return profile.verify040([item.relative_to(folder).as_posix() for item in files],
                             lambda name: (folder / name).read_bytes())['migrations']


def options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--docker', default='docker')
    parser.add_argument('--api-image')
    parser.add_argument('--source-sha')
    parser.add_argument('--receipt')
    args = parser.parse_args(argv)
    if args.run:
        profile.require(re.fullmatch(r'[0-9a-f]{40}', args.source_sha or '')
                        and re.fullmatch(r'sha256:[0-9a-f]{64}', args.api_image or ''),
                        'exact_source_and_image_required')
    return args


def rehearse(args, root=ROOT):
    root = root.resolve()
    hashes = manifest(root)
    proof = dict(profile='040', baseline='039', source_migrations=hashes,
                 baseline_migrations=profile.MIGRATIONS039, production_data_used=False,
                 production_runtime_changed=False, provider_messages_sent=False)
    if not args.run:
        return dict(proof, mode='plan')
    profile.require(not os.environ.get('DOCKER_HOST') or local_docker(os.environ['DOCKER_HOST']),
                    'local_docker_required')
    docker = lambda *values, **kw: run(args.docker, *values, **kw)
    context = json.loads(docker('context', 'inspect'))
    profile.require(len(context) == 1 and local_docker(context[0]['Endpoints']['docker']['Host']),
                    'local_docker_required')
    images = json.loads(docker('image', 'inspect', args.api_image))
    profile.require(len(images) == 1 and images[0]['Id'] == args.api_image
                    and images[0]['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == args.source_sha,
                    'source_image_revision_mismatch')
    git = lambda *values: run('git', '-c', 'safe.directory=' + str(root), '-C', root, *values)
    profile.require(git('rev-parse', 'HEAD').decode().strip() == args.source_sha,
                    'source_checkout_revision_mismatch')
    profile.require(not git('status', '--porcelain=v1', '--untracked-files=all').strip(),
                    'clean_source_required')
    digest = lambda data: hashlib.sha256(data).hexdigest()
    for name, expected in profile.MIGRATIONS039.items():
        profile.require(digest(git('show', 'HEAD:database/migrations/' + name).replace(b'\r\n', b'\n')) == expected,
                        'original_migrations_changed')
    token = secrets.token_hex(6)
    artifact = workspace_path(root, '.preview/migration-rehearsal040-' + token)
    receipt = workspace_path(root, args.receipt or str(artifact / 'receipt.json'))
    profile.require(not receipt.exists(), 'receipt_already_exists')
    baseline = artifact / 'migrations039'
    baseline.mkdir(parents=True)
    for name in profile.MIGRATIONS039:
        (baseline / name).write_bytes((root / 'database/migrations' / name).read_bytes())
    containers = []
    label = 'socialmei.migration-rehearsal040=' + token
    name = 'socialmei-rehearsal040-' + token

    def sql(statement, database='rehearsal040'):
        return docker('exec', '-i', name, 'psql', '-X', '-U', 'rehearsal', '-d', database,
                      '-v', 'ON_ERROR_STOP=1', '-Atq', data=statement.encode()).decode().strip()

    def migrate(directory, database='rehearsal040'):
        docker('run', '--rm', '--label', label, '--network', 'container:' + name,
               '-v', str(root) + ':/workspace:ro', '-v', str(directory) + ':/migrations:ro',
               '-e', 'PYTHONPATH=/workspace/python-service', '-e', 'DATABASE_URL=',
               '-e', 'POSTGRES_PASSWORD=', '-e', 'POSTGRES_HOST=127.0.0.1',
               '-e', 'POSTGRES_PORT=5432', '-e', 'POSTGRES_USER=rehearsal',
               '-e', 'POSTGRES_DB=' + database,
               '-e', 'PGOPTIONS=-c lock_timeout=3s -c statement_timeout=30s',
               '--entrypoint', 'python', args.api_image, '/workspace/tools/team_migrate.py')

    def snapshot(tables, schema=False):
        if schema:
            names = ','.join("'" + table + "'" for table in tables)
            return canonical_schema(json.loads(sql("SELECT jsonb_build_object('columns',(SELECT jsonb_agg(to_jsonb(c) ORDER BY table_name,ordinal_position) FROM information_schema.columns c WHERE table_schema='socialmei' AND table_name IN (" + names + ")), 'constraints',(SELECT jsonb_agg(jsonb_build_array(t.relname,c.conname,pg_get_constraintdef(c.oid)) ORDER BY t.relname,c.conname) FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='socialmei' AND t.relname IN (" + names + ")), 'indexes',(SELECT jsonb_agg(to_jsonb(i) ORDER BY tablename,indexname) FROM pg_indexes i WHERE schemaname='socialmei' AND tablename IN (" + names + ")))::text;")))
        return {table: json.loads(sql('SELECT COALESCE(jsonb_agg(to_jsonb(t) ORDER BY to_jsonb(t)::text),\'[]\'::jsonb)::text FROM socialmei."' + table + '" t;')) for table in tables}

    def tables():
        return json.loads(sql("SELECT json_agg(tablename ORDER BY tablename) FROM pg_tables WHERE schemaname='socialmei' AND tablename<>'schema_migrations';"))

    def ledger():
        return json.loads(sql('SELECT json_agg(to_jsonb(t) ORDER BY version) FROM socialmei.schema_migrations t;'))

    def sequences():
        return sql("SELECT jsonb_agg(to_jsonb(s) ORDER BY sequencename)::text FROM pg_sequences s WHERE schemaname='socialmei';")

    def backup(filename):
        data = docker('exec', name, 'pg_dump', '-U', 'rehearsal', '-d', 'rehearsal040',
                      '-Fc', '--no-owner', '--no-privileges')
        profile.require(data.startswith(b'PGDMP'), 'backup_format_invalid')
        path = artifact / filename
        with path.open('xb') as stream:
            stream.write(data)
        profile.require(path.read_bytes() == data, 'backup_readback_mismatch')
        return data

    def restore(data):
        sql('DROP DATABASE rehearsal040;', 'postgres')
        sql('CREATE DATABASE rehearsal040;', 'postgres')
        docker('exec', '-i', name, 'pg_restore', '-U', 'rehearsal', '-d', 'rehearsal040',
               '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges', data=data)

    try:
        container = docker('run', '-d', '--name', name, '--label', label, '--network', 'none',
                           '-e', 'POSTGRES_USER=rehearsal', '-e', 'POSTGRES_DB=rehearsal040',
                           '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:16-alpine').decode().strip()
        profile.require(re.fullmatch(r'[0-9a-f]{64}', container), 'isolated_postgres_not_created')
        containers.append(container)
        for attempt in range(60):
            try:
                docker('exec', name, 'pg_isready', '-h', '127.0.0.1', '-U', 'rehearsal')
                break
            except RuntimeError:
                if attempt == 59:
                    raise
                time.sleep(.5)
        profile.require(sql("SELECT current_setting('server_version_num')::int/10000;") == '16',
                        'postgres_16_required')
        migrate(baseline)
        profile.require([row['version'] for row in ledger()] == list(profile.MIGRATIONS039), 'baseline_ledger_invalid')
        sql(SEED)
        old_tables = tables()
        before, old_schema, old_sequences, old_ledger = snapshot(old_tables), snapshot(old_tables, True), sequences(), ledger()
        dump = backup('synthetic039.dump')
        restore(dump)
        # Compare catalog structure to its restored baseline; pg_dump may normalize expressions.
        restored_schema = snapshot(old_tables, True)
        profile.require(snapshot(old_tables) == before and sequences() == old_sequences
                        and ledger() == old_ledger
                        and restored_schema == old_schema, 'baseline_restore_diverged')
        sql('CREATE DATABASE rehearsal_incompatible TEMPLATE rehearsal040;', 'postgres')
        sql('CREATE TABLE socialmei.auth_identity_mail(id UUID);', 'rehearsal_incompatible')
        rejected = False
        try:
            migrate(root / 'database/migrations', 'rehearsal_incompatible')
        except RuntimeError:
            rejected = True
        profile.require(rejected and sql("SELECT to_regclass('socialmei.auth_email_activation') IS NULL;", 'rehearsal_incompatible') == 't'
                        and sql('SELECT count(*) FROM socialmei.schema_migrations;', 'rehearsal_incompatible') == '39',
                        'incompatible_migration_not_atomic')
        migrate(root / 'database/migrations')
        profile.require(snapshot(old_tables) == before and snapshot(old_tables, True) == restored_schema
                        and sequences() == old_sequences and ledger()[:39] == old_ledger
                        and [row['version'] for row in ledger()] == list(hashes), 'migration_preservation_failed')
        sql(CONTRACT)
        sql(IDENTITY_SEED)
        upgraded_tables = tables()
        after, upgraded_schema, upgraded_sequences, applied = snapshot(upgraded_tables), snapshot(upgraded_tables, True), sequences(), ledger()
        migrate(root / 'database/migrations')
        sql('BEGIN; SET LOCAL lock_timeout=\'3s\'; SET LOCAL statement_timeout=\'15s\';\n'
            + (root / 'database/migrations/040_identity_activation.sql').read_text(encoding='utf-8') + '\nCOMMIT;')
        profile.require(snapshot(upgraded_tables) == after and ledger() == applied
                        and snapshot(upgraded_tables, True) == upgraded_schema, 'migration_reapply_changed_state')
        upgraded_dump = backup('synthetic040.dump')
        restore(upgraded_dump)
        profile.require(snapshot(upgraded_tables) == after and ledger() == applied
                        and snapshot(upgraded_tables, True) == upgraded_schema
                        and sequences() == upgraded_sequences, 'upgraded_restore_diverged')
        proof.update(source_sha=args.source_sha, source_dirty=False, api_image_id=args.api_image,
                     api_image_revision=args.source_sha, backup_sha256=digest(dump),
                     upgraded_backup_sha256=digest(upgraded_dump), format='socialmei-migration-rehearsal-v1')
        for key in ('isolated', 'disposable', 'restored_backup_verified', 'existing_data_preserved',
                    'migration_reapply_verified', 'constraints_verified', 'schema_contract_verified',
                    'original_migrations_unchanged', 'incompatible_state_rejected',
                    'backwards_compatible_reads_verified', 'sequences_preserved', 'upgraded_backup_restore_verified'):
            proof[key] = True
        proof['backwards_compatible_reads_scope'] = '039 complete original-table rows and catalog; old application binary not executed'
    finally:
        for container in reversed(containers):
            owned = json.loads(docker('inspect', container))
            profile.require(len(owned) == 1 and owned[0]['Config']['Labels'].get('socialmei.migration-rehearsal040') == token
                            and owned[0]['HostConfig']['NetworkMode'] == 'none', 'cleanup_target_not_owned')
            docker('rm', '-f', '-v', container)
    proof['isolated_cleanup_verified'] = True
    profile.require(manifest(root) == hashes and git('rev-parse', 'HEAD').decode().strip() == args.source_sha
                    and not git('status', '--porcelain=v1', '--untracked-files=all').strip(),
                    'source_changed_during_rehearsal')
    profile.rehearsal040(proof, args.source_sha)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(proof, stream, indent=2)
        stream.write('\n')
    return proof


if __name__ == '__main__':
    try:
        print(json.dumps(rehearse(options()), indent=2))
    except (RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error) if re.fullmatch(r'[a-z0-9_]+', str(error)) else 'rehearsal_failed_details_suppressed')
