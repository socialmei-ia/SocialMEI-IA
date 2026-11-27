"""Verify captured production files and optionally build one image without deploying."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / 'deploy/production-overlay/20261127'


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


def build(role, entry):
    image = entry['image']
    base = f'socialmei-overlay-base:{role}-{image[7:19]}'
    subprocess.run(['docker', 'image', 'tag', image, base], check=True)
    identity = subprocess.check_output(['docker', 'image', 'inspect', '-f', '{{.Id}}', base], text=True).strip()
    if identity != image:
        raise RuntimeError('Frozen image mismatch')
    dockerfile = [f'FROM {base}']
    dockerfile.extend('COPY ' + json.dumps([name.lstrip('/'), name]) for name in sorted(entry['files']))
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for name in entry['files']:
            rel = name.lstrip('/')
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / role / rel).read_bytes())
        (root / 'Dockerfile').write_text('\n'.join(dockerfile) + '\n', encoding='utf-8')
        subprocess.run(['docker', 'build', '--pull=false', '--network=none',
                        '-t', f'socialmei-production-overlay:{role}-20261127', str(root)], check=True)


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', choices=sorted(manifest), help='Requires the exact local base image')
    args = parser.parse_args()
    verify(manifest)
    print(f'Verified {sum(len(e["files"]) for e in manifest.values())} files across {len(manifest)} roles')
    if args.build:
        build(args.build, manifest[args.build])
