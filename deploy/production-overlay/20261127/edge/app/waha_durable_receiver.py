"""Receive-only durable edge prototype. No production installer or sender.

ACK means the original signed bytes committed to the private spool, not API delivery.
The only downstream operation is POST to the fixed private WAHA ingress route.
"""
import hashlib
import hmac
import http.client
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 65536


class Rejected(ValueError):
    pass


class DurableReceiver:
    def __init__(self, directory, binding):
        if (type(binding.get('workspace_id')) is not int or binding['workspace_id'] not in (1,60)
                or not re.fullmatch(r'[0-9]{1,40}@c\.us', binding.get('account_id', ''))
                or not binding['account_id'].endswith('5976@c.us')
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', binding.get('instance', ''))
                or not isinstance(binding.get('session'), str) or not binding['session']
                or len(binding.get('hmac_key', '').encode()) < 32):
            raise Rejected('binding_not_authorized')
        self.binding = dict(binding)
        self.directory = Path(directory)
        if binding['workspace_id'] == 60:
            cid = binding.get('channel_id')
            revision = binding.get('revision')
            cutoff = binding.get('ingress_after')
            if (
                type(cid) is not int or cid <= 0
                or revision != 2
                or type(cutoff) is not int or cutoff <= 0
                or binding.get('session') != '01'
                or binding.get('engine') != 'GOWS'
                or binding.get('instance') != 'socialmei-equipe-piloto'
            ):
                raise Rejected('binding_not_authorized')
            if self.directory.is_symlink():
                raise Rejected('spool_not_private')
            self.directory.mkdir(mode=0o700,exist_ok=True)
            self.directory = self.directory / (
                'workspace-60-channel-'+str(cid)+'-r2'
            )
        self.directory.mkdir(mode=0o700, parents=False, exist_ok=True)
        if self.directory.is_symlink():
            raise Rejected('spool_not_private')
        os.chmod(self.directory, 0o700)
        self.path = self.directory / 'ingress.sqlite3'
        if self.path.is_symlink():
            raise Rejected('spool_not_private')
        self.lock = threading.Lock()
        with self.db() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            owner = hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()
            conn.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES('binding',?)", (owner,))
            if conn.execute("SELECT value FROM metadata WHERE key='binding'").fetchone()[0] != owner:
                raise Rejected('spool_binding_changed')
            conn.execute('CREATE TABLE IF NOT EXISTS queue('
                         'key TEXT PRIMARY KEY, body BLOB NOT NULL, signature TEXT NOT NULL,'
                         "state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,"
                         'next_attempt REAL NOT NULL DEFAULT 0, created REAL NOT NULL)')
            conn.execute('CREATE INDEX IF NOT EXISTS pending_queue ON queue(state,next_attempt,created)')
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            conn.execute('PRAGMA synchronous=FULL')
            with conn:
                yield conn
        finally:
            conn.close()

    def accept(self, body, signature, algorithm):
        if (not isinstance(body, bytes) or not 1 <= len(body) <= MAX_BODY
                or algorithm != 'sha512' or not isinstance(signature, str)
                or not re.fullmatch(r'[0-9a-fA-F]{128}', signature)
                or not hmac.compare_digest(bytes.fromhex(signature), hmac.new(
                    self.binding['hmac_key'].encode(), body, hashlib.sha512).digest())):
            raise Rejected('signature_rejected')
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise Rejected('invalid_envelope')
                value[key] = item
            return value
        try:
            event = json.loads(body.decode('utf-8'), object_pairs_hook=unique,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise Rejected('invalid_envelope') from None
        if (not isinstance(event, dict) or event.get('session') != self.binding['session']
                or not isinstance(event.get('me'), dict)
                or event['me'].get('id') != self.binding['account_id']
                or event.get('event') != 'message' or event.get('engine') != self.binding.get('engine', 'WEBJS')):
            raise Rejected('owner_or_event_rejected')
        cutoff = int(__import__('os').environ['WAHA_INGRESS_AFTER'])
        payload = event.get('payload')
        stamp = payload.get('timestamp') if isinstance(payload, dict) else None
        if type(stamp) not in (int, float):
            raise Rejected('invalid_message_time')
        if stamp < cutoff:
            return None
        key = hashlib.sha256(body).hexdigest()
        with self.db() as conn:
            conn.execute('INSERT OR IGNORE INTO queue(key,body,signature,created) VALUES(?,?,?,?)',
                         (key, body, signature, time.time()))
        return key  # Only returned after COMMIT succeeds; never log body/signature.

    def deliver_one(self, post, now=None):
        now = time.time() if now is None else now
        with self.lock, self.db() as conn:
            row = conn.execute("SELECT key,body,signature,attempts FROM queue WHERE state='pending' "
                               'AND next_attempt<=? ORDER BY created,key LIMIT 1', (now,)).fetchone()
            if row is None:
                return False
            key, body, signature, attempts = row
            try:
                status, receipt = post(body, signature, 'sha512')
                valid = (status == 200 and isinstance(receipt, dict)
                         and set(receipt) == {'processed', 'ignored', 'duplicates'}
                         and all(type(v) is int and v in {0, 1} for v in receipt.values())
                         and sum(receipt.values()) == 1)
                state = 'delivered' if valid else ('quarantined' if 400 <= status < 500 else 'pending')
            except Exception:
                state = 'pending'  # Uncertain commit: replay same signed bytes; API ledger deduplicates.
            conn.execute('UPDATE queue SET state=?,attempts=?,next_attempt=? WHERE key=?',
                         (state, attempts + 1, now + min(300, 2 ** min(attempts, 8)), key))
            return True

    def counts(self):
        with self.db() as conn:
            return dict(conn.execute('SELECT state,count(*) FROM queue GROUP BY state'))


def private_api_post(instance):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', instance):
        raise Rejected('invalid_instance')
    def post(body, signature, algorithm):
        # No redirects, arbitrary destinations, n8n, AI or sender endpoint.
        conn = http.client.HTTPConnection('socialmei-team-team-api-1', 8000, timeout=12)
        try:
            conn.request('POST', '/internal/waha/' + instance + '/webhook', body=body, headers={
                'Content-Type': 'application/json', 'X-Webhook-Hmac': signature,
                'X-Webhook-Hmac-Algorithm': algorithm,
            })
            response = conn.getresponse()
            raw = response.read(4097)
            return response.status, json.loads(raw) if len(raw) <= 4096 else None
        finally:
            conn.close()
    return post


def make_server(receiver, address):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Access URLs, private payloads and signatures must not reach logs.

        def do_POST(self):
            if self.path != '/receive':
                self.send_error(404)
                return
            try:
                self.connection.settimeout(10)
                if (self.headers.get('Transfer-Encoding')
                        or len(self.headers.get_all('Content-Length', [])) != 1
                        or len(self.headers.get_all('Content-Type', [])) != 1
                        or self.headers['Content-Type'].split(';')[0].strip() != 'application/json'
                        or len(self.headers.get_all('X-Webhook-Hmac', [])) != 1
                        or len(self.headers.get_all('X-Webhook-Hmac-Algorithm', [])) != 1):
                    raise Rejected('ambiguous_headers')
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= MAX_BODY:
                    raise Rejected('invalid_size')
                body = self.rfile.read(size)
                if len(body) != size:
                    raise Rejected('incomplete_body')
                receiver.accept(body, self.headers['X-Webhook-Hmac'],
                                self.headers['X-Webhook-Hmac-Algorithm'])
                self.send_response(202)
                self.end_headers()
            except (Rejected, ValueError):
                self.send_error(403, 'Rejected')
            except Exception:
                self.send_error(503, 'Storage unavailable')  # No ACK on failed durable write.
    return ThreadingHTTPServer(address, Handler)


if __name__ == '__main__':
    raise SystemExit('Preparation prototype only; no production launcher is authorized here.')
