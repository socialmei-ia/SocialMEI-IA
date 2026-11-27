"""Verify captured production files and optionally build one image without deploying."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / 'deploy/production-overlay/20261127'
REPO = ROOT.parents[2]
GATEWAY_FIXES = (
    '/srv/frontend/socialmei-app.html',
    '/srv/frontend/scripts/v22-agenda.js',
    '/srv/frontend/scripts/v22-backend.js',
    '/srv/frontend/scripts/v22-bootstrap.js',
    '/srv/frontend/scripts/v79-central.js',
)
API_INBOX_FIXES = ('/app/message_enrichment.py',)


def verify(manifest):
    for role, entry in manifest.items():
        if not re.fullmatch(r'[a-z]+', role) or not re.fullmatch(r'sha256:[a-f0-9]{64}', entry['image']):
            raise ValueError('Invalid role or base image identity')
        for name, digest in entry['files'].items():
            path = PurePosixPath(name)
            if not path.is_absolute() or '..' in path.parts:
                raise ValueError('Invalid overlay destination')
            source = ROOT / role / name.lstrip('/')
            if source.is_symlink() or not source.resolve().is_relative_to(ROOT / role):
                raise ValueError('Invalid source path')
            if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise ValueError(f'Source hash mismatch: {role}:{name}')


def build(role, entry, *, gateway_fixes=False, inbox_fixes=False):
    image = entry['image']
    base = f'socialmei-overlay-base:{role}-{image[7:19]}'
    subprocess.run(['docker', 'image', 'tag', image, base], check=True)
    identity = subprocess.check_output(['docker', 'image', 'inspect', '-f', '{{.Id}}', base], text=True).strip()
    if identity != image:
        raise RuntimeError('Frozen image mismatch')
    dockerfile = [f'FROM {base}']
    destinations = set(entry['files'])
    if gateway_fixes:
        destinations.update(GATEWAY_FIXES)
    if inbox_fixes:
        destinations.update(API_INBOX_FIXES)
    dockerfile.extend('COPY ' + json.dumps([name.lstrip('/'), name]) for name in sorted(destinations))
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name in sorted(destinations):
            rel = name.lstrip('/')
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            source = ROOT / role / rel
            if gateway_fixes and name in GATEWAY_FIXES:
                source = REPO / name.removeprefix('/srv/')
            if inbox_fixes and name in API_INBOX_FIXES:
                source = REPO / 'python-service' / Path(name).name
            data = source.read_bytes()
            target.write_bytes(data)
            if gateway_fixes and name in GATEWAY_FIXES:
                print(f'{hashlib.sha256(data).hexdigest()}  {name}')
        (root / 'Dockerfile').write_text('\n'.join(dockerfile) + '\n', encoding='utf-8')
        tag = f'socialmei-production-overlay:{role}-20261127' + ('-candidate' if gateway_fixes or inbox_fixes else '')
        subprocess.run(['docker', 'build', '--pull=false', '--network=none', '-t', tag, str(root)], check=True)


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', choices=sorted(manifest), help='Requires the exact local base image')
    parser.add_argument('--gateway-fixes', action='store_true', help='Include current app fixes in a separate gateway candidate')
    parser.add_argument('--inbox-fixes', action='store_true', help='Include inbox restoration API in a separate candidate, requires 043')
    args = parser.parse_args()
    if args.gateway_fixes and args.build != 'gateway':
        parser.error('--gateway-fixes requires --build gateway')
    if args.inbox_fixes and args.build != 'api':
        parser.error('--inbox-fixes requires --build api')
    verify(manifest)
    print(f'Verified {sum(len(e["files"]) for e in manifest.values())} files across {len(manifest)} roles')
    if args.build:
        build(args.build, manifest[args.build], gateway_fixes=args.gateway_fixes, inbox_fixes=args.inbox_fixes)
