
import os
import inspect

from contextlib import contextmanager
from database import connect

@contextmanager
def worker_lease(workspace):
    expected=os.getenv(
        "SOCIALMEI_INSTAGRAM_WORKER_DATABASE_NAME",""
    )

    if type(workspace) is not int or workspace<=0 or not expected:
        raise RuntimeError("Invalid worker scope")

    options=(
        {"worker":True}
        if "worker" in inspect.signature(connect).parameters
        else {}
    )

    with connect(**options) as conn:
        conn.autocommit=True

        actual=conn.execute(
            "SELECT current_database()"
        ).fetchone()[0]

        if actual!=expected:
            raise RuntimeError("Database mismatch")

        key="instagram-menu-worker:"+str(workspace)

        locked=conn.execute(
            "SELECT pg_try_advisory_lock(hashtextextended(%s,0))",
            (key,)
        ).fetchone()[0]

        if not locked:
            raise RuntimeError("Worker already running")

        try:
            def check():
                conn.execute("SELECT 1").fetchone()
                return conn

            yield check

        finally:
            if not conn.closed:
                conn.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s,0))",
                    (key,)
                )
