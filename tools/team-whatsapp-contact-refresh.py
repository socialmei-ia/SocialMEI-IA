#!/usr/bin/env python3
"""Bounded pilot label refresh. Default is read-only; never sends messages.

Each changed label has its own verified private rollback snapshot. Run at most
once per minute with --apply --confirm TEAM-1 from a pinned clean source stage.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace


def refresh(candidates, state, now, limit, apply, resolve):
    if (type(limit) is not int or not 1 <= limit <= 3 or len(candidates) > 200
            or any(type(cid) is not int or cid < 1 for cid in candidates)
            or len(set(candidates)) != len(candidates) or not isinstance(state, dict) or len(state) > 200):
        raise ValueError('refresh_input_invalid')
    for cid, entry in state.items():
        if (not isinstance(cid, str) or not cid.isascii() or not cid.isdigit() or int(cid) < 1
                or not isinstance(entry, dict) or set(entry) != {'failures', 'retry_at'}
                or type(entry['failures']) is not int or not 1 <= entry['failures'] <= 10000
                or type(entry['retry_at']) is not int or entry['retry_at'] < 0):
            raise ValueError('refresh_state_invalid')
    eligible = [cid for cid in candidates if state.get(str(cid), {}).get('retry_at', 0) <= now]
    result = {'action': 'contact_refresh' if apply else 'read_only', 'candidates': len(candidates),
              'eligible': len(eligible), 'attempted': 0, 'identified': 0, 'deferred': 0,
              'provider_messages_sent': False, 'personal_identifiers_printed': False}
    if not apply:
        return result, state
    updated = {str(cid): dict(state[str(cid)]) for cid in candidates if str(cid) in state}
    for cid in eligible[:limit]:
        result['attempted'] += 1
        try:
            outcome = resolve(cid)
            if outcome.get('action') not in ('verified_contact_number_displayed', 'already_identified'):
                raise ValueError('resolution_refused')
            updated.pop(str(cid), None)
            result['identified'] += 1
        except Exception:
            failures = min(updated.get(str(cid), {}).get('failures', 0) + 1, 10000)
            updated[str(cid)] = {'failures': failures, 'retry_at': now + min(300 * 2 ** min(failures - 1, 9), 86400)}
            result['deferred'] += 1
    return result, updated


def helper():
    spec = importlib.util.spec_from_file_location('contact_number', Path(__file__).with_name('team-whatsapp-contact-number.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(args):
    import fcntl
    h = helper()
    h.validate_source_runtime(args.source_sha)
    h.require(not args.apply or args.confirm == 'TEAM-1', 'explicit_confirmation_required')
    lock = h.ROOT / 'contact-number.lock'
    fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'w') as stream:
        h.private(lock, 0o600)
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = h.ROOT / 'contact-refresh-state.json'
        state = {}
        if path.exists() or path.is_symlink():
            h.private(path, 0o600)
            h.require(path.stat().st_size <= 32768, 'state_size_invalid')
            state = json.loads(path.read_bytes())
        candidates = h.database('candidates', None)
        def resolve(cid):
            return h.operate(SimpleNamespace(conversation_id=cid, source_sha=args.source_sha,
                                            apply=True, rollback=None, confirm='TEAM-1'))
        result, updated = refresh(candidates, state, int(time.time()), args.limit, args.apply, resolve)
        if args.apply:
            temporary = path.with_suffix('.tmp')
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'w') as output:
                json.dump(updated, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm')
    args = parser.parse_args()
    os.umask(0o077)
    try:
        print(json.dumps(run(args)))
    except Exception:
        print(json.dumps({'action': 'stopped', 'error_code': 'contact_refresh_refused_details_suppressed'}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
