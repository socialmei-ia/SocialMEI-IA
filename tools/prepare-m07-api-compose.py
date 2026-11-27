"""Freeze the observed API configuration for paired publication and rollback review."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import re
import subprocess

NAME = 'socialmei-team-team-api-1'
SERVICE = 'team-api'
EXTRA_NETWORK = 'socialmei-instagram-ai-private'
EXTRA_ALIAS = 'socialmei-ig-api'
ROOT = Path('/var/lib/socialmei/production-consolidation-m07')
PRIVATE_FILES = {
    '/app/.human-gows-key.private',
    '/app/.socialmei-booking-signing.private',
    '/app/.instagram-ai-runtime.private.json',
    '/app/.socialmei-content-ai.private.json',
    '/app/.socialmei-commercial-analysis.private.json',
}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def docker(*args, cwd=None):
    result = subprocess.run(['docker', *args], capture_output=True, cwd=cwd, timeout=25)
    require(result.returncode == 0, 'DOCKER_READ_FAILED')
    return result.stdout


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, sort_keys=True, indent=2)


def prepare(capture, output, images):
    raw = json.loads((capture/'runtime.private.json').read_text())
    baseline = raw[0]
    current = json.loads(docker('inspect', NAME))[0]
    require(current['Id'] == baseline['Id'] and current['State']['Running'], 'API_CHANGED')
    labels = current['Config']['Labels']
    work = labels['com.docker.compose.project.working_dir']
    config = labels['com.docker.compose.project.config_files'].split(',')
    cmd = ['compose', '--project-directory', work, '-p', 'socialmei-team']
    files = json.loads((capture/'index.private.json').read_text())
    require(all(sha(Path(row['source'])) == row['sha256'] for row in files['compose']), 'LIVE_COMPOSE_CHANGED')
    for path in config:
        cmd += ['-f', path]
    effective = json.loads(docker(*cmd, 'config', '--format', 'json', cwd=work))
    service = effective['services'][SERVICE]
    require(json.loads(docker('image', 'inspect', service['image']))[0]['Id'] == current['Image'], 'LIVE_IMAGE_CHANGED')
    actual_mounts = sorted((row['Source'], row['Destination'], row['RW']) for row in current['Mounts'])
    expected_mounts = sorted((row['source'], row['target'], not row.get('read_only', False))
                             for row in service['volumes'] if row['type']=='bind')
    require(expected_mounts == actual_mounts and len(actual_mounts) == len(service['volumes']), 'LIVE_BINDS_CHANGED')
    env = dict(row.split('=',1) for row in current['Config']['Env'])
    require(all(env.get(k)==v for k,v in service['environment'].items()), 'LIVE_ENV_CHANGED')
    require(env.get('SOCIALMEI_INSTAGRAM_INBOUND_MEDIA_ENABLED') != 'YES'
            and env.get('SOCIALMEI_WHATSAPP_MEDIA_COMMERCIAL_ENABLED') != 'YES', 'UNEXPECTED_MEDIA_ACTIVATION')
    networks = current['NetworkSettings']['Networks']
    staged_networks = {}
    for logical in service['networks']:
        name = effective['networks'][logical]['name']
        require(name in networks, 'MISSING_NETWORK')
        planned = set((service['networks'][logical] or {}).get('aliases', ())) | {NAME, SERVICE}
        require(planned == set(networks[name]['Aliases'] or ()), 'CONFIGURED_ALIAS_DRIFT')
        staged_networks[logical] = {'external': True, 'name': name}
    extra = set(networks) - {net['name'] for net in staged_networks.values()}
    require(extra == {EXTRA_NETWORK} and set(networks[EXTRA_NETWORK]['Aliases'] or ()) == {EXTRA_ALIAS},
            'UNEXPECTED_ADDITIONAL_NETWORK')
    staged_networks['ig_private'] = {'external': True, 'name': EXTRA_NETWORK}
    service['networks']['ig_private'] = {'aliases': [EXTRA_ALIAS]}
    service.pop('depends_on', None)
    service['container_name'] = NAME
    require({row['destination'] for row in files['files']} == PRIVATE_FILES, 'MISSING_PRIVATE_MOUNTS')
    output.mkdir(mode=0o700)
    evidence = {}
    for row in files['files']:
        source = Path(row['path'])
        target = output/('captured-'+Path(row['destination']).name)
        require(source.parent == capture and not source.is_symlink() and sha(source)==row['sha256'], 'PRIVATE_SOURCE_CHANGED')
        actual = docker('exec', NAME, 'cat', row['destination'])
        require(hashlib.sha256(actual).hexdigest()==row['sha256'], 'LIVE_PRIVATE_FILE_CHANGED')
        target.write_bytes(actual)
        os.chown(target, *(int(value) for value in row['owner']))
        target.chmod(int(row['mode'],8))
        service['volumes'].append({'type':'bind','source':str(target),'target':row['destination'],'read_only':True})
        evidence[row['destination']] = row['sha256']
    manifests = {}
    for role,image in images.items():
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', image) is not None, 'IMAGE_ID_REQUIRED')
        require(json.loads(docker('image','inspect',image))[0]['Id']==image, 'PINNED_IMAGE_UNAVAILABLE')
        path = output/(role+'.compose.private.json')
        write(path, {'name':'socialmei-team','services':{SERVICE:{**service,'image':image}},'networks':staged_networks})
        docker('compose', '-f', str(path), 'config', '--quiet')
        manifests[role] = sha(path)
    write(output/'gate.private.json', {'compose':manifests, 'private_content':evidence,
          'original_id':current['Id'],'original_image':current['Image'],'images':images,
          'additional_network':EXTRA_NETWORK,'additional_alias':EXTRA_ALIAS,'mutated_api':False})
    print(json.dumps({'output':str(output),'private_mount_count':len(evidence),'networks':len(staged_networks),'composes':manifests}))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate',required=True)
    parser.add_argument('--rollback',required=True)
    args=parser.parse_args()
    capture=args.capture.resolve(strict=True)
    parent=args.output.parent.resolve(strict=True)
    require(ROOT in capture.parents and ROOT in parent.parents and os.geteuid()==0, 'PRIVATE_RELEASE_CONTEXT_REQUIRED')
    prepare(capture, parent/args.output.name, {'candidate':args.candidate,'rollback':args.rollback})


if __name__=='__main__':
    try:
        main()
    except (RuntimeError,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as error:
        raise SystemExit(str(error) if isinstance(error,RuntimeError) else type(error).__name__) from None
