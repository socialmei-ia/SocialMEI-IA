"""Explicit opt-in worker for password recovery. No SMTP delivery on API startup."""

import argparse
import sys
import time

from account_recovery import process_one
from queue_wakeup import QueueWakeup, RECOVERY_CHANNEL


def poll_once(limit):
    processed = 0
    for _ in range(limit):
        if not process_one():
            break
        processed += 1
    return processed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="Authorize SMTP processing using the private server environment")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--watch", action="store_true",
                        help="Continue polling the queue; requires --run")
    parser.add_argument("--interval", type=int, default=15)
    args = parser.parse_args()
    if not args.run or not 1 <= args.limit <= 100 or not 5 <= args.interval <= 300:
        parser.error("--run, limit 1–100 and interval 5–300 are required")
    try:
        if not args.watch:
            processed = poll_once(args.limit)
            print(f"Recovery delivery requests processed: {processed}. No delivery receipt is implied.")
            return 0
        with QueueWakeup(RECOVERY_CHANNEL, interval=args.interval, reconcile=300,
                         sleeper=time.sleep) as wakeup:
            while True:
                wakeup.prepare()
                processed = poll_once(args.limit)
                if wakeup.mode == 'listen' and processed == args.limit:
                    continue
                # No addresses, tokens or queued customer counts in logs.
                wakeup.wait()
    except KeyboardInterrupt:
        return 0
    except Exception:
        print(
            "Recovery worker unavailable. Verify private configuration, database and migrations.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
