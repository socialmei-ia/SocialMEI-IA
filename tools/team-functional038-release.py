"""Pinned 266/035 -> a472/038 operator. Inspect by default; guarded atomic upgrade.

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
import zipfile


def sibling(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


legacy = sibling('functional038_runtime', 'team-whatsapp-release.py')
profile = sibling('functional038_profile', 'team-release-profile.py')
require = legacy.require
BASE_SHA = '266e59b6a766c07f60c83b7b3053b33fc91cc135'
CANDIDATE_SHA = 'a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510'
AUTHORIZATION = '266-035-to-a472-038'
BUNDLE_SHA256 = '43f5df836e3b49e4e99a5a01f0d243108f5310be4cd8e2d7d68a59d28afcac2a'
JOURNAL = 'functional038-state.json'
NAMES = {'team-api': legacy.API, 'team-gateway': legacy.GATEWAY}
PROTECTED = (legacy.POSTGRES, legacy.WAHA, legacy.N8N)
CANDIDATE_STATIC_FILES = legacy.STATIC_FILES + (
    'scripts/v22-appointments.js', 'scripts/v22-inbox-customer.js',
    'scripts/v22-whatsapp-replies.js', 'scripts/product-store.js',
)


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


def ledger(expected=None):
    query = "BEGIN READ ONLY; SELECT COALESCE(json_agg(version ORDER BY version),'[]'::json) FROM socialmei.schema_migrations; COMMIT;"
    output = legacy.docker('exec', legacy.POSTGRES, 'psql', '-X', '-A', '-t', '-U', 'socialmei_team',
                           '-d', 'socialmei_team', '-v', 'ON_ERROR_STOP=1', '-c', query).decode()
    rows = [v for v in output.splitlines() if v.startswith('[')]
    require(len(rows) == 1, 'ledger_indisponivel')
    result = json.loads(rows[0])
    if expected is not None:
        require(result == sorted(expected), 'ledger_divergente')
    return result


def ledger035():
    return ledger(profile.MIGRATIONS)


def ledger038():
    return ledger(profile.MIGRATIONS038)


def capacity_gate(bundle):
    require(bundle.is_file() and not bundle.is_symlink(), 'pacote_ausente')
    required = max(4 * 1024**3, bundle.stat().st_size * 8)
    require(shutil.disk_usage(tempfile.gettempdir()).free >= required,
            'espaco_temporario_insuficiente')
    memory = Path('/proc/meminfo').read_text()
    match = re.search(r'^MemAvailable:\s+(\d+) kB$', memory, re.M)
    require(match is not None and int(match[1]) >= 256 * 1024, 'memoria_disponivel_insuficiente')


def preflight(source, bundle):
    source_gate(source)
    require(legacy.run(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip() == CANDIDATE_SHA,
            'source_sha_divergente')
    require(not legacy.run(['git', '-C', str(source), 'status', '--porcelain=v1', '--untracked-files=all']).strip(),
            'source_modificado')
    files = sorted((source / 'database/migrations').glob('*.sql'))
    checked = profile.verify038([p.name for p in files], lambda name: (source / 'database/migrations' / name).read_bytes())
    require(checked['profile'] == '038', 'perfil_038_obrigatorio')
    capacity_gate(bundle)
    importer = sibling('v01_import', 'team-v33-import-images.py')
    receipt = read_bundle038(bundle)
    require(receipt.get('release_profile') == '038', 'pacote_nao_e_038')
    pinned = {s: json.loads(legacy.docker('image', 'inspect', legacy.image_tags(CANDIDATE_SHA)[s]))[0]['Id']
              for s in NAMES}
    require(all(importer.local_image_status(receipt, expected_sha=CANDIDATE_SHA).values()),
            'imagens_candidatas_nao_carregadas_ou_divergentes')
    ledger035()
    protected = {}
    for name in PROTECTED:
        container = legacy.inspect(name)
        require(container['State'].get('Running') is True
                and container['State'].get('Health', {}).get('Status') not in ('unhealthy', 'starting'),
                'servico_protegido_nao_saudavel')
        protected[name] = protected_fingerprint(container)
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


def backup_gate(folder, plans, *, fresh=True):
    require(folder.is_absolute() and folder == folder.resolve() and folder.parent == legacy.PRIVATE
            and folder.is_dir() and not folder.is_symlink() and folder.stat().st_uid == 0
            and stat.S_IMODE(folder.stat().st_mode) == 0o700, 'backup_privado_invalido')
    receipt = json.loads(private_file(folder / 'v01-backup-receipt.json').read_text())
    require(receipt.get('source_sha') == CANDIDATE_SHA and receipt.get('baseline_sha') == BASE_SHA
            and receipt.get('release_profile') == '038', 'recibo_backup_divergente')
    require(not fresh or 0 <= time.time() - receipt.get('captured_unix', 0) <= 900, 'backup_nao_fresco')
    required = {'postgres.dump', 'images-before.tar', 'private-config.tar', 'restore035.json'}
    hashes = receipt.get('sha256', {})
    require(required <= set(hashes), 'backup_incompleto')
    for name, digest in hashes.items():
        require(Path(name).name == name and name not in ('.', '..'), 'nome_backup_invalido')
        require(legacy.digest_file(private_file(folder / name)) == digest, 'backup_digest_diverge')
    require(not fresh or 0 <= time.time() - (folder / 'postgres.dump').stat().st_mtime <= 900,
            'dump_nao_fresco')
    restore = json.loads(private_file(folder / 'restore035.json').read_text())
    require(restore.get('backup_sha256') == hashes['postgres.dump']
            and restore.get('ledger') == sorted(profile.MIGRATIONS)
            and restore.get('restore_verified') is True and restore.get('isolated') is True
            and restore.get('migrations_executed') is False
            and restore.get('production_runtime_changed') is False,
            'restore_035_nao_comprovado')
    groups = ['columns', 'constraint_properties', 'constraints', 'environment', 'functions',
              'indexes', 'schemas', 'sequences', 'tables', 'triggers', 'views']
    require(restore.get('fingerprints_match') is True
            and restore.get('schema_and_constraints_match') is True
            and restore.get('table_count') == 71
            and isinstance(restore.get('metadata_groups'), list)
            and sorted(restore['metadata_groups']) == groups,
            'restore_035_dados_schema_constraints_nao_comprovados')
    require(receipt.get('runtime_fingerprints') == {
        s: runtime_fingerprint(p['container']) for s, p in plans.items()}, 'backup_runtime_diverge')
    require(receipt.get('mount_fingerprints') == {
        s: p['mount_fingerprints'] for s, p in plans.items()}, 'backup_mounts_divergem')
    verify_private_archive(folder / 'private-config.tar', plans)
    images = {s: {'tag': p['container']['Config']['Image'], 'image_id': p['container']['Image']}
              for s, p in plans.items()}
    sibling('functional038_rollback_import', 'team-functional038-rollback-images.py').verify_archive_config_digests(
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


def read_bundle038(bundle):
    require(bundle.is_absolute() and not bundle.is_symlink()
            and bundle.resolve().parent == legacy.BACKUPS.resolve(), 'pacote_fora_do_escopo')
    require(legacy.digest_file(bundle) == BUNDLE_SHA256, 'bundle_digest_diverge')
    importer = sibling('functional038_import', 'team-v33-import-images.py')
    with tempfile.TemporaryDirectory(prefix='functional038-verify-') as temporary:
        image_archive = Path(temporary) / 'images.tar.gz'
        with zipfile.ZipFile(bundle) as archive:
            names = {'SHA256SUMS', 'image-receipt.json', 'images.tar.gz'}
            entries = archive.infolist()
            require(len(entries) == 3 and {e.filename for e in entries} == names,
                    'pacote_com_entradas_inesperadas')
            require(all(not e.is_dir() and stat.S_IFMT(e.external_attr >> 16) != stat.S_IFLNK
                        and 0 < e.file_size <= 1024**3 for e in entries), 'pacote_invalido')
            actual = {}
            for entry in entries:
                digest = hashlib.sha256()
                with archive.open(entry) as stream:
                    if entry.filename == 'images.tar.gz':
                        with image_archive.open('xb') as output:
                            for chunk in iter(lambda: stream.read(1024**2), b''):
                                output.write(chunk)
                                digest.update(chunk)
                    else:
                        for chunk in iter(lambda: stream.read(1024**2), b''):
                            digest.update(chunk)
                actual[entry.filename] = digest.hexdigest()
            rows = [re.fullmatch(r'([a-f0-9]{64})\s+([a-zA-Z0-9._-]+)', line)
                    for line in archive.read('SHA256SUMS').decode().strip().splitlines()]
            require(len(rows) == 2 and all(rows), 'manifesto_sha256_invalido')
            expected = {row[2]: row[1] for row in rows}
            require(set(expected) == names - {'SHA256SUMS'}
                    and all(actual[name] == value for name, value in expected.items()),
                    'sha256_do_pacote_divergente')
            receipt = json.loads(archive.read('image-receipt.json'))
        require(receipt.get('source_sha') == CANDIDATE_SHA
                and receipt.get('release_profile') == '038'
                and receipt.get('migration_sha256') == profile.MIGRATIONS038
                and set(receipt.get('images', {})) == set(NAMES), 'recibo_038_divergente')
        proof = profile.rehearsal038(receipt.get('migration_rehearsal'), CANDIDATE_SHA)
        require(proof.get('api_image_id') == receipt['images']['team-api'].get('image_id'),
                'ensaio_nao_corresponde_a_imagem')
        for service, image in receipt['images'].items():
            require(image.get('tag') == legacy.image_tags(CANDIDATE_SHA)[service]
                    and re.fullmatch(r'sha256:[a-f0-9]{64}', str(image.get('image_id'))),
                    'imagem_de_recibo_invalida')
        importer.verify_archive_config_digests(image_archive, receipt['images'], CANDIDATE_SHA, 'bundle')
    return receipt


def source_gate(source):
    require(source.is_absolute() and source == source.resolve() and not source.is_symlink(),
            'source_fora_do_escopo')
    require(legacy.run(['git', '-C', str(source), 'rev-parse', 'HEAD']).decode().strip() == CANDIDATE_SHA,
            'source_sha_divergente')
    require(not legacy.run(['git', '-C', str(source), 'status', '--porcelain=v1', '--untracked-files=all']).strip(),
            'source_modificado')
    folder = source / 'database/migrations'
    names = sorted(p.name for p in folder.glob('*.sql'))
    require(all(not (folder / name).is_symlink() for name in names), 'migration_link_proibido')
    profile.verify038(names, lambda name: (folder / name).read_bytes())
    require((source / 'tools/team_migrate.py').is_file()
            and not (source / 'tools/team_migrate.py').is_symlink(), 'migrador_invalido')


def no_external_senders(plans):
    env = legacy.env_map(plans['team-api']['container'])
    for key in ('SOCIALMEI_WHATSAPP_BOT_ENABLED', 'SOCIALMEI_WHATSAPP_HUMAN_SEND_ENABLED'):
        require(env.get(key, 'false').strip().lower() == 'false', 'envio_automatico_deve_estar_desligado')


def migration_snapshot(source, backup):
    """Copy immutable pinned Git blobs, then recheck the complete038 manifest."""
    folder = backup / 'functional038-migration-source'
    folder.mkdir(mode=0o700)
    migrations = folder / 'migrations'
    migrations.mkdir(mode=0o700)
    for name in profile.MIGRATIONS038:
        content = legacy.run(['git', '-C', str(source), 'show',
                              CANDIDATE_SHA + ':database/migrations/' + name])
        path = migrations / name
        with path.open('xb') as stream:
            os.chmod(path, 0o600)
            stream.write(content)
    profile.verify038(sorted(p.name for p in migrations.iterdir()),
                      lambda name: (migrations / name).read_bytes())
    content = legacy.run(['git', '-C', str(source), 'show', CANDIDATE_SHA + ':tools/team_migrate.py'])
    script = folder / 'team_migrate.py'
    with script.open('xb') as stream:
        os.chmod(script, 0o600)
        stream.write(content)
    return migrations, script


def migrate038(source, plans, backup):
    """One official transaction, on an ephemeral container; never a database restore."""
    source_gate(source)
    ledger035()
    api = plans['team-api']['container']
    pg = legacy.inspect(legacy.POSTGRES)
    common = set(api['NetworkSettings']['Networks']) & set(pg['NetworkSettings']['Networks'])
    require(len(common) == 1, 'rede_database_ambigua')
    network = next(iter(common))
    network_details = json.loads(legacy.docker('network', 'inspect', network))
    require(len(network_details) == 1 and network_details[0].get('Internal') is True,
            'rede_database_nao_privada')
    env = legacy.env_map(api)
    keys = ('POSTGRES_HOST', 'POSTGRES_PORT', 'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD')
    require(all(isinstance(env.get(key), str) and env[key] and '\n' not in env[key]
                and '\r' not in env[key] and '\x00' not in env[key] for key in keys),
            'ambiente_database_invalido')
    pg_env = legacy.env_map(pg)
    require(env['POSTGRES_PORT'] == '5432'
            and env['POSTGRES_USER'] == pg_env.get('POSTGRES_USER')
            and env['POSTGRES_DB'] == pg_env.get('POSTGRES_DB')
            and env['POSTGRES_PASSWORD'] == pg_env.get('POSTGRES_PASSWORD'),
            'ambiente_database_divergente')
    aliases = set(pg['NetworkSettings']['Networks'][network].get('Aliases') or [])
    aliases.add(pg['Name'].removeprefix('/'))
    require(env['POSTGRES_HOST'] in aliases, 'host_database_fora_do_runtime')
    image = plans['team-api']['candidate_image_id']
    require(json.loads(legacy.docker('image', 'inspect', legacy.image_tags(CANDIDATE_SHA)['team-api']))[0]['Id'] == image,
            'imagem_candidata_alterada_antes_migration')
    migrations, script = migration_snapshot(source, backup)
    env_file = backup / 'functional038-migration.env'
    container = None
    label = fingerprint([str(backup), CANDIDATE_SHA])
    container_name = 'socialmei-functional038-migrate-' + label[:16]
    try:
        with env_file.open('x', encoding='utf-8') as output:
            os.chmod(env_file, 0o600)
            output.write(''.join(key + '=' + env[key] + '\n' for key in keys)
                         + 'PYTHONPATH=/app\nPYTHONDONTWRITEBYTECODE=1\n'
                         + 'PGOPTIONS=-c lock_timeout=5s -c statement_timeout=120s '
                         + '-c idle_in_transaction_session_timeout=150s\n')
        container = legacy.docker(
            'create', '--name', container_name, '--network', network, '--read-only', '--cap-drop', 'ALL',
            '--security-opt', 'no-new-privileges', '--memory', '256m', '--pids-limit', '128',
            '--label', 'socialmei.functional038.migration=' + label,
            '--env-file', str(env_file), '--entrypoint', 'python',
            '--mount', 'type=bind,src=' + str(migrations) + ',dst=/migrations,readonly',
            '--mount', 'type=bind,src=' + str(script) + ',dst=/maintenance/team_migrate.py,readonly',
            image, '/maintenance/team_migrate.py').decode().strip()
        require(re.fullmatch(r'[a-f0-9]{64}', container) is not None, 'migrador_container_invalido')
        created = legacy.inspect(container_name)
        require(created['Id'] == container and created['Image'] == image and created['Config']['Labels'].get(
            'socialmei.functional038.migration') == label, 'migrador_identidade_diverge')
        write_private_json(backup, 'functional038-migrator.json', {
            'source_sha': CANDIDATE_SHA, 'phase': 'created_before_start', 'container_id': container,
            'container_name': container_name, 'label': label, 'image_id': image,
            'migration_sha256': profile.MIGRATIONS038,
            'migrator_sha256': legacy.digest_file(script),
        })
        legacy.docker('start', '--attach', container, timeout=240)
        require(legacy.inspect(container_name)['State'].get('ExitCode') == 0, 'migration_falhou')
        ledger038()
    finally:
        if container:
            owned = legacy.inspect(container_name)
            require(owned['Id'] == container and owned['Config']['Labels'].get('socialmei.functional038.migration') == label,
                    'migrador_cleanup_ownership_diverge')
            legacy.docker('rm', '-f', container)
        env_file.unlink(missing_ok=True)


def write_private_json(backup, filename, state):
    require(filename in (JOURNAL, 'functional038-migrator.json'), 'arquivo_journal_invalido')
    path = backup / filename
    require(not path.is_symlink(), 'journal_link_proibido')
    descriptor, name = tempfile.mkstemp(prefix='functional038-state-', suffix='.tmp', dir=backup)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            json.dump(state, stream, sort_keys=True, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_journal(backup, state):
    write_private_json(backup, JOURNAL, state)


def recover_plans(state):
    plans = state['plans']
    require(set(plans) == set(NAMES), 'journal_servicos_divergem')
    for plan in plans.values():
        plan['wd'] = Path(plan['wd'])
    return plans


def migration_inactive(backup):
    label = fingerprint([str(backup), CANDIDATE_SHA])
    ids = legacy.docker('ps', '-a', '--no-trunc', '--filter',
                        'label=socialmei.functional038.migration=' + label,
                        '--format', '{{.ID}}').decode().splitlines()
    require(len(ids) <= 1 and all(re.fullmatch(r'[a-f0-9]{64}', value) for value in ids),
            'migrador_recuperacao_ambigua')
    if ids:
        name = 'socialmei-functional038-migrate-' + label[:16]
        current = legacy.inspect(name)
        require(current['Id'] == ids[0] and current['Config']['Labels'].get(
            'socialmei.functional038.migration') == label, 'migrador_recuperacao_identidade_diverge')
        require(current['State'].get('Running') is False, 'migrador_ainda_em_execucao')
        legacy.docker('rm', current['Id'])


def capture_candidate(service, plan, state, backup):
    current = legacy.inspect(NAMES[service])
    require(current['Image'] == plan['candidate_image_id'], 'imagem_candidata_alterada_no_corte')
    runtime_matches(plan['after'], current, service, image_for(current, CANDIDATE_SHA))
    require(legacy.security_invariant(current) == legacy.security_invariant(plan['container']),
            'seguranca_alterada')
    for key in ('Cmd', 'Entrypoint', 'WorkingDir', 'User', 'Healthcheck', 'StopSignal', 'Volumes'):
        require(current['Config'].get(key) == plan['container']['Config'].get(key),
                'configuracao_runtime_alterada')
    state['candidate_runtime'][service] = runtime_fingerprint(current)
    write_journal(backup, state)


def rollback_services(plans, protected, backup, backup_receipt, state):
    """Retain schema038 and every post-cutover row; recover only the two images."""
    ledger038()
    for service in set(NAMES) - set(state['attempted']):
        require(runtime_fingerprint(legacy.inspect(NAMES[service])) == runtime_fingerprint(
            plans[service]['container']), 'rollback_baseline_cas_diverge')
    failures = []
    for service in reversed(state['attempted']):
        try:
            plan = plans[service]
            inputs_unchanged(plans, protected, check_protected=False)
            current = legacy.inspect(NAMES[service])
            if service in state['rolled_back_services']:
                require(runtime_fingerprint(current) == state['rolled_back_runtime'][service],
                        'rollback_restaurado_cas_diverge')
                runtime_matches(plan['before'], current, service, image_for(current, BASE_SHA))
                continue
            expected = state['candidate_runtime'].get(service)
            if expected is None:
                if runtime_fingerprint(current) == runtime_fingerprint(plan['container']):
                    runtime_matches(plan['before'], current, service, image_for(current, BASE_SHA))
                    state['rolled_back_services'].append(service)
                    state['rolled_back_runtime'][service] = runtime_fingerprint(current)
                    write_journal(backup, state)
                    continue
                # An interrupted Compose call may have created the intended container.
                capture_candidate(service, plan, state, backup)
                current = legacy.inspect(NAMES[service])
                expected = state['candidate_runtime'][service]
            require(runtime_fingerprint(current) == expected, 'rollback_runtime_cas_diverge')
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
            restored = legacy.wait_service(service)
            runtime_matches(plan['before'], restored, service, image_for(restored, BASE_SHA))
            require(legacy.security_invariant(restored) == legacy.security_invariant(plan['container']),
                    'rollback_seguranca_diverge')
            state['rolled_back_services'].append(service)
            state['rolled_back_runtime'][service] = runtime_fingerprint(restored)
            write_journal(backup, state)
        except Exception:
            failures.append(service)
    require(not failures, 'rollback_incompleto')
    ledger038()
    legacy.public_smoke(expected_files=state['old_files'])
    inputs_unchanged(plans, protected)
    state['phase'] = 'rolled_back_schema038_retained'
    write_journal(backup, state)


def overlay_file(backup, service):
    path = backup / (service + '.candidate.compose.json')
    content = json.dumps(overlay(service)).encode()
    if path.exists() or path.is_symlink():
        require(private_file(path).read_bytes() == content, 'overlay_da_janela_diverge')
    else:
        with path.open('xb') as stream:
            os.chmod(path, 0o600)
            stream.write(content)
    return path


def publish_services(source, plans, protected, backup, receipt, state, *, run_migration):
    try:
        if run_migration:
            fresh_backup(receipt, backup)
            migrate038(source, plans, backup)
        state['phase'] = 'migration038_committed'
        write_journal(backup, state)
        for service, plan in plans.items():
            inputs_unchanged(plans, protected)
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
        state['phase'] = 'published038'
        write_journal(backup, state)
    except Exception:
        installed = ledger()
        require(installed in (sorted(profile.MIGRATIONS), sorted(profile.MIGRATIONS038)),
                'migration_estado_desconhecido_intervencao_obrigatoria')
        if installed == sorted(profile.MIGRATIONS038):
            state['phase'] = 'migration038_recovery_required'
            write_journal(backup, state)
            rollback_services(plans, protected, backup, receipt, state)
        else:
            require(not state['attempted'], 'runtime_alterado_com_ledger035')
            inputs_unchanged(plans, protected)
            state['phase'] = 'migration_failed035_retained'
            write_journal(backup, state)
        raise


def operate(source, bundle, backup=None, apply=False, authorization=None):
    source_gate(source)
    plans, protected = preflight(source, bundle)
    no_external_senders(plans)
    if not apply:
        return {'action': 'inspect_passed', 'source_sha': CANDIDATE_SHA,
                'migrations_executed': False, 'production_changed': False,
                'backup_verified': False, 'deployment_ready': False}
    require(authorization == AUTHORIZATION, 'autorizacao_operacional_explicita_obrigatoria')
    require(os.geteuid() == 0 and backup is not None, 'apply_exige_root_e_backup')
    with open('/run/lock/socialmei-wa-pilot-release.lock', 'a') as lock:
        legacy.fcntl.flock(lock, legacy.fcntl.LOCK_EX | legacy.fcntl.LOCK_NB)
        source_gate(source)
        plans, protected = preflight(source, bundle)
        no_external_senders(plans)
        receipt = backup_gate(backup, plans)
        require(not (backup / JOURNAL).exists(), 'janela_ja_iniciada_use_recuperacao')
        inputs_unchanged(plans, protected)
        state = {'source_sha': CANDIDATE_SHA, 'baseline_sha': BASE_SHA, 'bundle_sha256': BUNDLE_SHA256,
                 'backup_receipt_sha256': legacy.digest_file(backup / 'v01-backup-receipt.json'),
                 'phase': 'before_migration035', 'plans': plans,
                 'backup_plans': copy.deepcopy(plans), 'protected': protected,
                 'attempted': [], 'rolled_back_services': [], 'rolled_back_runtime': {},
                 'candidate_runtime': {},
                 'old_files': {p: hashlib.sha256(legacy.https('/frontend/' + p, 200)).hexdigest()
                               for p in legacy.STATIC_FILES}}
        write_journal(backup, state)
        publish_services(source, plans, protected, backup, receipt, state, run_migration=True)
    return {'action': 'api_gateway_published_schema038', 'source_sha': CANDIDATE_SHA,
            'migrations_executed': True, 'database_downgraded': False, 'provider_messages_sent': False}


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
                and state.get('backup_receipt_sha256') == legacy.digest_file(
                    private_file(backup / 'v01-backup-receipt.json')), 'journal_nao_corresponde_a_janela')
        require(state.get('phase') in ('before_migration035', 'published038', 'migration038_committed',
                'migration038_recovery_required'), 'janela_nao_recuperavel')
        plans = recover_plans(state)
        original = recover_plans({'plans': state['backup_plans']})
        receipt = backup_gate(backup, original, fresh=False)
        ledger038()
        migration_inactive(backup)
        require(set(state.get('attempted', [])) <= set(NAMES)
                and len(state['attempted']) == len(set(state['attempted']))
                and set(state.get('rolled_back_services', [])) <= set(state['attempted']),
                'journal_tentativas_divergem')
        no_external_senders(plans)
        rollback_services(plans, state['protected'], backup, receipt, state)
    return {'action': 'rolled_back_schema038_retained', 'source_sha': BASE_SHA,
            'migrations_executed': False, 'database_downgraded': False,
            'provider_messages_sent': False}


def resume(source, bundle, backup, authorization=None):
    """Reapply within the same fresh window after a completed image-only rollback."""
    require(authorization == AUTHORIZATION, 'autorizacao_operacional_explicita_obrigatoria')
    require(os.geteuid() == 0, 'resume_exige_root')
    source_gate(source)
    capacity_gate(bundle)
    receipt_images = read_bundle038(bundle)
    importer = sibling('functional038_resume_import', 'team-v33-import-images.py')
    require(all(importer.local_image_status(receipt_images, expected_sha=CANDIDATE_SHA).values()),
            'imagens_candidatas_nao_carregadas_ou_divergentes')
    with open('/run/lock/socialmei-wa-pilot-release.lock', 'a') as lock:
        legacy.fcntl.flock(lock, legacy.fcntl.LOCK_EX | legacy.fcntl.LOCK_NB)
        state = json.loads(private_file(backup / JOURNAL).read_text())
        require(state.get('source_sha') == CANDIDATE_SHA and state.get('baseline_sha') == BASE_SHA
                and state.get('bundle_sha256') == BUNDLE_SHA256
                and state.get('backup_receipt_sha256') == legacy.digest_file(
                    private_file(backup / 'v01-backup-receipt.json'))
                and state.get('phase') == 'rolled_back_schema038_retained', 'resume_janela_diverge')
        original = recover_plans({'plans': state['backup_plans']})
        # This is not a later release or a new migration: the original bounded window stays fresh.
        receipt = backup_gate(backup, original)
        ledger038()
        migration_inactive(backup)
        plans = recover_plans(state)
        inputs_unchanged(plans, state['protected'])
        for service, plan in plans.items():
            current = legacy.inspect(NAMES[service])
            expected = state['rolled_back_runtime'].get(service, runtime_fingerprint(plan['container']))
            require(runtime_fingerprint(current) == expected, 'resume_runtime_cas_diverge')
            runtime_matches(plan['before'], current, service, image_for(current, BASE_SHA))
            require(legacy.render(plan['command'], plan['wd']) == plan['before'],
                    'resume_modelo_baseline_diverge')
            require(mount_fingerprints(current) == plan['mount_fingerprints'],
                    'resume_mounts_divergem')
            plan['container'] = current
        no_external_senders(plans)
        state.update(phase='migration038_committed', attempted=[], rolled_back_services=[],
                     rolled_back_runtime={}, candidate_runtime={})
        write_journal(backup, state)
        publish_services(source, plans, state['protected'], backup, receipt, state, run_migration=False)
    return {'action': 'api_gateway_reapplied_schema038', 'source_sha': CANDIDATE_SHA,
            'migrations_executed': False, 'database_downgraded': False,
            'provider_messages_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--authorization')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true')
    action.add_argument('--rollback', action='store_true')
    action.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    try:
        require(not (args.rollback or args.resume) or args.backup is not None,
                'recuperacao_exige_backup_da_janela')
        if args.rollback:
            result = rollback(args.source, args.bundle, args.backup, args.authorization)
        elif args.resume:
            result = resume(args.source, args.bundle, args.backup, args.authorization)
        else:
            result = operate(args.source, args.bundle, args.backup, args.apply, args.authorization)
        print(json.dumps(result))
    except Exception as error:
        code = str(error) if isinstance(error, legacy.Blocked) and re.fullmatch(r'[a-z0-9_]+', str(error)) else 'gate_failed_details_redacted'
        print(json.dumps({'action': 'blocked', 'code': code,
                          'production_state_requires_verification': args.apply or args.rollback or args.resume}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()


