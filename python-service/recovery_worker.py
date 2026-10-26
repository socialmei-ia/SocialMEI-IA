"""Explicit bounded worker for the recovery queue. Never starts with the API."""

import argparse
import sys
from account_recovery import process_one


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Authorize SMTP processing using this environment configuration",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not args.run or not 1 <= args.limit <= 100:
        parser.error("--run and limit1–100 are required")
    try:
        processed = 0
        for _ in range(args.limit):
            if not process_one():
                break
            processed += 1
        print(
            f"Recovery delivery requests processed: {processed}. No delivery receipt is implied."
        )
        return 0
    except Exception:
        print(
            "Recovery worker unavailable. Verify private configuration, database and migrations.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
