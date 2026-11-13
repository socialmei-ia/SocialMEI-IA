#!/usr/bin/env python3
"""Bounded, read-only PostgreSQL workload sampling; never emits connection details."""
import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time

COUNTERS = (
    "xact_commit", "xact_rollback", "blks_read", "blks_hit",
    "tup_returned", "tup_fetched", "tup_inserted", "tup_updated",
    "tup_deleted", "temp_bytes", "deadlocks",
)
SQL = (
    "SELECT stats_reset::text, numbackends, " + ", ".join(COUNTERS) +
    " FROM pg_catalog.pg_stat_database WHERE datname = current_database()"
)


def decode(row):
    if row is None or len(row) != len(COUNTERS) + 2:
        raise ValueError("invalid_statistics")
    if any(type(number) is not int or number < 0 for number in row[1:]):
        raise ValueError("invalid_statistics")
    return {
        "reset": row[0] or "never",
        "connections": row[1],
        "counters": dict(zip(COUNTERS, row[2:])),
    }


def snapshot(dsn):
    import psycopg
    with psycopg.connect(
        dsn, autocommit=True, connect_timeout=5,
        options="-c default_transaction_read_only=on -c statement_timeout=3000",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SQL)
            return decode(cursor.fetchone())


def compare(first, last, seconds):
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        raise ValueError("invalid_elapsed_time")
    if first["reset"] != last["reset"]:
        raise ValueError("statistics_reset_during_sample")
    changes = {}
    for name in COUNTERS:
        delta = last["counters"][name] - first["counters"][name]
        if delta < 0:
            raise ValueError("counters_reset_during_sample")
        changes[name] = delta
    blocks = changes["blks_hit"] + changes["blks_read"]
    return {
        "duration_seconds": round(seconds, 3),
        "connections_first": first["connections"],
        "connections_last": last["connections"],
        "delta": changes,
        "per_minute": {name: round(value * 60 / seconds, 2) for name, value in changes.items()},
        "block_cache_hit_percent": round(100 * changes["blks_hit"] / blocks, 2) if blocks else None,
    }


def run(args=None):
    parser = argparse.ArgumentParser(description="Sample PostgreSQL activity without changing data")
    parser.add_argument("--interval", type=int, default=60, help="seconds between samples, 10-300")
    parser.add_argument("--samples", type=int, default=2, help="number of samples, 2-12")
    parsed = parser.parse_args(args)
    if not 10 <= parsed.interval <= 300 or not 2 <= parsed.samples <= 12:
        parser.error("interval must be 10-300 and samples must be 2-12")
    dsn = os.environ.get("SOCIALMEI_PG_METRICS_DSN", "").strip()
    if not dsn:
        print("metrics_connection_not_configured", file=sys.stderr)
        return 2
    try:
        started = time.monotonic()
        first = snapshot(dsn)
        last = first
        for _ in range(parsed.samples - 1):
            time.sleep(parsed.interval)
            last = snapshot(dsn)
        result = compare(first, last, time.monotonic() - started)
    except Exception as error:
        # Never print exception details; libpq errors may include connection material.
        print("metrics_collection_failed:" + type(error).__name__, file=sys.stderr)
        return 1
    print(json.dumps({
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "source": "pg_stat_database",
        "samples": parsed.samples,
        "statement_count": parsed.samples,
        "interpretation": "Database-wide cumulative counters, not provider operations or per-query attribution",
        "measurements": result,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())
