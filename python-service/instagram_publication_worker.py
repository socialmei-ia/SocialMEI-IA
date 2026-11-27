"""Run only scheduled Instagram feed publications; require explicit deployment opt-in."""
import argparse
import logging
import os
import time

import psycopg

from instagram_publishing import schedule_enabled, schedule_schema_ready
from instagram_runtime import build_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuous", action="store_true")
    args = parser.parse_args()
    if os.getenv("SOCIALMEI_INSTAGRAM_SCHEDULE_WORKER_ENABLED") != "YES" or not schedule_enabled():
        parser.exit(2, "Instagram publication scheduler disabled.\n")
    if not schedule_schema_ready():
        parser.exit(2, "Instagram publication schedule migration unavailable.\n")
    publisher = build_runtime().publish
    if publisher is None:
        parser.exit(2, "Instagram publication runtime unavailable.\n")
    while True:
        try:
            processed = publisher.process_scheduled_once()
        except (psycopg.OperationalError, psycopg.errors.SerializationFailure, psycopg.errors.DeadlockDetected):
            if not args.continuous:
                parser.exit(1, "Instagram publication scheduler could not reach a transaction.\n")
            logging.warning("Instagram publication scheduler transaction unavailable")
            processed = False
        if not args.continuous:
            return
        if not processed:
            time.sleep(5)


if __name__ == "__main__":
    main()
