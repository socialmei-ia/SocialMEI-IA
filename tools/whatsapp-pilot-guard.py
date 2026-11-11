"""Bounded operator-authorized pilot around the released menu worker."""
import hashlib
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

import httpx
from public_worker import Config, run_once, WAHA_URL


def pause():
    while True:
        time.sleep(3600)


def main():
    state_path = Path('/run/socialmei/pilot-state/state.json')
    if state_path.exists():
        print('PILOT_CLOSED_EXISTING_STATE', flush=True)
        return pause()
    allowed = json.loads(Path('/run/socialmei/pilot/allowed-contacts.json').read_text())
    assert allowed and all(isinstance(x, str) and x.startswith('waha:') for x in allowed)
    start = datetime.fromisoformat(os.environ['SOCIALMEI_PILOT_START_UTC']).timestamp()
    end = start + 600
    assert start <= time.time() < end
    monotonic_end = time.monotonic() + min(600, end - time.time())
    state = {'status': 'running', 'start_utc': datetime.fromtimestamp(start, timezone.utc).isoformat(),
             'end_utc': datetime.fromtimestamp(end, timezone.utc).isoformat(),
             'attempted': 0, 'confirmed': 0, 'contacts': {}, 'reason': None}

    def save():
        temporary = state_path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(state, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, state_path)

    # A restarted process must never reset the send budget or repeat an uncertain send.
    fd = os.open(state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    save()

    def within_window():
        return time.time() < end and time.monotonic() < monotonic_end

    class PilotClient(httpx.Client):
        def request(self, method, url, **kwargs):
            outgoing = method == 'POST' and url == WAHA_URL + '/api/sendText'
            contact = None
            if outgoing:
                assert within_window(), 'pilot_window_closed'
                body = json.loads(kwargs['content'])
                assert 'waha:' + body['chatId'] in allowed, 'contact_not_authorized'
                contact = hashlib.sha256(body['chatId'].encode()).hexdigest()
                assert state['attempted'] < 40 and state['contacts'].get(contact, 0) < 5, 'pilot_limit_reached'
                state['attempted'] += 1
                state['contacts'][contact] = state['contacts'].get(contact, 0) + 1
                save()
            response = super().request(method, url, **kwargs)
            if outgoing:
                response.raise_for_status()
                state['last_post_response_ok'] = True
                save()
            return response

    try:
        config = Config.from_env()
        while within_window():
            result = run_once(config, client_factory=PilotClient)
            if result == 'ENVIO_CONFIRMADO':
                state['confirmed'] += 1
                state.pop('last_post_response_ok', None)
                save()
                print('PILOT_CONFIRMED', state['confirmed'], flush=True)
                if state['attempted'] >= 40 or max(state['contacts'].values(), default=0) >= 5:
                    state['reason'] = 'send_limit_reached'
                    break
            elif result not in {'SEM_MENSAGENS_NOVAS', 'SEM_ENVIO_AUTORIZADO', 'ENVIO_NEGADO_PELO_SERVIDOR'}:
                state['reason'] = 'uncertain_or_invalid_result'
                break
            time.sleep(min(3, max(0, end - time.time())))
        state['reason'] = state['reason'] or 'window_expired'
    except Exception as error:
        state['reason'] = 'error_' + type(error).__name__
    state['status'] = 'paused'
    state['closed_utc'] = datetime.now(timezone.utc).isoformat()
    save()
    print('PILOT_CLOSED', state['reason'], flush=True)
    return pause()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('PILOT_CLOSED_STARTUP_ERROR', flush=True)
        pause()
