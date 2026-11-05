"""Pinned app-only a472/038 -> f280/038 release. Inspect unless explicitly authorized.

The approved038 runtime checks are reused; this entry point never runs a migrator
or restores production PostgreSQL. Recovery replaces only API/gateway images.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = sibling('product204_approved038', 'team-functional038-release.py')
legacy = runtime.legacy
profile = runtime.profile
require = runtime.require
BASE_SHA = 'a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510'
CANDIDATE_SHA = 'f2805c8a1549071010850090606c6a92f9d6ba7a'
BUNDLE_SHA256 = '5b682c41d76a002a574522d10405232eb4673216e0b8245e49274e84ab01ff34'
AUTHORIZATION = 'a472-038-to-f280-038-app-only'
JOURNAL = 'product204-state.json'
BACKUP_RECEIPT = 'product204-backup-receipt.json'
BASELINE_WINDOW = 'functional038-window-20261104T005701Z-17201648d4fb'
NAMES = runtime.NAMES
PROTECTED = runtime.PROTECTED
BASELINE_STATIC_FILES = tuple(dict.fromkeys(runtime.CANDIDATE_STATIC_FILES + (
    'relatorios-leitura.html',
    'scripts/auth-store.js',
    'scripts/v22-bootstrap.js',
    'scripts/v22-knowledge-reporting.js',
    'scripts/v22-report-access.js',
    'scripts/v22-whatsapp-readiness.js',
)))
CANDIDATE_STATIC_FILES = tuple(dict.fromkeys(BASELINE_STATIC_FILES + (
    'relatorios-leitura.html',
    'scripts/auth-store.js',
    'scripts/report-viewer-details.js',
    'scripts/v22-bootstrap.js',
    'scripts/v22-business-export.js',
    'scripts/v22-businesses.js',
    'scripts/v22-customer-reporting.js',
    'scripts/v22-finance-reporting.js',
    'scripts/v22-knowledge-reporting.js',
    'scripts/v22-product-reporting.js',
    'scripts/v22-report-access.js',
    'scripts/v22-sale-history.js',
    'scripts/v22-team-members.js',
    'scripts/v22-whatsapp-readiness.js',
    'scripts/v22-workspace-audit.js',
    'styles/v22-businesses.css',
    'styles/v22-team-members.css',
)))

# A private import gives this release its own immutable runtime configuration.
# Only the baseline ledger callback changes: both ends require exact038.
runtime.BASE_SHA = BASE_SHA
runtime.CANDIDATE_SHA = CANDIDATE_SHA
runtime.BUNDLE_SHA256 = BUNDLE_SHA256
runtime.JOURNAL = JOURNAL
runtime.CANDIDATE_STATIC_FILES = CANDIDATE_STATIC_FILES
runtime.ledger035 = runtime.ledger038

fingerprint = runtime.fingerprint
runtime_fingerprint = runtime.runtime_fingerprint
protected_fingerprint = runtime.protected_fingerprint
mount_fingerprints = runtime.mount_fingerprints
verify_private_archive = runtime.verify_private_archive
private_file = runtime.private_file
approved_context = runtime.context
overlay = runtime.overlay
allowed_model = runtime.allowed_model
image_for = runtime.image_for
runtime_matches = runtime.runtime_matches
ledger038 = runtime.ledger038
capacity_gate = runtime.capacity_gate
source_gate = runtime.source_gate
read_bundle038 = runtime.read_bundle038
inputs_unchanged = runtime.inputs_unchanged
fresh_backup = runtime.fresh_backup
no_external_senders = runtime.no_external_senders
write_journal = runtime.write_journal
recover_plans = runtime.recover_plans
capture_candidate = runtime.capture_candidate
rollback_services = runtime.rollback_services
overlay_file = runtime.overlay_file


def context(container):
    """Accept the exact already-published038 overlay, never arbitrary private files."""
    try:
        return approved_context(container)
    except legacy.Blocked as error:
        require(str(error) == 'compose_fora_do_escopo', 'contexto_compose_invalido')
    labels = container['Config']['Labels']
    service = labels.get('com.docker.compose.service')
    require(service in NAMES, 'overlay_baseline_servico_diverge')
    wd = Path(labels['com.docker.compose.project.working_dir']).resolve()
    env = Path(labels['com.docker.compose.project.environment_file'])
    paths = [Path(v) for v in labels['com.docker.compose.project.config_files'].split(',') if v]
    folder = legacy.PRIVATE / BASELINE_WINDOW
    require(folder.is_dir() and not folder.is_symlink() and folder.resolve() == folder
            and folder.stat().st_uid == 0 and stat.S_IMODE(folder.stat().st_mode) == 0o700,
            'overlay_baseline_pasta_privada_invalida')
    overlay_path = folder / (service + '.candidate.compose.json')
    private_file(overlay_path)
    outside = [p for p in paths if not (p.resolve().is_relative_to(legacy.ROOT.resolve())
                                      or p.resolve().is_relative_to(legacy.BACKUPS.resolve()))]
    require(outside == [overlay_path] and paths[-1] == overlay_path,
            'overlay_baseline_fora_do_escopo')
    expected = {'image': legacy.image_tags(BASE_SHA)[service]}
    if service == 'team-api':
        expected['environment'] = {'SOCIALMEI_RELEASE_SHA': BASE_SHA}
    require(json.loads(overlay_path.read_text()) == {'services': {service: expected}},
            'overlay_baseline_conteudo_diverge')
    journal = json.loads(private_file(folder / 'functional038-state.json').read_text())
    require(journal.get('source_sha') == BASE_SHA
            and journal.get('baseline_sha') == '266e59b6a766c07f60c83b7b3053b33fc91cc135'
            and journal.get('bundle_sha256') == '43f5df836e3b49e4e99a5a01f0d243108f5310be4cd8e2d7d68a59d28afcac2a'
            and journal.get('phase') == 'published038'
            and journal.get('candidate_runtime', {}).get(service) == runtime_fingerprint(container),
            'overlay_baseline_journal_diverge')
    command = ['docker', '--host=unix:///var/run/docker.sock', 'compose',
               '-p', 'socialmei-team', '--env-file', str(env)]
    for path in paths:
        command += ['-f', str(path)]
    return wd, command, {str(p): legacy.digest_file(p) for p in [env, *paths]}


runtime.context = context


def preflight(source, bundle):
    plans, protected = runtime.preflight(source, bundle)
    no_external_senders(plans)
    return plans, protected


def backup_gate(folder, plans, *, fresh=True):
    require(folder.is_absolute() and folder == folder.resolve() and folder.parent == legacy.PRIVATE
            and folder.is_dir() and not folder.is_symlink() and folder.stat().st_uid == 0
            and stat.S_IMODE(folder.stat().st_mode) == 0o700, 'backup_privado_invalido')
    receipt = json.loads(private_file(folder / BACKUP_RECEIPT).read_text())
    require(receipt.get('source_sha') == CANDIDATE_SHA and receipt.get('baseline_sha') == BASE_SHA
            and receipt.get('release_profile') == '038', 'recibo_backup_divergente')
    require(not fresh or 0 <= time.time() - receipt.get('captured_unix', 0) <= 900, 'backup_nao_fresco')
    required = {'postgres.dump', 'images-before.tar', 'private-config.tar', 'restore038.json'}
    hashes = receipt.get('sha256', {})
    require(required <= set(hashes), 'backup_incompleto')
    for name, digest in hashes.items():
        require(Path(name).name == name and name not in ('.', '..'), 'nome_backup_invalido')
        require(legacy.digest_file(private_file(folder / name)) == digest, 'backup_digest_diverge')
    require(not fresh or 0 <= time.time() - (folder / 'postgres.dump').stat().st_mtime <= 900,
            'dump_nao_fresco')
    restore = json.loads(private_file(folder / 'restore038.json').read_text())
    require(restore.get('backup_sha256') == hashes['postgres.dump']
            and restore.get('ledger') == sorted(profile.MIGRATIONS038)
            and restore.get('restore_verified') is True and restore.get('isolated') is True
            and restore.get('migrations_executed') is False
            and restore.get('production_runtime_changed') is False,
            'restore_038_nao_comprovado')
    groups = ['columns', 'constraint_properties', 'constraints', 'environment', 'functions',
              'indexes', 'schemas', 'sequences', 'tables', 'triggers', 'views']
    require(restore.get('fingerprints_match') is True
            and restore.get('schema_and_constraints_match') is True
            and restore.get('sequence_states_match') is True
            and restore.get('accounts_memberships_match') is True
            and restore.get('table_count') == 74
            and isinstance(restore.get('metadata_groups'), list)
            and sorted(restore['metadata_groups']) == groups,
            'restore_038_dados_schema_constraints_nao_comprovados')
    require(receipt.get('runtime_fingerprints') == {
        s: runtime_fingerprint(p['container']) for s, p in plans.items()}, 'backup_runtime_diverge')
    require(receipt.get('mount_fingerprints') == {
        s: p['mount_fingerprints'] for s, p in plans.items()}, 'backup_mounts_divergem')
    verify_private_archive(folder / 'private-config.tar', plans)
    images = {s: {'tag': p['container']['Config']['Image'], 'image_id': p['container']['Image']}
              for s, p in plans.items()}
    sibling('product204_rollback_import', 'team-functional038-rollback-images.py').verify_archive_config_digests(
        folder / 'images-before.tar', images, BASE_SHA, 'bundle')
    return receipt


def publish_services(source, plans, protected, backup, receipt, state):
    """Publish two images; schema remains038 on success and every failure path."""
    try:
        ledger038()
        fresh_backup(receipt, backup)
        state['phase'] = 'before_services'
        write_journal(backup, state)
        for service, plan in plans.items():
            inputs_unchanged(plans, protected)
            ledger038()
            require(runtime_fingerprint(legacy.inspect(NAMES[service])) == runtime_fingerprint(plan['container']),
                    'runtime_alterado_antes_do_corte')
            image_for(plan['container'], BASE_SHA)
            require(json.loads(legacy.docker('image', 'inspect', legacy.image_tags(CANDIDATE_SHA)[service]))[0]['Id']
                    == plan['candidate_image_id'], 'imagem_candidata_alterada_antes_do_corte')
            path = overlay_file(backup, service)
            command = plan['command'] + ['-f', str(path)]
            allowed_model(plan['before'], legacy.render(command, plan['wd']), service)
            state['attempted'].append(service)
            write_journal(backup, state)
            legacy.run(command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', service],
                       cwd=plan['wd'], timeout=180)
            legacy.wait_service(service)
            capture_candidate(service, plan, state, backup)
            inputs_unchanged(plans, protected)
            ledger038()
        legacy.public_smoke(expected_files={p: legacy.digest_file(source / 'frontend' / p)
                                           for p in CANDIDATE_STATIC_FILES})
        state['phase'] = 'published_app_only038'
        write_journal(backup, state)
    except Exception:
        ledger038()
        state['phase'] = 'app_only_recovery_required'
        write_journal(backup, state)
        rollback_services(plans, protected, backup, receipt, state)
        raise


def operate(source, bundle, backup=None, apply=False, authorization=None):
    source_gate(source)
    plans, protected = preflight(source, bundle)
    if not apply:
        return {'action': 'inspect_passed', 'source_sha': CANDIDATE_SHA,
                'baseline_sha': BASE_SHA, 'migrations_executed': False,
                'production_changed': False, 'backup_verified': False, 'deployment_ready': False}
    require(authorization == AUTHORIZATION, 'autorizacao_operacional_explicita_obrigatoria')
    require(os.geteuid() == 0 and backup is not None, 'apply_exige_root_e_backup')
    with open('/run/lock/socialmei-wa-pilot-release.lock', 'a') as lock:
        legacy.fcntl.flock(lock, legacy.fcntl.LOCK_EX | legacy.fcntl.LOCK_NB)
        source_gate(source)
        plans, protected = preflight(source, bundle)
        receipt = backup_gate(backup, plans)
        require(not (backup / JOURNAL).exists(), 'janela_ja_iniciada_use_recuperacao')
        inputs_unchanged(plans, protected)
        state = {'source_sha': CANDIDATE_SHA, 'baseline_sha': BASE_SHA, 'bundle_sha256': BUNDLE_SHA256,
                 'backup_receipt_sha256': legacy.digest_file(backup / BACKUP_RECEIPT),
                 'phase': 'before_services', 'plans': plans,
                 'backup_plans': copy.deepcopy(plans), 'protected': protected,
                 'attempted': [], 'rolled_back_services': [], 'rolled_back_runtime': {},
                 'candidate_runtime': {}, 'migrations_executed': False,
                 'old_files': {p: hashlib.sha256(legacy.https('/frontend/' + p, 200)).hexdigest()
                               for p in BASELINE_STATIC_FILES}}
        write_journal(backup, state)
        publish_services(source, plans, protected, backup, receipt, state)
    return {'action': 'api_gateway_published_schema038', 'source_sha': CANDIDATE_SHA,
            'migrations_executed': False, 'database_downgraded': False, 'provider_messages_sent': False}


def rollback(source, bundle, backup, authorization=None):
    require(authorization == AUTHORIZATION, 'autorizacao_operacional_explicita_obrigatoria')
    require(os.geteuid() == 0, 'rollback_exige_root')
    source_gate(source)
    read_bundle038(bundle)
    with open('/run/lock/socialmei-wa-pilot-release.lock', 'a') as lock:
        legacy.fcntl.flock(lock, legacy.fcntl.LOCK_EX | legacy.fcntl.LOCK_NB)
        state = json.loads(private_file(backup / JOURNAL).read_text())
        require(state.get('source_sha') == CANDIDATE_SHA and state.get('baseline_sha') == BASE_SHA
                and state.get('bundle_sha256') == BUNDLE_SHA256
                and state.get('migrations_executed') is False
                and state.get('backup_receipt_sha256') == legacy.digest_file(
                    private_file(backup / BACKUP_RECEIPT)), 'journal_nao_corresponde_a_janela')
        require(state.get('phase') in ('before_services', 'published_app_only038',
                'app_only_recovery_required'), 'janela_nao_recuperavel')
        plans = recover_plans(state)
        original = recover_plans({'plans': state['backup_plans']})
        receipt = backup_gate(backup, original, fresh=False)
        ledger038()
        require(set(state.get('attempted', [])) <= set(NAMES)
                and len(state['attempted']) == len(set(state['attempted']))
                and set(state.get('rolled_back_services', [])) <= set(state['attempted']),
                'journal_tentativas_divergem')
        no_external_senders(plans)
        rollback_services(plans, state['protected'], backup, receipt, state)
    return {'action': 'rolled_back_schema038_retained', 'source_sha': BASE_SHA,
            'migrations_executed': False, 'database_downgraded': False,
            'provider_messages_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--backup', type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true')
    action.add_argument('--rollback', action='store_true')
    parser.add_argument('--authorization')
    args = parser.parse_args()
    try:
        if args.rollback:
            require(args.backup is not None, 'rollback_exige_backup')
            result = rollback(args.source, args.bundle, args.backup, args.authorization)
        else:
            result = operate(args.source, args.bundle, args.backup, args.apply, args.authorization)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        code = str(error) if isinstance(error, legacy.Blocked) and re.fullmatch('[a-z0-9_]+', str(error)) else 'operacao_bloqueada_detalhes_privados'
        print(json.dumps({'status': 'NO-GO', 'code': code}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
