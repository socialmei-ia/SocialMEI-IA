"""Single persistent sender for the explicitly enabled Instagram menu. No AI."""
import fcntl
import json
import os
from datetime import datetime
from pathlib import Path
import time

from instagram_auto_menu import enabled, next_source, reply, db
from instagram_contact_identity import refresh_contacts
from instagram_runtime import build_runtime
from instagram_worker_health import heartbeat
from queue_wakeup import QueueWakeup, instagram_channel


def save(path, state):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(state, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def main():
    folder = Path('/run/socialmei/instagram-menu-state')
    lock = (folder/'sender.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    heartbeat('starting', 'initializing')
    try:
        workspace = int(os.environ['SOCIALMEI_INSTAGRAM_AUTO_MENU_WORKSPACE_ID'])
        assert enabled(workspace)
        start = datetime.fromisoformat(os.environ['SOCIALMEI_INSTAGRAM_AUTO_MENU_START_UTC'])
        assert start.tzinfo is not None
        run_sender(workspace, start, folder)
    except Exception:
        heartbeat('blocked', 'unavailable')
        raise


def run_sender(workspace, start, folder):
    path = folder/'state.json'
    state = json.loads(path.read_text()) if path.exists() else {'status':'running','in_flight':False,'confirmed':0,'start':start.isoformat()}
    assert state['status']=='running' and not state['in_flight'] and state['start']==start.isoformat()
    with db() as conn:
        assert not conn.execute("SELECT 1 FROM socialmei.ig_menu_replies WHERE workspace_id=%s "
                                "AND status IN ('dispatching','uncertain') LIMIT 1", (workspace,)).fetchone()
    runtime = build_runtime()
    assert runtime.status=='configured' and runtime.send
    save(path,state)
    backoff=15
    last_contact_refresh=time.monotonic()
    print('INSTAGRAM_MENU_READY',flush=True)
    try:
        read_status='ready'
        def touch():
            heartbeat('running', read_status)
        with QueueWakeup(instagram_channel(workspace), interval=15, reconcile=60,
                         sleeper=time.sleep, heartbeat=touch) as wakeup:
            while True:
                wakeup.prepare()
                try:
                    message=next_source(workspace,start)
                except Exception:
                    read_status='unavailable'
                    state['read_failures']=state.get('read_failures',0)+1; save(path,state)
                    wakeup.pause(backoff); backoff=min(300,backoff*2); continue
                backoff=15
                read_status='ready'
                touch()
                if message is None:
                    # One profile lookup per 15 minutes, even while Direct is idle.
                    if time.monotonic()-last_contact_refresh>=900:
                        last_contact_refresh=time.monotonic()
                        try:
                            outcome=refresh_contacts(runtime,workspace,limit=1,
                                                     after_id=state.get('contact_refresh_cursor',0))
                            state['contact_refresh_cursor']=outcome['last_id']
                            save(path,state)
                        except Exception: pass
                    wakeup.wait(); continue
                state['in_flight']=True; save(path,state)
                result=reply(runtime,workspace,message,start)
                if result not in {'confirmed','skipped','duplicate','rate_limited'}:
                    raise RuntimeError('Unconfirmed automatic reply')
                if result=='confirmed':
                    state['confirmed']+=1
                    print('INSTAGRAM_MENU_CONFIRMED',state['confirmed'],flush=True)
                state['in_flight']=False; save(path,state)
                try:
                    outcome=refresh_contacts(runtime,workspace,limit=1,
                                             after_id=state.get('contact_refresh_cursor',0))
                    state['contact_refresh_cursor']=outcome['last_id']
                    save(path,state)
                except Exception: pass
                last_contact_refresh=time.monotonic()
                wakeup.pause(3)
    except Exception as error:
        state.update(status='paused',reason=type(error).__name__); save(path,state)
        heartbeat('paused', 'unavailable')
        print('INSTAGRAM_MENU_PAUSED',type(error).__name__,flush=True)


if __name__=='__main__':
    try: main()
    except Exception as error: print('INSTAGRAM_MENU_STARTUP_BLOCKED',type(error).__name__,flush=True)
    while True: time.sleep(3600)
