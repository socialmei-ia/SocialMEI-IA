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
API_INBOX_FIXES = ('/app/message_enrichment.py', '/app/instagram_inbound_media.py')
EDITORIAL_API = ('/app/instagram_publishing.py', '/app/instagram_publication_worker.py')
EDITORIAL_GATEWAY = '/srv/frontend/scripts/v22-instagram-publisher.js'
COMMERCIAL_API = ('/app/opportunities.py', '/app/sales_data.py', '/app/shared_data.py')
COMMERCIAL_GATEWAY = ('/srv/frontend/scripts/v22-frame.js', '/srv/frontend/telas/oportunidades.html')
MANAGEMENT_API = ('/app/finance_reporting.py',)
MANAGEMENT_GATEWAY = ('/srv/frontend/scripts/v22-finance-reporting.js', '/srv/frontend/scripts/lia.js')
MENU_MEDIA_FILES = ('/app/whatsapp_media_intent.py',)
MENU_MEDIA_PATCH = REPO / 'deploy/production-candidates/whatsapp-media.patch'
INSTAGRAM_MEDIA_PATCH = REPO / 'deploy/production-candidates/instagram-media.patch'
MEDIA_COMMERCIAL_PATCH = REPO / 'deploy/production-candidates/media-commercial.patch'


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


def build(role, entry, *, gateway_fixes=False, inbox_fixes=False, whatsapp_media=False, media_commercial=False, instagram_media=False, editorial=False, commercial=False, management=False):
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
    if whatsapp_media or media_commercial:
        destinations.update(MENU_MEDIA_FILES)
    if editorial:
        destinations.update(EDITORIAL_API if role == 'api' else (EDITORIAL_GATEWAY,))
    if commercial:
        destinations.update(COMMERCIAL_API if role == 'api' else COMMERCIAL_GATEWAY)
    if management:
        destinations.update(MANAGEMENT_API if role == 'api' else MANAGEMENT_GATEWAY)
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
            if (whatsapp_media or media_commercial) and name in MENU_MEDIA_FILES:
                source = REPO / 'python-service' / Path(name).name
            data = source.read_bytes() if source.is_file() else None
            if editorial and role == 'api' and name in EDITORIAL_API:
                data = (REPO / 'python-service' / Path(name).name).read_bytes()
                if name == EDITORIAL_API[0]:
                    marker = b'# SM_CONTENT_AI_V1\n'
                    _, found, content_ai = source.read_bytes().replace(b'\r\n', b'\n').partition(marker)
                    if not found:
                        raise RuntimeError('Missing production content AI route')
                    data = data.rstrip() + b'\n\n' + marker + content_ai
            if editorial and name == EDITORIAL_GATEWAY:
                data = (REPO / name.removeprefix('/srv/')).read_bytes()
            if commercial and role == 'api' and name in COMMERCIAL_API:
                data = (REPO / 'python-service' / Path(name).name).read_bytes()
            if commercial and name in COMMERCIAL_GATEWAY:
                data = (REPO / name.removeprefix('/srv/')).read_bytes()
            if management and name in MANAGEMENT_API:
                data = (REPO / 'python-service' / Path(name).name).read_bytes()
            if management and name in MANAGEMENT_GATEWAY:
                data = (REPO / name.removeprefix('/srv/')).read_bytes()
            if data is None:
                raise FileNotFoundError(source)
            target.write_bytes(data)
            if gateway_fixes and name in GATEWAY_FIXES:
                print(f'{hashlib.sha256(data).hexdigest()}  {name}')
        patches = [(whatsapp_media, MENU_MEDIA_PATCH), (media_commercial, MEDIA_COMMERCIAL_PATCH),
                   (instagram_media, INSTAGRAM_MEDIA_PATCH)]
        for active, patch in patches:
            if active:
                subprocess.run(['git', 'apply', '--no-index', str(patch)], cwd=root, check=True)
        (root / 'Dockerfile').write_text('\n'.join(dockerfile) + '\n', encoding='utf-8')
        tag = f'socialmei-production-overlay:{role}-20261127' + ('-candidate' if gateway_fixes or inbox_fixes or whatsapp_media or media_commercial else '')
        if editorial:
            tag += '-editorial'
        if commercial:
            tag += '-commercial'
        if management:
            tag += '-management'
        subprocess.run(['docker', 'build', '--pull=false', '--network=none', '-t', tag, str(root)], check=True)


if __name__ == '__main__':
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', choices=sorted(manifest), help='Requires the exact local base image')
    parser.add_argument('--gateway-fixes', action='store_true', help='Include current app fixes in a separate gateway candidate')
    parser.add_argument('--inbox-fixes', action='store_true', help='Include inbox restoration API in a separate candidate, requires 043')
    parser.add_argument('--whatsapp-media', action='store_true', help='Include WhatsApp media planning, requires 042 and an activation cutoff')
    parser.add_argument('--media-commercial', action='store_true', help='Include bounded WhatsApp media evidence in the API commercial queue')
    parser.add_argument('--instagram-media', action='store_true', help='Include opt-in Instagram attachment ingress (requires --inbox-fixes and 047)')
    parser.add_argument('--editorial', action='store_true', help='Include Instagram photo scheduler, requires 048 for activation')
    parser.add_argument('--commercial', action='store_true', help='Include opportunity-to-sale conversion')
    parser.add_argument('--management', action='store_true', help='Include finance, MEI reporting, search and Lia updates')
    args = parser.parse_args()
    if args.management and (args.build not in {'api','gateway'} or (args.build == 'gateway' and not args.gateway_fixes)):
        parser.error('--management requires --build api or --build gateway --gateway-fixes')
    if args.commercial and (args.build not in {'api','gateway'} or (args.build == 'gateway' and not args.gateway_fixes)):
        parser.error('--commercial requires --build api or --build gateway --gateway-fixes')
    if args.editorial and args.build not in {'api','gateway'}:
        parser.error('--editorial requires --build api or gateway')
    if args.instagram_media and (args.build != 'api' or not args.inbox_fixes or not args.media_commercial):
        parser.error('--instagram-media requires --build api --inbox-fixes --media-commercial')
    if args.media_commercial and args.build != 'api':
        parser.error('--media-commercial requires --build api')
    if args.whatsapp_media and args.build != 'menu':
        parser.error('--whatsapp-media requires --build menu')
    if args.gateway_fixes and args.build != 'gateway':
        parser.error('--gateway-fixes requires --build gateway')
    if args.inbox_fixes and args.build != 'api':
        parser.error('--inbox-fixes requires --build api')
    verify(manifest)
    print(f'Verified {sum(len(e["files"]) for e in manifest.values())} files across {len(manifest)} roles')
    if args.build:
        build(args.build, manifest[args.build], gateway_fixes=args.gateway_fixes, inbox_fixes=args.inbox_fixes, whatsapp_media=args.whatsapp_media, media_commercial=args.media_commercial, instagram_media=args.instagram_media, editorial=args.editorial, commercial=args.commercial, management=args.management)
