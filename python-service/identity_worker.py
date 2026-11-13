"""Explicit opt-in identity mail worker, durable queue with bounded reconciliation."""
import argparse
import sys

from identity_activation import CHANNEL, configured, process_one
from queue_wakeup import QueueWakeup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--watch', action='store_true')
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if not args.run or not 1 <= args.limit <= 100:
        parser.error('--run and limit 1–100 are required')
    try:
        configured()
        with QueueWakeup(CHANNEL, interval=60, reconcile=300) as wakeup:
            while True:
                wakeup.prepare()
                processed = 0
                for _ in range(args.limit):
                    if not process_one():
                        break
                    processed += 1
                if not args.watch:
                    return 0
                if processed < args.limit:
                    wakeup.wait()
    except Exception:
        print('Identity worker unavailable. Verify private configuration and approved schema.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
