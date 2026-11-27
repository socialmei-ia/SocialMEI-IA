"""Build the independently deployable Agenda/business slice of the consolidated gateway."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[1]
FROZEN = REPO / 'deploy/production-overlay/20261127'
FILES = ('socialmei-app.html', 'scripts/v22-bootstrap.js', 'scripts/v22-agenda.js')
OLD_REV = b'795-agenda-1'
NEW_REV = b'm07-agenda-negocio-1'
OLD_CARD = b'function meiCard(){const m='
NEW_CARD = b"function meiCard(){if(window.SocialMEIAuth?.remote)return '';const m="


def replace_once(data, old, new):
    if data.count(old) != 1:
        raise ValueError('Frozen gateway source diverged')
    return data.replace(old, new, 1)


def prepare(folder):
    manifest = json.loads((FROZEN / 'manifest.json').read_text(encoding='utf-8'))['gateway']
    frozen = FROZEN / 'gateway/srv/frontend'
    app, bootstrap, agenda = FILES
    snapshots = {}
    for name in (app, bootstrap):
        data = (frozen / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != manifest['files']['/srv/frontend/'+name]:
            raise ValueError('Frozen gateway digest mismatch')
        marker = b'scripts/v22-bootstrap.js?v=' if name == app else b'scripts/v22-agenda.js?v='
        snapshots[name] = replace_once(data, marker+OLD_REV, marker+NEW_REV)
    snapshots[app] = replace_once(snapshots[app], OLD_CARD, NEW_CARD)
    snapshots[agenda] = (REPO / 'frontend' / agenda).read_bytes()
    folder.mkdir(parents=False, exist_ok=False)
    files = {}
    for name, data in snapshots.items():
        file = folder / 'frontend' / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        files[name] = hashlib.sha256(data).hexdigest()
    source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    (folder / 'manifest.json').write_text(json.dumps({
        'source': source, 'base': manifest['image'], 'output': files,
        'production_source': {name: manifest['files']['/srv/frontend/'+name] for name in (app,bootstrap)},
    }, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    prepare(parser.parse_args().output)
