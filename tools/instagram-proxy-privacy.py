"""Prepare *unapplied* privacy-reviewed Caddy candidates for Instagram OAuth.

Never changes live containers, reloads Caddy, enables OAuth, or prints config content.
Fail closed if active JSON differs from the on-disk Caddyfile or routes change.
"""

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


ENCODER = {
    "format": "filter",
    "fields": {
        "request>uri": {"filter": "delete"},
        "request>headers": {"filter": "delete"},
        "resp_headers": {"filter": "delete"},
    },
    "wrap": {"format": "json"},
}
LOG_BLOCK = """    log default {
        format filter {
            request>uri delete
            request>headers delete
            resp_headers delete
            wrap json
        }
    }
"""
CONTAINERS = {
    "public": "socialmei-caddy",
    "gateway": "socialmei-team-team-gateway-1",
}


def _global_block(source):
    """Return the opening/closing braces of a leading global options block."""
    i = 0
    while i < len(source):
        while i < len(source) and source[i].isspace():
            i += 1
        if i < len(source) and source[i] == "#":
            pos = source.find("\n", i)
            i = len(source) if pos < 0 else pos + 1
            continue
        break
    if i == len(source) or source[i] != "{":
        return None
    start = i
    depth = 0
    quoted = False
    escaped = False
    comment = False
    for j in range(i, len(source)):
        char = source[j]
        if comment:
            if char == "\n":
                comment = False
            continue
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == "#":
            comment = True
        elif char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start, j
    raise RuntimeError("Global Caddy options block is not closed.")


def with_logging(source):
    if not source.strip():
        raise RuntimeError("Empty Caddyfile.")
    bounds = _global_block(source)
    if bounds is None:
        return "{\n" + LOG_BLOCK + "}\n" + source
    start, end = bounds
    global_text = source[start + 1 : end]
    # Do not append a second default logger or reinterpret an existing logger.
    for line in global_text.splitlines():
        if re.match(r"^\s*log(?:\s+default)?\s*\{", line) and not line.lstrip().startswith("#"):
            raise RuntimeError("Existing global logger requires manual security review.")
    return source[: start + 1] + "\n" + LOG_BLOCK + source[start + 1 :]


def protected(config):
    logging = config.get("logging") or {}
    logs = logging.get("logs") or {}
    if "default" not in logs:
        return False
    for entry in logs.values():
        encoder = entry.get("encoder") or {}
        if encoder.get("format") != "filter":
            return False
        fields = encoder.get("fields") or {}
        for key in ENCODER["fields"]:
            if fields.get(key, {}).get("filter") != "delete":
                return False
    return True


def logging_only(before, after):
    """Verify semantic JSON changed in logging only, without unsafe loggers."""
    if not protected(after):
        return False
    b = copy.deepcopy(before)
    a = copy.deepcopy(after)
    old = b.pop("logging", {}) or {}
    new = a.pop("logging", {}) or {}
    if a != b:
        return False
    old_logs = old.pop("logs", {}) or {}
    new_logs = new.pop("logs", {}) or {}
    if old != new:
        return False
    if "default" in old_logs:
        return False
    if set(new_logs) != set(old_logs) | {"default"}:
        return False
    if any(old_logs[name] != new_logs[name] for name in old_logs):
        return False
    # Only an encoder was introduced; no writer, level, or routing changed.
    return set(new_logs["default"]) == {"encoder"}


def _call(args, *, input=None):
    try:
        proc = subprocess.run(
            args, input=input, text=True, capture_output=True,
            timeout=30, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Cannot safely inspect/adapt Caddy.") from None
    if proc.returncode:
        raise RuntimeError("Cannot safely inspect/adapt Caddy.")
    return proc.stdout


def _json(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, TypeError):
        raise RuntimeError("Caddy config JSON unavailable.") from None


def _adapt(container, source):
    return _json(_call([
        "docker", "exec", "-i", container, "caddy", "adapt",
        "--config", "/dev/stdin", "--adapter", "caddyfile",
    ], input=source))


def _candidate(container):
    raw = _call(["docker", "exec", container, "cat", "/etc/caddy/Caddyfile"])
    active = _json(_call([
        "docker", "exec", container, "wget", "-qO-",
        "http://127.0.0.1:2019/config/",
    ]))
    baseline = _adapt(container, raw)
    if baseline != active:
        raise RuntimeError("Active Caddy config differs from source; manual review required.")
    changed = with_logging(raw)
    adapted = _adapt(container, changed)
    if not logging_only(active, adapted):
        raise RuntimeError("Candidate changes more than protected log encoding.")
    return raw, changed


def _write_private(path, content):
    fd, temp_name = tempfile.mkstemp(prefix=".instagram-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def prepare(directory):
    # Inspect everything before writing anything, so one bad proxy blocks both.
    results = {name: _candidate(container) for name, container in CONTAINERS.items()}
    if directory.is_symlink():
        raise RuntimeError("Output directory must not be a symlink.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    receipt = {}
    for name, (original, candidate) in results.items():
        for suffix, value in (("original", original), ("candidate", candidate)):
            path = directory / (name + "." + suffix + ".Caddyfile")
            if path.is_symlink():
                raise RuntimeError("Output path must not be a symlink.")
            _write_private(path, value)
            receipt[path.name] = hashlib.sha256(value.encode()).hexdigest()
    _write_private(directory / "sha256.json", json.dumps(receipt, indent=2) + "\n")
    print("Two private candidates prepared and compared. NO live changes. Review:", directory)


def main():
    parser = argparse.ArgumentParser(description="Offline Caddy privacy preparation only")
    parser.add_argument("command", choices=["prepare"])
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / "socialmei-backups" / "instagram-pilot-inspection"),
    )
    options = parser.parse_args()
    try:
        prepare(Path(options.output_dir))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
