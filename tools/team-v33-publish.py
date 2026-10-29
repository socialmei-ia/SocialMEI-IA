#!/usr/bin/env python3
"""Explicit image-only Team 033 publication; preparation never restarts a service.

Requires CI images already imported and a healthy, matching effective runtime.
No build, pull, migration, database restore or provider activation is performed.
Private snapshots contain secrets: never share the preparation directory.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen


def sibling(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = sibling('team-v33-runtime-audit')
privacy_helper = sibling('instagram-proxy-privacy')
archive_helper = sibling('v25-release-publish')
shape_helper = sibling('team-publish-prepared')
image_helper = sibling('team-v33-import-images')
ROOT, BACKUPS = audit.ROOT, Path('/home/ubuntu/socialmei-backups')
SHA, SOURCE = audit.EXPECTED_SHA, audit.SOURCE
SERVICES = ('team-api', 'team-gateway')
NAMES = {s: 'socialmei-team-' + s + '-1' for s in SERVICES}
NETWORKS = {'team-api': {'socialmei-team_api', 'socialmei-team_database', 'socialmei_team_egress'},
            'team-gateway': {'socialmei-team_api', 'socialmei_team_web'}}
ORIGIN = 'https://socialmei-ia.54-94-213-7.sslip.io'
require = audit.require


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checkout_snapshot():
    head = audit.command(['git', '-C', str(ROOT), 'rev-parse', 'HEAD']).strip()
    status = audit.command(['git', '-C', str(ROOT), 'status', '--porcelain=v1', '--untracked-files=all']).splitlines()
    require(head == '6f4c8e1795cbb2e9074845edd9ac099a8ea3925b'
            and status == [' M deploy/team/Caddyfile'], 'checkout_original_alterado')
    return {'head': head, 'status': status, 'caddy_sha256': digest(ROOT / 'deploy/team/Caddyfile')}


def env_map(row):
    values = row['Config'].get('Env') or []
    require(all(isinstance(v, str) and '=' in v for v in values), 'ambiente_invalido')
    pairs = [v.split('=', 1) for v in values]
    require(len({k for k, _ in pairs}) == len(pairs), 'ambiente_duplicado')
    return dict(pairs)


def target_environment(live):
    env = env_map(live)
    audit.env_flags(live)
    env['SOCIALMEI_RELEASE_SHA'] = SHA
    # Explicitly preserve disabled behavior even when the old image omitted a flag.
    for name in audit.SENSITIVE_FLAGS:
        env[name] = 'false'
    env['SOCIALMEI_WAHA_INGRESS_MODE'] = 'disabled'
    return env


def invariant(row):
    config = row['Config']
    return {'host': row['HostConfig'], 'mounts': sorted(row.get('Mounts') or [], key=lambda m: m['Destination']),
            'networks': {name: {'aliases': sorted(set(info.get('Aliases') or []) - {row.get('Id'), str(row.get('Id', ''))[:12]}), 'ipam': info.get('IPAMConfig'), 'links': info.get('Links')} for name, info in row['NetworkSettings']['Networks'].items()},
            'config': {k: config.get(k) for k in ('Cmd', 'Entrypoint', 'WorkingDir', 'User', 'Healthcheck', 'ExposedPorts', 'StopSignal')}}


def candidate_model(before, service, tag, environment):
    result = copy.deepcopy(before)
    target = result['services'][service]
    target['image'] = tag
    if environment is not None:
        target['environment'] = environment
    return result


def literal_environment(environment):
    return {k: v.replace('$', '$$') for k, v in environment.items()}


def up(command, service):
    require(service in SERVICES, 'servico_fora_do_escopo')
    return command + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', service]


class Publisher:
    def __init__(self, folder):
        require(folder.parent == BACKUPS and folder.is_dir() and not folder.is_symlink(), 'pasta_invalida')
        require(folder.stat().st_uid == os.geteuid() and folder.stat().st_mode & 0o077 == 0, 'pasta_deve_ser_privada')
        self.folder = folder
        self.mutation_started = (folder / 'cutover-started.private.json').exists()
        self.lock = (BACKUPS / '.team-v33-publish.lock').open('a')
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def run(self, args, timeout=60):
        try:
            result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError('comando_indisponivel') from None
        require(result.returncode == 0, 'comando_falhou')
        return result.stdout

    def docker(self, *args, timeout=60):
        return audit.docker(*args, timeout=timeout)

    def inspect(self, name):
        rows = json.loads(self.docker('inspect', name))
        require(len(rows) == 1, 'objeto_docker_ambiguo')
        return rows[0]

    def write(self, name, value):
        path = self.folder / name
        require(not path.exists() and not path.is_symlink(), 'artefato_ja_existe')
        with path.open('x') as stream:
            os.chmod(path, 0o600)
            json.dump(value, stream, sort_keys=True, indent=2)

    def read(self, name):
        path = self.folder / name
        require(path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o077 == 0, 'artefato_privado_invalido')
        return json.loads(path.read_text())

    def others(self):
        rows = self.docker('ps', '-a', '--no-trunc', '--format', '{{.Names}} {{.ID}}').splitlines()
        return sorted(row for row in rows if row.split()[0] not in NAMES.values())

    def privacy_snapshot(self, *, public_only=False):
        result = {}
        for name in (('socialmei-caddy',) if public_only else ('socialmei-caddy', NAMES['team-gateway'])):
            active = json.loads(self.docker('exec', name, 'wget', '-qO-',
                                'http://127.0.0.1:2019/config/'))
            adapted = json.loads(self.docker('exec', name, 'caddy', 'adapt',
                                 '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'))
            require(active == adapted, 'caddy_ativo_diverge_do_arquivo')
            require(privacy_helper.protected(active), 'caddy_logs_sem_protecao')
            if name == NAMES['team-gateway']:
                require(not archive_helper.has_http_auth(active), 'gateway_com_http_basic')
            result[name] = hashlib.sha256(json.dumps(
                active, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return result

    def compose(self, row):
        labels = row['Config']['Labels']
        require(labels.get('com.docker.compose.project') == 'socialmei-team'
                and labels.get('com.docker.compose.project.working_dir') == str(ROOT), 'origem_compose_divergente')
        files = labels['com.docker.compose.project.config_files'].split(',')
        require(files and files[0] == str(ROOT / 'compose.team.yaml'), 'base_compose_divergente')
        require(all(Path(f).is_absolute() and Path(f).is_file() and not Path(f).is_symlink() for f in files), 'overlay_ausente')
        cmd = ['docker', '--host=unix:///var/run/docker.sock', 'compose', '--project-name', 'socialmei-team', '--env-file', str(ROOT / '.env.team')]
        for file in files:
            cmd += ['-f', file]
        return cmd, files

    def model(self, command):
        result = json.loads(self.run(command + ['config', '--format', 'json']))
        # Compose serializes literal dollars as $$ for safe re-input. Compare
        # effective environment values with Docker inspect, not this encoding.
        for service in result.get('services', {}).values():
            environment = service.get('environment') or {}
            for key, value in environment.items():
                if isinstance(value, str):
                    environment[key] = value.replace('$$', '$')
        return result

    def files(self, rows, compose_files):
        paths = {Path(p) for p in compose_files} | {ROOT / '.env.team'}
        for row in rows.values():
            for mount in row.get('Mounts') or []:
                if mount['Type'] != 'bind':
                    continue
                path = Path(mount['Source'])
                require(path.is_absolute() and path.exists() and not path.is_symlink(), 'montagem_invalida')
                if path.is_dir():
                    for item in path.rglob('*'):
                        require(not item.is_symlink(), 'montagem_com_symlink')
                        if item.is_file():
                            paths.add(item)
                else:
                    paths.add(path)
        require(all(p.is_file() and not p.is_symlink() for p in paths), 'configuracao_ausente')
        return {str(p): digest(p) for p in sorted(paths)}

    def prepare(self, bundle):
        require(shutil.disk_usage('/').free >= 4 * 1024**3, 'disco_insuficiente')
        require(not (self.folder / 'prepared.private.json').exists(), 'ja_preparado')
        audit.run_audit()
        receipt = image_helper.read_bundle(bundle)
        require(all(image_helper.local_image_status(receipt).values()), 'importar_imagens_primeiro')
        rows = {s: self.inspect(NAMES[s]) for s in SERVICES}
        archive_helper.database_target(rows['team-api'], self.inspect(audit.DB_NAME))
        saved = {'sha': SHA, 'services': {}, 'others': self.others(), 'bundle': str(bundle), 'bundle_sha256': digest(bundle), 'checkout': checkout_snapshot(), 'privacy': self.privacy_snapshot()}
        files = []
        expected_images = {}
        for service, row in rows.items():
            require(set(row['NetworkSettings']['Networks']) == NETWORKS[service], 'topologia_divergente')
            command, sources = self.compose(row)
            files += sources
            before = self.model(command)
            require(shape_helper.runtime_shape_matches(before, row, service), 'compose_runtime_divergente')
            configured = before['services'][service].get('environment') or {}
            require(all(env_map(row).get(k) == str(v) for k, v in configured.items()), 'ambiente_runtime_divergente')
            old_tag = row['Config']['Image']
            require(self.inspect(old_tag)['Id'] == row['Image'], 'tag_rollback_divergente')
            tag = f'socialmei-v33/{service}:{SHA}'
            image = self.inspect(tag)
            require(image.get('Os') == 'linux' and image.get('Architecture') == 'amd64'
                    and image.get('Config', {}).get('Labels', {}).get('org.opencontainers.image.revision') == SHA, 'imagem_candidata_divergente')
            # Preserve all runtime env, including inherited defaults; only revision/off flags may change.
            environment = target_environment(row) if service == 'team-api' else env_map(row)
            override = {'services': {service: {'image': tag, 'environment': literal_environment(environment)}}}
            self.write(service + '.override.private.json', override)
            candidate = command + ['-f', str(self.folder / (service + '.override.private.json'))]
            require(self.model(candidate) == candidate_model(before, service, tag, environment), 'delta_compose_inesperado')
            rollback_tag = f'socialmei-v33-rollback/{service}:{row["Id"][:12]}'
            self.docker('image', 'tag', row['Image'], rollback_tag)
            expected_images[rollback_tag] = row['Image']
            self.write(service + '.before.private.json', before)
            self.write(service + '.container.private.json', row)
            rollback_override = {'services': {service: {'image': rollback_tag, 'environment': literal_environment(env_map(row))}}}
            self.write(service + '.rollback.private.json', rollback_override)
            rollback_cmd = command + ['-f', str(self.folder / (service + '.rollback.private.json'))]
            require(self.model(rollback_cmd) == candidate_model(before, service, rollback_tag, env_map(row)), 'delta_rollback_inesperado')
            saved['services'][service] = {'container_id': row['Id'], 'old_image': row['Image'], 'new_image': image['Id'],
                'tag': tag, 'rollback_tag': rollback_tag, 'before_command': command, 'candidate_command': candidate,
                'rollback_command': rollback_cmd, 'environment': environment, 'old_environment': env_map(row), 'invariant': invariant(row)}
        saved['baseline_frontend_sha256'] = self.docker('exec', NAMES['team-gateway'], 'sha256sum', '/srv/frontend/socialmei-app.html').split()[0]
        saved['files'] = self.files(rows, files)
        saved['bind_directories'] = sorted({m['Source'] for row in rows.values() for m in row.get('Mounts') or [] if m['Type'] == 'bind' and Path(m['Source']).is_dir()})
        with tarfile.open(self.folder / 'runtime-config.tar.gz', 'w:gz') as archive:
            for path in saved['files']:
                archive.add(path, arcname=path.lstrip('/'), recursive=False)
        self.docker('image', 'save', '-o', str(self.folder / 'rollback.tar'), *expected_images, timeout=300)
        import gzip
        with (self.folder / 'rollback.tar').open('rb') as source, gzip.open(self.folder / 'rollback.tar.gz', 'wb', compresslevel=1) as dest:
            shutil.copyfileobj(source, dest, 1024**2)
        (self.folder / 'rollback.tar').unlink()
        archive_helper.verify_image_archive(self.folder / 'rollback.tar.gz', expected_images)
        saved['archive_images'] = expected_images
        saved['artifacts'] = {p.name: digest(p) for p in self.folder.iterdir() if p.is_file()}
        self.write('prepared.private.json', saved)
        self.guard(saved)
        return {'status': 'prepared', 'candidate_sha': SHA, 'services_changed': False, 'database_changed': False}

    def guard(self, saved, rollback=False, missing=()):
        require(saved['sha'] == SHA and set(saved['services']) == set(SERVICES), 'candidata_divergente')
        require(checkout_snapshot() == saved['checkout'], 'checkout_original_alterado')
        public_only = rollback and 'team-gateway' in missing
        expected_privacy = {k: v for k, v in saved['privacy'].items() if not public_only or k == 'socialmei-caddy'}
        require(self.privacy_snapshot(public_only=public_only) == expected_privacy, 'privacidade_caddy_alterada')
        audit.ledger_current(audit.prepared_source())
        require(digest(Path(saved['bundle'])) == saved['bundle_sha256'], 'pacote_alterado')
        receipt = image_helper.read_bundle(Path(saved['bundle']))
        require(all(image_helper.local_image_status(receipt).values()), 'imagens_importadas_divergentes')
        for directory in saved['bind_directories']:
            actual = {str(p) for p in Path(directory).rglob('*') if p.is_file()}
            require(not any(p.is_symlink() for p in Path(directory).rglob('*')), 'montagem_com_symlink')
            require(actual == {p for p in saved['files'] if Path(p).is_relative_to(directory)}, 'montagem_inventario_alterado')
        require(self.others() == saved['others'], 'outros_servicos_alterados')
        for path, value in saved['files'].items():
            require(Path(path).is_file() and not Path(path).is_symlink() and digest(Path(path)) == value, 'configuracao_alterada')
        for name, value in saved['artifacts'].items():
            require(Path(name).name == name and digest(self.folder / name) == value, 'artefato_alterado')
        archive_helper.verify_image_archive(self.folder / 'rollback.tar.gz', saved['archive_images'])
        for service, receipt in saved['services'].items():
            require(service in SERVICES, 'servico_fora_do_escopo')
            existing_names = self.docker('ps', '-a', '--format', '{{.Names}}').splitlines() if rollback else []
            live = self.inspect(NAMES[service]) if not rollback or NAMES[service] in existing_names else None
            require(live is not None or service in missing, 'servico_nao_tocado_ausente')
            if not rollback:
                require(live['Id'] == receipt['container_id'] and live['Image'] == receipt['old_image'], 'runtime_alterado')
            if live is not None:
                require(invariant(live) == receipt['invariant'], 'runtime_formato_alterado')
                require(live['Image'] in (receipt['old_image'], receipt['new_image']), 'imagem_runtime_desconhecida')
                require(env_map(live) in (receipt['old_environment'], receipt['environment']) if rollback else env_map(live) == receipt['old_environment'], 'runtime_ambiente_alterado')
            require(self.inspect(receipt['rollback_tag'])['Id'] == receipt['old_image'], 'rollback_imagem_alterada')
            require(self.inspect(receipt['tag'])['Id'] == receipt['new_image'], 'candidata_imagem_alterada')
            before = self.read(service + '.before.private.json')
            require(self.model(receipt['before_command']) == before, 'compose_alterado')
            require(self.model(receipt['candidate_command']) == candidate_model(before, service, receipt['tag'], receipt['environment']), 'candidata_compose_alterado')
            require(self.model(receipt['rollback_command']) == candidate_model(before, service, receipt['rollback_tag'], receipt['old_environment']), 'rollback_compose_alterado')
            command = receipt['before_command']
            require(receipt['candidate_command'] == command + ['-f', str(self.folder / (service + '.override.private.json'))]
                    and receipt['rollback_command'] == command + ['-f', str(self.folder / (service + '.rollback.private.json'))], 'comando_de_corte_alterado')

    def verify(self, saved, candidate):
        for service, receipt in saved['services'].items():
            row = None
            for attempt in range(30):
                row = self.inspect(NAMES[service])
                healthy = row['State'].get('Running') is True and (service != 'team-api' or row['State'].get('Health', {}).get('Status') == 'healthy')
                if healthy:
                    break
                time.sleep(2)
            require(healthy and row['Image'] == receipt['new_image' if candidate else 'old_image'], 'imagem_ou_saude_divergente')
            require(invariant(row) == receipt['invariant'], 'formato_runtime_divergente')
            require(env_map(row) == receipt['environment' if candidate else 'old_environment'], 'ambiente_divergente')
        require(checkout_snapshot() == saved['checkout'], 'checkout_original_alterado')
        require(self.privacy_snapshot() == saved['privacy'], 'privacidade_caddy_alterada')
        for path, value in saved['files'].items():
            require(digest(Path(path)) == value, 'configuracao_alterada')
        api = self.inspect(NAMES['team-api'])
        audit.env_flags(api)
        gw = self.inspect(NAMES['team-gateway'])
        audit.gateway_guard(gw, audit.container_summary(NAMES['team-gateway'], gw))
        if candidate:
            expected = digest(SOURCE / 'frontend/socialmei-app.html')
            got = self.docker('exec', NAMES['team-gateway'], 'sha256sum', '/srv/frontend/socialmei-app.html').split()[0]
            require(expected == got, 'frontend_divergente')
        self.verify_http(saved, candidate)
        require(self.others() == saved['others'], 'outros_servicos_alterados')
        audit.ledger_current(audit.prepared_source())

    def verify_http(self, saved, candidate):
        checks = [('/', 200), ('/api/v1/auth/registration', 200), ('/api/v1/clientes', 401), ('/health/db', 404)]
        if candidate:
            checks += [('/scripts/' + name, 200) for name in ('v22-bootstrap.js', 'v22-backend.js', 'v22-instagram.js', 'v22-instagram-publisher.js')]
        for path, expected_status in checks:
            passed = False
            for attempt in range(15):
                try:
                    try:
                        with urlopen(ORIGIN + path, timeout=10) as response:
                            code = response.status
                            require(not response.headers.get('WWW-Authenticate'), 'http_basic_inesperado')
                            if path == '/' or path.startswith('/scripts/'):
                                source = SOURCE / ('frontend/socialmei-app.html' if path == '/' else 'frontend' + path)
                                expected_hash = digest(source) if candidate else saved['baseline_frontend_sha256']
                                require(hashlib.sha256(response.read(4 * 1024**2)).hexdigest() == expected_hash, 'frontend_https_divergente')
                    except HTTPError as error:
                        code = error.code
                    if code == expected_status:
                        passed = True
                        break
                except OSError:
                    pass
                time.sleep(2)
            require(passed, 'https_divergente')

    def rollback(self, saved, touched=SERVICES):
        touched = tuple(touched)
        self.guard(saved, rollback=True, missing=touched)
        for service in touched:
            self.run(up(saved['services'][service]['rollback_command'], service), timeout=180)
        self.verify(saved, False)

    def apply(self):
        saved = self.read('prepared.private.json')
        available = next((int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')), 0)
        require(available >= 256 * 1024, 'memoria_insuficiente')
        require(not (self.folder / 'cutover-started.private.json').exists(), 'tentativa_ja_consumida')
        self.guard(saved)
        self.verify(saved, False)
        # A fresh database backup, though this image-only switch never writes SQL.
        output = self.run(['python3', 'tools/team-maintenance.py', 'backup'], timeout=300)
        matches = re.findall(r'/home/ubuntu/socialmei-backups/(team-auto-[0-9]{8}-[0-9]{6}-[a-z0-9]+)', output)
        require(len(set(matches)) == 1, 'recibo_backup_fresco_ausente')
        backup = BACKUPS / matches[0]
        proof = json.loads((backup / 'concluido.json').read_text())
        require(isinstance(proof.get('sha256'), dict) and 'equipe.dump' in proof['sha256'], 'backup_fresco_invalido')
        for name, value in proof['sha256'].items():
            require(Path(name).name == name and not (backup / name).is_symlink() and digest(backup / name) == value, 'backup_fresco_corrompido')
        self.guard(saved)
        touched = []
        self.write('cutover-started.private.json', {'status': 'started', 'sha': SHA})
        try:
            for service in SERVICES:
                touched.append(service)
                self.mutation_started = True
                self.run(up(saved['services'][service]['candidate_command'], service), timeout=180)
            self.verify(saved, True)
        except Exception:
            if touched:
                try:
                    self.rollback(saved, reversed(touched))
                except Exception:
                    self.write('rollback-failed.private.json', {'status': 'manual_recovery_required', 'database_restored': False})
                    raise RuntimeError('rollback_exige_intervencao') from None
            raise RuntimeError('corte_falhou_rollback_verificado') from None
        self.write('installed.private.json', {'sha': SHA, 'status': 'verified', 'database_changed': False, 'providers_activated': False, 'browser_login': 'not_verified'})
        return {'status': 'published', 'candidate_sha': SHA, 'database_changed': False, 'providers_activated': False, 'browser_login': 'not_verified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['team'], required=True)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    for name in ('prepare', 'inspect', 'apply', 'rollback'):
        modes.add_argument('--' + name, action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        task = Publisher(args.folder)
        if args.prepare:
            require(args.bundle is not None, 'pacote_obrigatorio')
            result = task.prepare(args.bundle)
        elif args.apply:
            result = task.apply()
        else:
            saved = task.read('prepared.private.json')
            task.guard(saved, rollback=args.rollback, missing=SERVICES if args.rollback else ())
            if args.rollback:
                task.mutation_started = True
                task.rollback(saved)
            result = {'status': 'rollback_verified' if args.rollback else 'inspection_passed', 'database_changed': False}
        print(json.dumps(result))
    except Exception as error:
        code = str(error) if str(error) in ('rollback_exige_intervencao', 'corte_falhou_rollback_verificado') else 'private_verification_failed'
        print(json.dumps({'status': 'blocked', 'details': code, 'production_change_possible': getattr(locals().get('task'), 'mutation_started', False) and code != 'corte_falhou_rollback_verificado', 'rollback_verified': code == 'corte_falhou_rollback_verificado', 'database_restore_executed': False}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
