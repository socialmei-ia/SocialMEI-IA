#!/usr/bin/env python3
"""Prepare, publish or roll back the M07 gateway-only slice on the approved host."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.request import urlopen

ROOT = Path('/var/lib/socialmei/production-consolidation-m07')
NAME = 'socialmei-team-team-gateway-1'
SERVICE = 'team-gateway'
PROJECT = 'socialmei-team'
PUBLIC = 'https://socialmei-ia.54-94-213-7.sslip.io'
FILES = {'socialmei-app.html', 'scripts/v22-bootstrap.js', 'scripts/v22-agenda.js'}
DELTAS = {'A /config/caddy/autosave.json', 'A /data/caddy/instance.uuid', 'A /data/caddy/last_clean.json'}
GENERATED_DIRECTORIES = {'/data/caddy/locks', '/etc', '/etc/caddy', '/etc/caddy/private'}


class Gate(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Gate(reason)


def run(*args, cwd=None, timeout=130):
    p = subprocess.run(args, cwd=cwd, timeout=timeout, capture_output=True)
    require(p.returncode == 0, 'COMMAND_FAILED_' + '_'.join(args[:2]))
    return p.stdout


def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2), encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def container_files(container, assets):
    return {
        asset: digest(run('docker', 'exec', container, 'cat', '/srv/frontend/' + asset))
        for asset in sorted(assets)
    }


def runtime_identity(item):
    return {
        'entrypoint': item['Config']['Entrypoint'],
        'cmd': item['Config']['Cmd'],
        'env': sorted(item['Config']['Env'] or []),
        'user': item['Config']['User'],
        'mounts': sorted([m['Type'], m['Source'], m['Destination'], m['RW']] for m in item['Mounts']),
        'networks': {k: sorted(v['Aliases'] or []) for k, v in item['NetworkSettings']['Networks'].items()},
        'restart': item['HostConfig']['RestartPolicy'],
        'ports': item['HostConfig']['PortBindings'] or {},
    }


def others():
    rows = run('docker', 'ps', '-a', '--no-trunc', '--format', '{{.Names}} {{.ID}}').decode().splitlines()
    return sorted(row for row in rows if not row.startswith(NAME + ' '))


def docker_compose(path):
    return ['docker', 'compose', '-p', PROJECT, '-f', str(path)]


def same_public(assets):
    for asset, expected in assets.items():
        with urlopen(PUBLIC + '/frontend/' + asset, timeout=8) as response:
            require(response.status == 200 and digest(response.read(4_000_000)) == expected,
                    'PUBLIC_ASSET_MISMATCH')
    with urlopen(PUBLIC + '/api/v1/auth/session', timeout=8) as response:
        require(response.status == 200, 'AUTH_SESSION_UNREACHABLE')


def healthy(image, identity, assets):
    for _ in range(18):
        try:
            current = inspect(NAME)
            require(current['State']['Running'] and current['Image'] == image, 'GATEWAY_NOT_RUNNING')
            require(runtime_identity(current) == identity, 'GATEWAY_RUNTIME_DRIFT')
            require(container_files(NAME, assets) == assets, 'GATEWAY_CONTAINER_ASSET_MISMATCH')
            same_public(assets)
            return
        except (Gate, OSError):
            time.sleep(2)
    raise Gate('GATEWAY_HEALTH_FAILED')


def switch(path):
    run(*docker_compose(path), 'up', '-d', '--no-deps', '--no-build',
        '--pull', 'never', '--force-recreate', SERVICE)


def prepare(folder):
    bundle = folder / 'bundle'
    stage = read(bundle/'stage/manifest.json')
    captured = read(bundle/'capture.json')['gateway']
    require(set(stage['output']) == FILES and stage['base'] == captured['image'], 'STAGE_IDENTITY_MISMATCH')
    require(re.fullmatch(r'[a-f0-9]{40}', stage['source']) is not None, 'SOURCE_IDENTITY_MISSING')
    base = stage['base']
    current = inspect(NAME)
    require(current['Image'] == base and current['State']['Running'], 'BASE_RUNTIME_MISMATCH')
    original = {p.removeprefix('/srv/frontend/'): h for p, h in captured['files'].items()
                if p.startswith('/srv/frontend/')}
    require(len(original) == len(captured['files']), 'UNEXPECTED_CAPTURE_PATH')
    require(container_files(NAME, original) == original, 'LIVE_FRONTEND_DRIFT')
    for line in run('docker', 'diff', NAME).decode().splitlines():
        _, filename = line.split(' ', 1)
        if filename in GENERATED_DIRECTORIES:
            run('docker','exec',NAME,'test','-d',filename)
            continue
        if filename.removeprefix('/srv/frontend/') in original or line in DELTAS:
            continue
        require(any(path.startswith(filename.rstrip('/') + '/') for path in [
            *captured['files'], *(d.split(' ', 1)[1] for d in DELTAS),
        ]), 'UNEXPECTED_GATEWAY_WRITABLE_LAYER_CHANGE')
    labels = current['Config']['Labels']
    require(labels['com.docker.compose.project'] == PROJECT, 'WRONG_COMPOSE_PROJECT')
    cwd = labels['com.docker.compose.project.working_dir']
    files = labels['com.docker.compose.project.config_files'].split(',')
    command = ['docker', 'compose', '--project-directory', cwd, '-p', PROJECT]
    for file in files:
        command.extend(('-f', file))
    live = json.loads(run(*command, 'config', '--format', 'json', cwd=cwd))
    service = copy.deepcopy(live['services'][SERVICE])
    require(inspect(service['image'])['Id'] == base, 'COMPOSE_SOURCE_IMAGE_MISMATCH')
    identity = runtime_identity(current)
    require(not identity['ports'] and all(m[0] == 'bind' for m in identity['mounts']), 'UNEXPECTED_PORT_OR_VOLUME')
    planned_mounts = sorted([m['type'], m['source'], m['target'], not m.get('read_only', False)]
                           for m in service.get('volumes', []))
    require(planned_mounts == identity['mounts'], 'COMPOSE_BIND_DRIFT')
    networks = {}
    for logical in service.get('networks', {}):
        name = live['networks'][logical]['name']
        require(name in identity['networks'], 'UNEXPECTED_COMPOSE_NETWORK')
        expected = sorted(set([NAME, SERVICE, *(service['networks'][logical] or {}).get('aliases', [])]))
        require(expected == identity['networks'][name], 'COMPOSE_NETWORK_ALIAS_DRIFT')
        networks[logical] = {'name': name, 'external': True}
    require(len(networks) == len(identity['networks']), 'COMPOSE_NETWORK_COUNT_DRIFT')
    require('build' not in service and not service.get('volumes_from'), 'UNEXPECTED_COMPOSE_BUILD')
    service.pop('depends_on', None)
    service['container_name'] = NAME
    before = others()
    images = {}
    base_tag = 'socialmei-production-overlay:m07-gateway-original-base'
    run('docker','image','tag',base,base_tag)
    for name, assets in (('rollback', original), ('candidate', original | stage['output'])):
        context = folder/name
        context.mkdir(mode=0o700, exist_ok=False)
        dockerfile = [f'FROM {base_tag}']
        for asset, expected in sorted(assets.items()):
            source = bundle/('stage' if name=='candidate' and asset in FILES else 'frozen')/'frontend'/asset
            require(file_digest(source)==expected, 'PACKAGE_FILE_HASH_MISMATCH')
            dest = context/'frontend'/asset
            dest.parent.mkdir(exist_ok=True, parents=True)
            dest.write_bytes(source.read_bytes())
            dockerfile.append('COPY '+json.dumps(['frontend/'+asset,'/srv/frontend/'+asset]))
        (context/'Dockerfile').write_text('\n'.join(dockerfile)+'\n', encoding='utf-8')
        tag = 'socialmei-production-overlay:m07-gateway-'+name
        run('docker','build','--pull=false','--network=none','-t',tag,str(context))
        ident = inspect(tag)['Id']
        images[name] = ident
        spec = {'name': PROJECT, 'services': {SERVICE: {**service, 'image': tag}}, 'networks': networks}
        path = folder / (name+'.compose.private.json')
        write(path, spec)
        run(*docker_compose(path), 'config', '--quiet')
    # The original agenda script lives in the base image; capture its live digest for rollback.
    rollback = {name: original[name] for name in FILES if name in original}
    rollback.update(container_files(NAME, FILES - set(rollback)))
    same_public(rollback)
    require(others() == before and inspect(NAME)['Id']==current['Id'], 'RUNTIME_CHANGED_DURING_PREPARATION')
    plan = {
        'source': stage['source'], 'original_id': current['Id'], 'images': images,
        'runtime_private': identity, 'others': before,
        'compose_hashes': {role: file_digest(folder/(role+'.compose.private.json'))
                           for role in ('candidate','rollback')},
        'expected': stage['output'], 'old': rollback,
        'original_files': original,
        'configuration_hashes': {p: file_digest(p) for p in files},
        'bind_hashes': {m['Source']: file_digest(m['Source']) for m in current['Mounts'] if Path(m['Source']).is_file()},
        'capture': str(folder.parent/'receipt.json'),
    }
    write(folder/'plan.private.json', plan)
    print(json.dumps({'plan_sha256':file_digest(folder/'plan.private.json'),'images':images,'files':len(FILES)}))


def execute(folder, expected, *, rollback=False):
    file = folder/'plan.private.json'
    require(file_digest(file) == expected, 'PLAN_HASH_CHANGED')
    plan = read(file)
    receipts = read(Path(plan['capture']))
    require(receipts['restored_isolated'] and receipts['row_counts_equal']
            and file_digest(Path(plan['capture']).parent/'prechange041.dump') == receipts['sha256'], 'BACKUP_RECEIPT_INVALID')
    require(all(file_digest(p)==h for p,h in plan['configuration_hashes'].items()), 'COMPOSE_FILES_CHANGED')
    require(all(file_digest(p)==h for p,h in plan['bind_hashes'].items()), 'PRIVATE_BIND_FILES_CHANGED')
    for role in ('candidate','rollback'):
        require(file_digest(folder/(role+'.compose.private.json')) == plan['compose_hashes'][role], 'FROZEN_COMPOSE_CHANGED')
        require(inspect('socialmei-production-overlay:m07-gateway-'+role)['Id'] == plan['images'][role], 'IMAGE_CHANGED')
    live = inspect(NAME)
    require(rollback or live['Id'] == plan['original_id'], 'ORIGINAL_GATEWAY_CHANGED')
    require(runtime_identity(live)==plan['runtime_private'] and others()==plan['others'], 'LIVE_RUNTIME_DRIFT')
    if not rollback:
        require(container_files(NAME,plan['original_files'])==plan['original_files'], 'EFFECTIVE_GATEWAY_BYTES_CHANGED')
        try:
            switch(folder/'candidate.compose.private.json')
            healthy(plan['images']['candidate'],plan['runtime_private'],plan['expected'])
            require(others()==plan['others'], 'OTHER_CONTAINERS_CHANGED')
        except Exception:
            switch(folder/'rollback.compose.private.json')
            healthy(plan['images']['rollback'],plan['runtime_private'],plan['old'])
            write(folder/'result.json',{'status':'rolled_back','source':plan['source']})
            raise Gate('CUTOVER_FAILED_ROLLBACK_VERIFIED') from None
        write(folder/'result.json',{'status':'published','source':plan['source'],'image':plan['images']['candidate']})
        print('GATEWAY_ONLY_PUBLISHED')
    else:
        switch(folder/'rollback.compose.private.json')
        healthy(plan['images']['rollback'],plan['runtime_private'],plan['old'])
        write(folder/'result.json',{'status':'rolled_back','source':plan['source']})
        print('GATEWAY_ROLLBACK_VERIFIED')


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare','apply','rollback'])
    parser.add_argument('folder', type=Path)
    parser.add_argument('--plan-sha256')
    args=parser.parse_args()
    folder=args.folder.resolve(strict=True)
    require(ROOT in folder.parents and folder.stat().st_uid==0 and folder.stat().st_mode&0o077==0, 'PRIVATE_FOLDER_REQUIRED')
    with (ROOT/'.gateway-m07.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.operation=='prepare':
            prepare(folder)
        else:
            require(bool(re.fullmatch(r'[a-f0-9]{64}', args.plan_sha256 or '')), 'PLAN_HASH_REQUIRED')
            execute(folder,args.plan_sha256,rollback=args.operation=='rollback')


if __name__=='__main__':
    try:
        main()
    except (Gate, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(str(exc) if isinstance(exc, Gate) else type(exc).__name__) from None
