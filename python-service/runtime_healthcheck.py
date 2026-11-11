"""Frequent liveness, periodic readiness; never connect to PostgreSQL directly."""
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.request


STATE = Path(tempfile.gettempdir()) / "socialmei-runtime-health.json"
READINESS_INTERVAL = 60


def probe(path, *, readiness=False):
    with urllib.request.urlopen("http://127.0.0.1:8000" + path, timeout=6 if readiness else 2) as response:
        payload = json.load(response)
    return payload.get("status") == "healthy" and (
        not readiness or payload.get("shared_data") is True
    )


def check(*, state_file=STATE, clock=time.monotonic, request=probe):
    # Liveness is always fresh and does not execute SQL.
    if not request("/health"):
        return False
    now = clock()
    try:
        previous = json.loads(state_file.read_text(encoding="utf-8"))
        checked_at = previous["checked_at"]
        healthy = previous["healthy"]
        valid = type(checked_at) in (float, int) and type(healthy) is bool
        if valid and 0 <= now - checked_at < READINESS_INTERVAL:
            return healthy
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        healthy = request("/health/db", readiness=True)
    except Exception:
        healthy = False
    # No DSN, exception text or business data is written to this state file.
    descriptor, temporary = tempfile.mkstemp(dir=state_file.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump({"checked_at": now, "healthy": healthy}, output)
        os.replace(temporary, state_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return healthy


if __name__ == "__main__":
    try:
        healthy = check()
    except Exception:
        healthy = False
    print("Application and periodic database readiness: " + ("healthy" if healthy else "unavailable"))
    raise SystemExit(0 if healthy else 1)
