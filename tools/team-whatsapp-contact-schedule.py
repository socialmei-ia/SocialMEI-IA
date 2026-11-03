#!/usr/bin/env python3
"""Inspect/install/remove only the pilot contact-label cron job, never a sender."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

JOB = Path('/etc/cron.d/socialmei-whatsapp-contact-refresh')
LOG = Path('/var/lib/socialmei-wa-pilot/contact-refresh.log')


def schedule(source, sha):
    if (not re.fullmatch(r'[a-f0-9]{40}', sha)
            or not re.fullmatch(r'/home/ubuntu/socialmei-backups/[A-Za-z0-9_-]+/source', str(source))):
        raise ValueError('schedule_source_invalid')
    return ('# Managed SocialMEI pilot contact labels; no sender\n'
            'SHELL=/bin/sh\nPATH=/usr/bin:/bin\nMAILTO=""\n'
            '* * * * * root /usr/bin/python3 ' + str(source / 'tools/team-whatsapp-contact-refresh.py')
            + ' --source-sha ' + sha + ' --limit 3 --apply --confirm TEAM-1 >> ' + str(LOG) + ' 2>&1\n')


def change_required(action, current, expected):
    if action not in ('install', 'remove') or current not in (None, expected):
        raise ValueError('unrecognized_schedule_preserved')
    return current is None if action == 'install' else current is not None


def run(args, h=None):
    import fcntl
    if h is None:
        spec = importlib.util.spec_from_file_location('contact_refresh', Path(__file__).with_name('team-whatsapp-contact-refresh.py'))
        refresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(refresh)
        h = refresh.helper()
    if args.remove:
        h.validate_source(args.source_sha)
    else:
        h.validate_source_runtime(args.source_sha)
    h.require(not (args.install or args.remove) or args.confirm == 'TEAM-1', 'explicit_confirmation_required')
    fd = os.open(h.ROOT / 'contact-number.lock', os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as lock:
        h.private(h.ROOT / 'contact-number.lock', 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = Path(__file__).resolve().parents[1]
        body = schedule(source, args.source_sha).encode()
        current = None
        if JOB.exists() or JOB.is_symlink():
            h.private(JOB, 0o600)
            current = JOB.read_bytes()
        action = 'install' if args.install else 'remove'
        change = change_required(action, current, body)
        if not (args.install or args.remove):
            return {'action': 'read_only', 'installed': current == body, 'source_sha': args.source_sha}
        if not change:
            return {'action': 'already_installed' if args.install else 'already_removed'}
        if args.install:
            cron = subprocess.run(['systemctl', 'is-active', 'cron'], capture_output=True, timeout=15)
            h.require(cron.returncode == 0, 'cron_not_active')
            if LOG.exists() or LOG.is_symlink():
                h.private(LOG, 0o600)
                h.require(LOG.stat().st_size <= 1048576, 'log_rotation_required')
            else:
                logfd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
                os.close(logfd)
        folder = h.ROOT / ('contact-schedule-' + time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
        folder.mkdir(mode=0o700)
        snapshot = json.dumps({'version': 1, 'action': action, 'source_sha': args.source_sha,
                               'before': None if current is None else current.decode(), 'expected': body.decode()}, sort_keys=True).encode()
        for name, data in [('snapshot.json', snapshot), ('snapshot.sha256', hashlib.sha256(snapshot).hexdigest().encode())]:
            fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(data); output.flush(); os.fsync(output.fileno())
        h.require((folder / 'snapshot.json').read_bytes() == snapshot, 'snapshot_write_failed')
        if args.install:
            fd = os.open(JOB, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(body); output.flush(); os.fsync(output.fileno())
            h.require(JOB.read_bytes() == body, 'schedule_write_failed')
        else:
            h.require(JOB.read_bytes() == body, 'schedule_changed')
            JOB.unlink()
        return {'action': 'installed' if args.install else 'removed', 'backup': folder.name,
                'source_sha': args.source_sha, 'provider_messages_sent': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--confirm')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--install', action='store_true')
    modes.add_argument('--remove', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(run(args)))
    except Exception:
        print(json.dumps({'action': 'stopped', 'error_code': 'contact_schedule_refused_details_suppressed'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
