"""File-only liveness for the single Instagram sender; no database probes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket

FOLDER = Path('/run/socialmei/instagram-menu-state')


def heartbeat(status, read_status, *, folder=FOLDER):
    path = folder / 'health.json'
    temporary = folder / 'health.tmp'
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump({'worker': socket.gethostname(), 'status': status, 'read_status': read_status,
                   'heartbeat_at': datetime.now(timezone.utc).isoformat()}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def healthy(*, folder=FOLDER, now=None):
    try:
        state = json.loads((folder / 'state.json').read_text())
        health = json.loads((folder / 'health.json').read_text())
        stamp = datetime.fromisoformat(health['heartbeat_at'])
        if stamp.tzinfo is None:
            return False
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        return (state.get('status') == 'running' and health.get('status') == 'running'
                and health.get('read_status') == 'ready'
                and health.get('worker') == socket.gethostname() and -5 <= age <= 120)
    except (OSError, ValueError, TypeError, KeyError):
        return False


if __name__ == '__main__':
    raise SystemExit(0 if healthy() else 1)
