"""Optional PostgreSQL wakeups; durable queues remain the source of truth."""
import os
import re
import time

import psycopg
from psycopg import sql

from settings import database_url

RECOVERY_CHANNEL = 'socialmei_recovery_queue'


def mode():
    value = os.getenv('SOCIALMEI_QUEUE_WAKEUP_MODE', 'poll')
    if value not in {'poll', 'listen'}:
        raise ValueError('Invalid queue wakeup mode')
    return value


def instagram_channel(workspace):
    if type(workspace) is not int or not 1 <= workspace <= 2**63 - 1:
        raise ValueError('Invalid queue workspace')
    return 'socialmei_instagram_' + str(workspace)


def _channel(value):
    if not isinstance(value, str) or not re.fullmatch(r'socialmei_[a-z0-9_]{1,50}', value):
        raise ValueError('Invalid queue channel')
    return value


def notify_queue(conn, channel):
    """A savepoint prevents optional wakeup failure from losing persisted work."""
    _channel(channel)
    if mode() != 'listen':
        return False
    try:
        with conn.transaction():
            conn.execute("SELECT pg_notify(%s, '')", (channel,))
        return True
    except psycopg.Error:
        # Reconciliation finds the committed row even when a wakeup is unavailable.
        return False


class QueueWakeup:
    def __init__(self, channel, *, interval=15, reconcile=60, sleeper=None, heartbeat=None):
        self.channel = _channel(channel)
        self.mode = mode()
        if not 1 <= interval <= 300 or not interval <= reconcile <= 300:
            raise ValueError('Invalid queue interval')
        self.interval = interval
        self.reconcile = reconcile
        self.sleep = sleeper or time.sleep
        self.heartbeat = heartbeat or (lambda: None)
        self.connection = None
        self.retry_at = 0
        self.retry_delay = 15
        self.connection_failures = 0

    def __enter__(self):
        self.prepare()
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self.connection is not None:
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

    def _failed(self):
        self.close()
        self.connection_failures += 1
        self.retry_at = time.monotonic() + self.retry_delay
        self.retry_delay = min(300, self.retry_delay * 2)

    def prepare(self):
        """Subscribe before scanning so enqueue between scan and wait is retained."""
        if self.mode != 'listen' or self.connection is not None or time.monotonic() < self.retry_at:
            return
        try:
            self.connection = psycopg.connect(database_url(), autocommit=True,
                connect_timeout=5, application_name='socialmei-queue-wakeup')
            self.connection.execute(sql.SQL('LISTEN {}').format(sql.Identifier(self.channel)))
        except Exception:
            self._failed()

    def pause(self, seconds):
        remaining = seconds
        while remaining > 0:
            self.heartbeat()
            duration = min(30, remaining)
            self.sleep(duration)
            remaining -= duration
        self.heartbeat()

    def wait(self):
        if self.mode != 'listen' or self.connection is None:
            self.pause(self.interval)
            return False
        remaining = self.reconcile
        try:
            while remaining > 0:
                self.heartbeat()
                duration = min(30, remaining)
                events = self.connection.notifies(timeout=duration, stop_after=1)
                received = next(events, None) is not None
                events.close()
                # A successful LISTEN alone does not prove this connection can wait.
                self.retry_delay = 15
                if received:
                    # A burst can leave many signals after all durable rows were drained.
                    pending = self.connection.notifies(timeout=0, stop_after=1000)
                    for _ in pending:
                        pass
                    pending.close()
                    self.heartbeat()
                    return True
                remaining -= duration
            self.heartbeat()
            return False
        except Exception:
            self._failed()
            self.pause(self.interval)
            return False
