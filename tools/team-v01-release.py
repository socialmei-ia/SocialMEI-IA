"""Pinned 266/035 API+gateway operator. Inspect by default; never runs migrations.

Apply requires an independently verified, fresh private backup/restore receipt.
Do not run apply without the responsible operator's deployment authorization.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
import tarfile
import time


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = sibling('v01_runtime', 'team-whatsapp-release.py')
profile = sibling('v01_profile', 'team-release-profile.py')
require = legacy.require
BASE_SHA = '266e59b6a766c07f60c83b7b3053b33fc91cc135'
CANDIDATE_SHA = 'baecbe1f7b7d2af0f3edc1f03b097f18ff5cc3ca'
NAMES = {'team-api': legacy.API, 'team-gateway': legacy.GATEWAY}
PROTECTED = (legacy.POSTGRES, legacy.WAHA, legacy.N8N)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def runtime_fingerprint(container):
    # Healthcheck timestamps and process counters change without a configuration change.
    return fingerprint({key: container.get(key) for key in
                        ('Id', 'Image', 'Config', 'HostConfig', 'Mounts', 'NetworkSettings')})


def protected_fingerprint(container):
    return fingerprint([runtime_fingerprint(container), container['State'].get('StartedAt'),
                        container.get('RestartCount'), container['State'].get('Running'),
                        container['State'].get('Status')])


def mount_fingerprints(container):
    result = {}
    for mount in container.get('Mounts', []):
        require(mount['Type'] == 'bind' and mount['RW'] is False, 'mount_privado_nao_readonly')
        root = Path(mount['Source'])
        require(root.is_absolute() and not root.is_symlink(), 'mount_origem_invalida')
        paths = [root, *sorted(root.rglob('*'))] if root.is_dir() else [root]
        require(len(paths) <= 20000, 'mount_grande_demais')
        rows = []
        for path in paths:
            require(not path.is_symlink() and (path.is_file() or path.is_dir()), 'mount_contem_link_ou_especial')
            info = path.stat()
            require(info.st_size <= 1024**3, 'mount_arquivo_grande_demais')
            rows.append([str(path.relative_to(root)), stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid,
                         legacy.digest_file(path) if path.is_file() else None])
        result[str(root)] = fingerprint(rows)
    return result


def verify_private_archive(archive_path, plans):
    expected = {}
    for plan in plans.values():
        for filename in plan['files']:
            path = Path(filename)
            expected['config/' + hashlib.sha256(str(path).encode()).hexdigest()] = path
        for filename in plan['mount_fingerprints']:
            root = Path(filename)
            prefix = 'mounts/' + hashlib.sha256(str(root).encode()).hexdigest() + '/'
            if root.is_file():
                expected[prefix + '__file__'] = root
            else:
                for path in root.rglob('*'):
                    require(not path.is_symlink(), 'backup_mount_link_proibido')
                    if path.is_file():
                        expected[prefix + path.relative_to(root).as_posix()] = path
    require(len(expected) <= 20000, 'backup_config_grande_demais')
    seen = set()
    with tarfile.open(archive_path) as archive:
        for member in archive:
            require(member.isfile() and member.name in expected and member.name not in seen,
                    'backup_config_conteudo_diverge')
            path = expected[member.name]
            info = path.stat()
            require(member.size == info.st_size and member.mode == stat.S_IMODE(info.st_mode)
                    and member.uid == info.st_uid and member.gid == info.st_gid,
                    'backup_config_metadados_divergem')
            with archive.extractfile(member) as stream:
                require(hashlib.file_digest(stream, 'sha256').hexdigest() == legacy.digest_file(path),
                        'backup_config_bytes_divergem')
            seen.add(member.name)
    require(seen == set(expected), 'backup_config_incompleto')


def private_file(path):
    require(path.is_file() and not path.is_symlink(), 'arquivo_privado_invalido')
    info = path.stat()
    require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600,
            'arquivo_privado_permissoes_invalidas')
    return path


def context(container):
    labels = container['Config']['Labels']
    require(labels.get('com.docker.compose.project') == 'socialmei-team',
            'projeto_compose_divergente')
    wd = Path(labels.get('com.docker.compose.project.working_dir', '')).resolve()
    require(wd == legacy.ROOT.resolve(), 'checkout_compose_divergente')
    env = Path(labels.get('com.docker.compose.project.environment_file', ''))
    require(env.is_absolute() and env.resolve() == wd / '.env.team'
            and env.is_file() and not env.is_symlink(), 'env_compose_divergente')
    paths = [Path(v) for v in labels.get('com.docker.compose.project.config_files', '').split(',') if v]
    require(paths and len(paths) == len(set(paths)) and all(
        p.is_absolute() and p.is_file() and not p.is_symlink() for p in paths),
        'arquivos_compose_invalidos')
    require(all(p.resolve().is_relative_to(legacy.ROOT.resolve())
                or p.resolve().is_relative_to(legacy.BACKUPS.resolve()) for p in paths),
            'compose_fora_do_escopo')
    command = ['docker', '--host=unix:///var/run/docker.sock', 'compose',
               '-p', 'socialmei-team', '--env-file', str(env)]
    for path in paths:
        command += ['-f', str(path)]
    return wd, command, {str(p): legacy.digest_file(p) for p in [env, *paths]}


def overlay(service):
    config = {'image': legacy.image_tags(CANDIDATE_SHA)[service]}
    if service == 'team-api':
        config['environment'] = {'SOCIALMEI_RELEASE_SHA': CANDIDATE_SHA}
    return {'services': {service: config}}


def allowed_model(before, after, service):
    expected = copy.deepcopy(before)
    expected['services'][service]['image'] = legacy.image_tags(CANDIDATE_SHA)[service]
    if service == 'team-api':
        expected['services'][service].setdefault('environment', {})['SOCIALMEI_RELEASE_SHA'] = CANDIDATE_SHA
    require(after == expected, 'mudanca_fora_do_escopo')


def image_for(container, sha):
    rows = json.loads(legacy.docker('image', 'inspect', container['Config']['Image']))
    require(len(rows) == 1 and rows[0]['Id'] == container['Image']
            and rows[0]['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == sha,
            'imagem_runtime_divergente')
    return rows[0]


def runtime_matches(model, container, service, image):
    config = model['services'][service]
    require(legacy.shape_matches(model, container, service), 'runtime_modelo_divergente')
    for key, options in config.get('networks', {}).items():
        network = model['networks'][key]['name']
        aliases = set(container['NetworkSettings']['Networks'][network].get('Aliases') or [])
        expected_aliases = set((options or {}).get('aliases') or [])
        expected_aliases.update((service, container['Name'].removeprefix('/')))
        require(aliases == expected_aliases, 'aliases_runtime_divergentes')
    inherited = dict(v.split('=', 1) for v in image['Config'].get('Env', []) if '=' in v)
    inherited.update({k: str(v) for k, v in (config.get('environment') or {}).items()})
    require(legacy.env_map(container) == inherited, 'ambiente_runtime_divergente')
    require(config['image'] == container['Config']['Image'], 'tag_runtime_divergente')
    require(container['Config'].get('User', '') == (config.get('user') if config.get('user') is not None
                                                  else image['Config'].get('User', '')),
            'usuario_runtime_divergente')
    restart = config.get('restart', 'no')
    require(container['HostConfig'].get('RestartPolicy', {}).get('Name', 'no') == restart,
            'restart_runtime_divergente')
    for field, docker_field in [('command', 'Cmd'), ('entrypoint', 'Entrypoint'), ('working_dir', 'WorkingDir')]:
        expected = config[field] if config.get(field) is not None else image['Config'].get(docker_field)
        require(expected == container['Config'].get(docker_field), 'comando_runtime_divergente')


def ledger035():
    query = "BEGIN READ ONLY; SELECT COALESCE(json_agg(version ORDER BY version),'[]'::json) FROM socialmei.schema_migrations; COMMIT;"
    output = legacy.docker('exec', legacy.POSTGRES, 'psql', '-X', '-A', '-t', '-U', 'socialmei_team',
                           '-d', 'socialmei_team', '-v', 'ON_ERROR_STOP=1', '-c', query).decode()
    rows = [v for v in output.splitlines() if v.startswith('[')]
    require(len(rows) == 1 and json.loads(rows[0]) == sorted(profile.MIGRATIONS),
            'ledger_035_divergente')


def capacity_gate(bundle):
    require(bundle.is_file() and not bundle.is_symlink(), 'pacote_ausente')
    required = max(4 * 1024**3, bundle.stat().st_size * 8)
    require(shutil.disk_usage(tempfile.gettempdir()).free >= required,
            'espaco_temporario_insuficiente')
    memory = Path('/proc/meminfo').read_text()
    match = re.search(r'^MemAvailable:\s+(\d+) kB$', memory, re.M)
    require(match is not None and int(match[1]) >= 256 * 1024, 'memoria_disponivel_insuficiente')


def preflight(source, bundle):
    require(legacy.run(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip() == CANDIDATE_SHA,
            'source_sha_divergente')
    require(not legacy.run(['git', '-C', str(source), 'status', '--porcelain=v1', '--untracked-files=all']).strip(),
            'source_modificado')
    files = sorted((source / 'database/migrations').glob('*.sql'))
    checked = profile.verify([p.name for p in files], lambda name: (source / 'database/migrations' / name).read_bytes())
    require(checked['profile'] == '035', 'perfil_035_obrigatorio')
    capacity_gate(bundle)
    importer = sibling('v01_import', 'team-v33-import-images.py')
    receipt = importer.read_bundle(bundle, expected_sha=CANDIDATE_SHA)
    require(receipt.get('release_profile') == '035', 'pacote_nao_e_035')
    pinned = {s: json.loads(legacy.docker('image', 'inspect', legacy.image_tags(CANDIDATE_SHA)[s]))[0]['Id']
              for s in NAMES}
    require(all(importer.local_image_status(receipt, expected_sha=CANDIDATE_SHA).values()),
            'imagens_candidatas_nao_carregadas_ou_divergentes')
    ledger035()
    protected = {name: protected_fingerprint(legacy.inspect(name)) for name in PROTECTED}
    plans = {}
    for service, name in NAMES.items():
        container = legacy.inspect(name)
        require(container['State'].get('Running'), 'servico_baseline_inativo')
        if service == 'team-api':
            require(container['State'].get('Health', {}).get('Status') == 'healthy', 'api_baseline_nao_saudavel')
        image = image_for(container, BASE_SHA)
        wd, command, hashes = context(container)
        before = legacy.render(command, wd)
        runtime_matches(before, container, service, image)
        candidate = json.loads(legacy.run(command + ['-f', '-', 'config', '--format', 'json'],
                                        cwd=wd, input_bytes=json.dumps(overlay(service)).encode()))
        # Match Compose's escaped literal dollars using the existing runtime renderer convention.
        for cfg in candidate.get('services', {}).values():
            for key, value in (cfg.get('environment') or {}).items():
                if isinstance(value, str):
                    cfg['environment'][key] = value.replace('$$', '$')
        allowed_model(before, candidate, service)
        candidate_image = json.loads(legacy.docker('image', 'inspect', legacy.image_tags(CANDIDATE_SHA)[service]))[0]
        require(candidate_image['Id'] == pinned[service], 'tag_candidata_alterada_durante_validacao')
        require(candidate_image['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == CANDIDATE_SHA,
                'imagem_candidata_revision_diverge')
        effective_env = dict(v.split('=', 1) for v in candidate_image['Config'].get('Env', []) if '=' in v)
        effective_env.update({k: str(v) for k, v in candidate['services'][service].get('environment', {}).items()})
        expected_env = legacy.env_map(container)
        if service == 'team-api':
            expected_env['SOCIALMEI_RELEASE_SHA'] = CANDIDATE_SHA
        require(effective_env == expected_env, 'defaults_imagem_alteram_ambiente')
        plans[service] = {'wd': wd, 'command': command, 'files': hashes, 'before': before,
                          'after': candidate, 'container': container,
                          'mount_fingerprints': mount_fingerprints(container),
                          'candidate_image_id': candidate_image['Id']}
    require('socialmei_team_egress' in legacy.inspect(legacy.API)['NetworkSettings']['Networks'],
            'egress_ausente')
    return plans, protected


def backup_gate(folder, plans):
    require(folder.is_absolute() and folder == folder.resolve() and folder.parent == legacy.PRIVATE
            and folder.is_dir() and not folder.is_symlink() and folder.stat().st_uid == 0
            and stat.S_IMODE(folder.stat().st_mode) == 0o700, 'backup_privado_invalido')
    receipt = json.loads(private_file(folder / 'v01-backup-receipt.json').read_text())
    require(receipt.get('source_sha') == CANDIDATE_SHA and receipt.get('baseline_sha') == BASE_SHA
            and receipt.get('release_profile') == '035', 'recibo_backup_divergente')
    require(0 <= time.time() - receipt.get('captured_unix', 0) <= 900, 'backup_nao_fresco')
    required = {'postgres.dump', 'images-before.tar', 'private-config.tar', 'restore035.json'}
    hashes = receipt.get('sha256', {})
    require(required <= set(hashes), 'backup_incompleto')
    for name, digest in hashes.items():
        require(Path(name).name == name and name not in ('.', '..'), 'nome_backup_invalido')
        require(legacy.digest_file(private_file(folder / name)) == digest, 'backup_digest_diverge')
    require(0 <= time.time() - (folder / 'postgres.dump').stat().st_mtime <= 900,
            'dump_nao_fresco')
    restore = json.loads(private_file(folder / 'restore035.json').read_text())
    require(restore.get('backup_sha256') == hashes['postgres.dump']
            and restore.get('ledger') == sorted(profile.MIGRATIONS)
            and restore.get('restore_verified') is True and restore.get('isolated') is True
            and restore.get('migrations_executed') is False
            and restore.get('production_runtime_changed') is False,
            'restore_035_nao_comprovado')
    require(receipt.get('runtime_fingerprints') == {
        s: runtime_fingerprint(p['container']) for s, p in plans.items()}, 'backup_runtime_diverge')
    require(receipt.get('mount_fingerprints') == {
        s: p['mount_fingerprints'] for s, p in plans.items()}, 'backup_mounts_divergem')
    verify_private_archive(folder / 'private-config.tar', plans)
    images = {s: {'tag': p['container']['Config']['Image'], 'image_id': p['container']['Image']}
              for s, p in plans.items()}
    sibling('v01_rollback_import', 'team-v33-import-images.py').verify_archive_config_digests(
        folder / 'images-before.tar', images, BASE_SHA, 'bundle')
    return receipt


def inputs_unchanged(plans, protected, *, check_protected=True):
    for plan in plans.values():
        require(all(legacy.digest_file(Path(path)) == digest for path, digest in plan['files'].items()),
                'configuracao_alterada_durante_janela')
        require(mount_fingerprints(plan['container']) == plan['mount_fingerprints'],
                'mount_privado_alterado_durante_janela')
    if check_protected:
        require(all(protected_fingerprint(legacy.inspect(name)) == value for name, value in protected.items()),
                'servico_protegido_alterado_ou_reiniciado')


def fresh_backup(receipt, folder):
    require(0 <= time.time() - receipt.get('captured_unix', 0) <= 900
            and 0 <= time.time() - (folder / 'postgres.dump').stat().st_mtime <= 900,
            'backup_expirou_antes_do_corte')


def operate(source, bundle, backup=None, apply=False):
    plans, protected = preflight(source, bundle)
    if not apply:
        return {'action': 'inspect_passed', 'source_sha': CANDIDATE_SHA,
                'migrations_executed': False, 'production_changed': False,
                'backup_verified': False, 'deployment_ready': False}
    require(os.geteuid() == 0 and backup is not None, 'apply_exige_root_e_backup')
    # Shared lock with the existing pilot operator; no concurrent publication.
    with open('/run/lock/socialmei-wa-pilot-release.lock', 'a') as lock:
        legacy.fcntl.flock(lock, legacy.fcntl.LOCK_EX | legacy.fcntl.LOCK_NB)
        # Rebuild the complete plan under the lock, avoiding stale inspect evidence.
        plans, protected = preflight(source, bundle)
        backup_receipt = backup_gate(backup, plans)
        inputs_unchanged(plans, protected)
        attempted = []
        old_files = {p: hashlib.sha256(legacy.https('/frontend/' + p, 200)).hexdigest()
                     for p in legacy.STATIC_FILES}
        try:
            for service, plan in plans.items():
                inputs_unchanged(plans, protected)
                if not attempted:
                    fresh_backup(backup_receipt, backup)
                require(runtime_fingerprint(legacy.inspect(NAMES[service])) == runtime_fingerprint(plan['container']),
                        'runtime_alterado_antes_do_corte')
                image_for(plan['container'], BASE_SHA)
                require(json.loads(legacy.docker('image', 'inspect', legacy.image_tags(CANDIDATE_SHA)[service]))[0]['Id']
                        == plan['candidate_image_id'], 'imagem_candidata_alterada_antes_do_corte')
                path = backup / (service + '.candidate.compose.json')
                with path.open('x', encoding='utf-8') as stream:
                    os.chmod(path, 0o600)
                    json.dump(overlay(service), stream)
                command = plan['command'] + ['-f', str(path)]
                allowed_model(plan['before'], legacy.render(command, plan['wd']), service)
                attempted.append(service)
                legacy.run(command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', service],
                           cwd=plan['wd'], timeout=180)
                current = legacy.wait_service(service)
                require(current['Image'] == plan['candidate_image_id'], 'imagem_candidata_alterada_no_corte')
                runtime_matches(plan['after'], current, service, image_for(current, CANDIDATE_SHA))
                require(legacy.security_invariant(current) == legacy.security_invariant(plan['container']),
                        'seguranca_alterada')
                for key in ('Cmd', 'Entrypoint', 'WorkingDir', 'User', 'Healthcheck', 'StopSignal', 'Volumes'):
                    require(current['Config'].get(key) == plan['container']['Config'].get(key),
                            'configuracao_runtime_alterada')
                inputs_unchanged(plans, protected)
                ledger035()
            expected = {p: legacy.digest_file(source / 'frontend' / p) for p in legacy.STATIC_FILES}
            legacy.public_smoke(expected_files=expected)
        except Exception:
            # Restore only the attempted services, using their original, untouched Compose contexts.
            failures = []
            for service in reversed(attempted):
                try:
                    plan = plans[service]
                    # Protected-service drift must be reported, but must not strand a changed API.
                    inputs_unchanged(plans, protected, check_protected=False)
                    try:
                        image_for(plan['container'], BASE_SHA)
                    except legacy.Blocked:
                        archive = private_file(backup / 'images-before.tar')
                        require(legacy.digest_file(archive) == backup_receipt['sha256']['images-before.tar'],
                                'rollback_arquivo_alterado')
                        legacy.docker('load', '--input', str(archive), timeout=300)
                        image_for(plan['container'], BASE_SHA)
                    legacy.run(plan['command'] + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', service],
                               cwd=plan['wd'], timeout=180)
                    current = legacy.wait_service(service)
                    runtime_matches(plan['before'], current, service, image_for(current, BASE_SHA))
                    require(legacy.security_invariant(current) == legacy.security_invariant(plan['container']),
                            'rollback_seguranca_diverge')
                except Exception:
                    failures.append(service)
            require(not failures, 'rollback_incompleto')
            ledger035()
            legacy.public_smoke(expected_files=old_files)
            inputs_unchanged(plans, protected)
            raise
    return {'action': 'api_gateway_published', 'source_sha': CANDIDATE_SHA,
            'migrations_executed': False, 'provider_messages_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(operate(args.source, args.bundle, args.backup, args.apply)))
    except Exception as error:
        # Compose output, runtime environment, private paths and provider payloads are never printed.
        code = str(error) if isinstance(error, legacy.Blocked) and re.fullmatch(r'[a-z0-9_]+', str(error)) else 'gate_failed_details_redacted'
        print(json.dumps({'action': 'blocked', 'code': code,
                          'production_state_requires_verification': args.apply}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
