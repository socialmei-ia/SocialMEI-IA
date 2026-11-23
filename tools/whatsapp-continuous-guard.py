"""Continuous inbound-only sender; uncertain dispatch requires operator reconciliation."""
import fcntl
import argparse
import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from public_worker import API_URL, WAHA_URL, SOURCE_URL, Config, SourceUnavailable, run_once


def resume_new_only(folder, expected_sha, incident, cutoff):
    """Operator-only journal transition after database and provider reconciliation."""
    path = folder / 'state.json'
    with (folder / 'sender.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise RuntimeError('Journal changed since review')
        state = json.loads(raw)
        if (state['status'] != 'paused' or state['in_flight'] is not True
                or state.get('public') is not True or cutoff <= state['start']
                or not time.time() - 60 <= cutoff <= time.time()):
            raise RuntimeError('Paused public journal and fresh UTC cutoff required')
        backup = folder / ('state-before-' + incident.hex + '.json')
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        journal = object.__new__(Journal)
        journal.path = path
        journal.state = {**state, 'start': cutoff, 'status': 'running', 'in_flight': False,
                         'reason': None, 'recovery': {'operation_id': str(incident),
                         'previous_sha256': expected_sha, 'cutoff': cutoff,
                         'disposition': 'uncertain_preserved_no_replay'}}
        journal.save()


class Journal:
    def __init__(self, folder, start, allowed, *, public=False):
        if not public and (len(allowed) != 1 or not allowed[0].startswith('waha:')):
            raise ValueError('Exactly one authorized contact required')
        self.public = public
        self.path = folder / 'state.json'
        self.lock = (folder / 'sender.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            self.lock.close()
            raise
        self.allowed = allowed
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
            if (self.state['start'] != start or self.state['status'] == 'paused' or self.state['in_flight']
                    or self.state.get('public', False) != public):
                self.lock.close()
                raise RuntimeError('Reconciliation required')
        else:
            self.state = dict(start=start, status='running', in_flight=False,
                              attempts=[], attempted=0, confirmed=0, reason=None, public=public)
        self.save()

    def save(self):
        temporary = self.path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(self.state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.path)
        fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def available(self, now, contact=None):
        if now < self.state['start']:
            raise RuntimeError('Clock moved before activation')
        self.state['attempts'] = [entry for entry in self.state['attempts']
                                  if (entry['time'] if isinstance(entry, dict) else entry) > now - (900 if self.public else 2700)]
        if not self.public:
            return len(self.state['attempts']) < 5
        if len(self.state['attempts']) >= 60:
            return False
        return contact is None or sum(entry['contact'] == contact for entry in self.state['attempts']) < 10

    def before_send(self, body, now):
        contact = hashlib.sha256(body['chatId'].encode()).hexdigest()
        if (not self.public and 'waha:' + body['chatId'] not in self.allowed) or not self.available(now, contact):
            raise RuntimeError('Dispatch outside authorization')
        self.state['attempts'].append({'time': now, 'contact': contact} if self.public else now)
        self.state['attempted'] += 1
        self.save()


def serve(journal, config, *, poll=run_once, sleep=time.sleep, clock=time.time):
    class Client(httpx.Client):
        def request(self, method, url, **kwargs):
            if method == 'GET' and url == API_URL + SOURCE_URL:
                kwargs['timeout'] = httpx.Timeout(15, connect=2)
            if method == 'POST' and url in {config.waha_url + '/api/sendText', config.waha_url + '/api/sendList'}:
                journal.before_send(json.loads(kwargs['content']), clock())
            return super().request(method, url, **kwargs)

    backoff = 15
    try:
        while True:
            if not journal.available(clock()):
                sleep(15)
                continue
            journal.state['in_flight'] = True
            journal.save()
            try:
                result = poll(config, client_factory=Client)
            except SourceUnavailable:
                # This exception is restricted to reads before any decision, claim or send.
                journal.state['in_flight'] = False
                journal.state['source_read_failures'] = journal.state.get('source_read_failures', 0) + 1
                journal.save()
                sleep(backoff)
                backoff = min(300, backoff * 2)
                continue
            if result == 'RESULTADO_INCERTO_NAO_REENVIAR':
                journal.state.update(status='paused', reason='delivery_uncertain')
                journal.save()
                print('CONTINUOUS_PAUSED delivery_uncertain', flush=True)
                return
            if result not in {'ENVIO_CONFIRMADO', 'SEM_MENSAGENS_NOVAS',
                              'SEM_ENVIO_AUTORIZADO', 'ENVIO_NEGADO_PELO_SERVIDOR'}:
                raise RuntimeError('Uncertain result')
            journal.state['in_flight'] = False
            if result == 'ENVIO_CONFIRMADO':
                journal.state['confirmed'] += 1
                print('CONTINUOUS_CONFIRMED', journal.state['confirmed'], flush=True)
            journal.save()
            backoff = 15
            sleep(3 if result == 'ENVIO_CONFIRMADO' else 15)
    except Exception as error:
        journal.state.update(status='paused', reason=type(error).__name__)
        journal.save()
        print('CONTINUOUS_PAUSED', type(error).__name__, flush=True)


def main():
    folder = Path('/run/socialmei/continuous-state')
    public = os.getenv('SOCIALMEI_MENU_PUBLIC_INBOUND_ACTIVE') == 'YES'
    allowed = [] if public else json.loads(Path('/run/socialmei/pilot/allowed-contacts.json').read_text())
    start = datetime.fromisoformat(os.environ['SOCIALMEI_CONTINUOUS_START_UTC']).timestamp()
    journal = Journal(folder, start, allowed, public=public)
    config = Config.from_env()
    print('CONTINUOUS_READY_PUBLIC_INBOUND' if public else 'CONTINUOUS_READY_SINGLE_CONTACT', flush=True)
    serve(journal, config)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume-new-only', action='store_true')
    parser.add_argument('--journal-sha256')
    parser.add_argument('--uncertain-operation')
    args = parser.parse_args()
    if args.resume_new_only:
        from uuid import UUID
        cutoff = datetime.fromisoformat(os.environ['SOCIALMEI_CONTINUOUS_START_UTC'])
        if cutoff.utcoffset() is None or not args.journal_sha256 or not args.uncertain_operation:
            parser.error('Reviewed journal hash, uncertain operation and explicit UTC cutoff required')
        resume_new_only(Path('/run/socialmei/continuous-state'), args.journal_sha256,
                        UUID(args.uncertain_operation), cutoff.timestamp())
        raise SystemExit(0)
    try:
        main()
    except Exception as error:
        print('CONTINUOUS_STARTUP_BLOCKED', type(error).__name__, flush=True)
    # Never let a restart policy clear an uncertainty latch.
    while True:
        time.sleep(3600)
