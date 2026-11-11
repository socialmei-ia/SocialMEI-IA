"""Single-contact continuous sender; uncertain dispatch requires operator reconciliation."""
import fcntl
import json
import os
import time
from datetime import datetime
from pathlib import Path

import httpx
from public_worker import API_URL, WAHA_URL, SOURCE_URL, Config, SourceUnavailable, run_once


class Journal:
    def __init__(self, folder, start, allowed):
        if len(allowed) != 1 or not allowed[0].startswith('waha:'):
            raise ValueError('Exactly one authorized contact required')
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
            if self.state['start'] != start or self.state['status'] == 'paused' or self.state['in_flight']:
                self.lock.close()
                raise RuntimeError('Reconciliation required')
        else:
            self.state = dict(start=start, status='running', in_flight=False,
                              attempts=[], attempted=0, confirmed=0, reason=None)
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

    def available(self, now):
        # Retain the existing per-contact ceiling as a rolling 45-minute limit.
        if now < self.state['start']:
            raise RuntimeError('Clock moved before activation')
        self.state['attempts'] = [t for t in self.state['attempts'] if t > now - 2700]
        return len(self.state['attempts']) < 5

    def before_send(self, body, now):
        if 'waha:' + body['chatId'] not in self.allowed or not self.available(now):
            raise RuntimeError('Dispatch outside authorization')
        self.state['attempts'].append(now)
        self.state['attempted'] += 1
        self.save()


def serve(journal, config, *, poll=run_once, sleep=time.sleep, clock=time.time):
    class Client(httpx.Client):
        def request(self, method, url, **kwargs):
            if method == 'GET' and url == API_URL + SOURCE_URL:
                kwargs['timeout'] = httpx.Timeout(15, connect=2)
            if method == 'POST' and url == WAHA_URL + '/api/sendText':
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
                # This exception is restricted to the first read, before any claim.
                journal.state['in_flight'] = False
                journal.state['source_read_failures'] = journal.state.get('source_read_failures', 0) + 1
                journal.save()
                sleep(backoff)
                backoff = min(300, backoff * 2)
                continue
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
    allowed = json.loads(Path('/run/socialmei/pilot/allowed-contacts.json').read_text())
    start = datetime.fromisoformat(os.environ['SOCIALMEI_CONTINUOUS_START_UTC']).timestamp()
    journal = Journal(folder, start, allowed)
    config = Config.from_env()
    print('CONTINUOUS_READY_SINGLE_CONTACT', flush=True)
    serve(journal, config)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('CONTINUOUS_STARTUP_BLOCKED', type(error).__name__, flush=True)
    # Never let a restart policy clear an uncertainty latch.
    while True:
        time.sleep(3600)
