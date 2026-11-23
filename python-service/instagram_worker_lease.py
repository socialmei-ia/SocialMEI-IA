"""One Python sender per workspace on the explicitly reviewed API database."""
from contextlib import contextmanager
import os

from database import connect


@contextmanager
def worker_lease(workspace):
    expected = os.getenv('SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME', '')
    if type(workspace) is not int or workspace <= 0 or not expected:
        raise RuntimeError('Instagram worker database review required')
    with connect(worker=True) as conn:
        conn.autocommit = True
        actual = conn.execute('SELECT current_database()').fetchone()[0]
        if actual != expected:
            raise RuntimeError('Instagram worker database mismatch')
        locked = conn.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0))',
                              ('instagram-menu-worker:' + str(workspace),)).fetchone()[0]
        if not locked:
            raise RuntimeError('Instagram workspace sender already running')
        try:
            def check():
                # A lost lock connection must stop processing before provider I/O.
                conn.execute('SELECT 1').fetchone()
                return conn
            yield check
        finally:
            if not conn.closed:
                conn.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))',
                             ('instagram-menu-worker:' + str(workspace),))
