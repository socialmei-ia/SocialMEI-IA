"""Interactive, private, staged Instagram OAuth setup for the team VPS.

This tool edits only the server's .env.team after a private backup. It never
restarts containers, deploys code, enables OAuth/webhooks/sending, or prints tokens.
"""
import base64
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
HOST_KEY = "SOCIALMEI_TEAM_HOST"
CLIENT_ID = "27816981071315232"
RETURN_PATH = "/api/v1/instagram/meta/oauth/return"
SAFE_SCOPES = {
    "instagram_business_basic", "instagram_business_manage_messages",
    "instagram_business_content_publish", "instagram_business_manage_comments",
}
DISABLED = {
    "SOCIALMEI_INSTAGRAM_RUNTIME_MODE": "disabled",
    "SOCIALMEI_INSTAGRAM_RUNTIME_INGRESS_ENABLED": "false",
    "SOCIALMEI_INSTAGRAM_RUNTIME_SEND_ENABLED": "false",
    "SOCIALMEI_INSTAGRAM_PROXY_PRIVACY_REVIEWED": "false",
}


def _value(line):
    if line.startswith(("'", '"')) and line[-1:] == line[:1]:
        return line[1:-1]
    return line


def read_environment(content):
    values = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if key in values:
            raise RuntimeError("Duplicate env key; manual review required.")
        values[key] = _value(value.strip())
    return values


def _check_uri(url, host, client_id):
    if not isinstance(url, str) or len(url) > 4096 or "'" in url or "\n" in url:
        raise RuntimeError("Invalid Meta authorization URL.")
    try:
        parsed = urlsplit(url)
        pairs = parse_qsl(parsed.query, strict_parsing=True, keep_blank_values=True)
        args = {key: val for key, val in pairs}
        if len(args) != len(pairs):
            raise ValueError("Duplicate URL key")
    except (ValueError, TypeError):
        raise RuntimeError("Invalid Meta authorization URL.") from None
    allowed = {
        "client_id", "redirect_uri", "response_type", "scope",
        "force_reauth", "enable_fb_login",
    }
    scopes = args.get("scope", "").split(",")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ("instagram.com", "www.instagram.com")
        or parsed.path.rstrip("/") != "/oauth/authorize"
        or parsed.port not in (None, 443)
        or parsed.username or parsed.password or parsed.fragment
        or set(args) - allowed
        or args.get("client_id") != client_id
        or args.get("redirect_uri") != "https://" + host + RETURN_PATH
        or args.get("response_type") != "code"
        or len(scopes) != len(set(scopes))
        or "instagram_business_basic" not in scopes
        or not set(scopes) <= SAFE_SCOPES
    ):
        raise RuntimeError("Meta URL, scopes or registered callback do not match.")
    for option in ("force_reauth", "enable_fb_login"):
        if option in args and args[option] not in ("true", "false"):
            raise RuntimeError("Meta URL option is invalid.")
    return ",".join(scopes)


def _quoted(value):
    if not isinstance(value, str) or "\r" in value or "\n" in value or "'" in value:
        raise RuntimeError("Unsafe env value; nothing was saved.")
    return "'" + value + "'"


def _write_private(path, content):
    if path.is_symlink():
        raise RuntimeError("Refusing symlinked private file.")
    fd, name = tempfile.mkstemp(dir=str(path.parent), prefix=".ig-private-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def staged_values(existing, *, prompt=input, hidden=getpass.getpass):
    host = existing.get(HOST_KEY, "")
    if not re.fullmatch(r"[a-z0-9.-]{4,253}", host) or "." not in host:
        raise RuntimeError("Invalid existing SocialMEI team host.")
    for key, inactive in DISABLED.items():
        if existing.get(key, inactive) != inactive:
            raise RuntimeError("Already activated or reviewed: do not overwrite live config.")
    result = {}
    prefix = "SOCIALMEI_INSTAGRAM_"
    client_id = existing.get(prefix + "CLIENT_ID") or CLIENT_ID
    if client_id != CLIENT_ID:
        raise RuntimeError("Client ID differs from the verified Instagram panel.")
    result["CLIENT_ID"] = client_id
    secret = existing.get(prefix + "CLIENT_SECRET") or hidden("Instagram App Secret (hidden): ").strip()
    if not 32 <= len(secret) <= 16384 or any(c.isspace() or c in "'\r\n" for c in secret):
        raise RuntimeError("Instagram App Secret missing or invalid.")
    result["CLIENT_SECRET"] = secret
    graph = existing.get(prefix + "GRAPH_VERSION") or prompt("Confirmed Graph version (vNN.0): ").strip()
    if not re.fullmatch(r"v[1-9][0-9]{0,2}\.0", graph):
        raise RuntimeError("Graph version must be confirmed from the Meta Dashboard.")
    result["GRAPH_VERSION"] = graph
    embed = existing.get(prefix + "AUTHORIZATION_EMBED") or prompt("Meta authorization URL: ").strip()
    result["SCOPES"] = _check_uri(embed, host, client_id)
    if existing.get(prefix + "SCOPES") and existing[prefix + "SCOPES"] != result["SCOPES"]:
        raise RuntimeError("Existing scopes conflict with the Meta URL.")
    result["AUTHORIZATION_EMBED"] = embed
    keyring = existing.get(prefix + "TOKEN_KEYRING")
    key_id = existing.get(prefix + "TOKEN_ACTIVE_KEY_ID")
    if bool(keyring) != bool(key_id):
        raise RuntimeError("Partial token keyring: manual recovery required.")
    if not keyring:
        key_id = "pilot-" + secrets.token_hex(4)
        keyring = json.dumps({key_id: base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")}, separators=(",", ":"))
    else:
        try:
            raw = json.loads(keyring)
            if not isinstance(raw, dict) or not 1 <= len(raw) <= 16 or key_id not in raw:
                raise ValueError()
            for kid, value in raw.items():
                if not isinstance(kid, str) or not kid or not isinstance(value, str):
                    raise ValueError()
                decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
                if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != value.rstrip("="):
                    raise ValueError()
        except (ValueError, TypeError):
            raise RuntimeError("Existing keyring invalid; refusing rotation.") from None
    result["TOKEN_KEYRING"] = keyring
    result["TOKEN_ACTIVE_KEY_ID"] = key_id
    result["WEBHOOK_VERIFY_TOKEN"] = existing.get(prefix + "WEBHOOK_VERIFY_TOKEN") or secrets.token_urlsafe(48)
    return {prefix + name: value for name, value in result.items()}


def prepare(path, *, prompt=input, hidden=getpass.getpass):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Expected private .env.team not found.")
    content = path.read_text(encoding="utf-8")
    existing = read_environment(content)
    additions = staged_values(existing, prompt=prompt, hidden=hidden)
    for key, val in DISABLED.items():
        if key not in existing:
            additions[key] = val
    updates = [key + "=" + _quoted(value) for key, value in additions.items() if key not in existing]
    if not updates:
        print("Private values already staged. OAuth remains OFF.")
        return
    folder = Path.home() / "socialmei-backups" / "instagram-pilot-inspection"
    if folder.is_symlink():
        raise RuntimeError("Backup directory is a symlink.")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    backup = folder / ("env-team-before-" + secrets.token_hex(8) + ".bak")
    _write_private(backup, content)
    updated = content.rstrip("\n") + "\n" + "\n".join(updates) + "\n"
    _write_private(path, updated)
    print("Staged server-only settings with private backup. OAuth, incoming and sending remain OFF.")


if __name__ == "__main__":
    try:
        prepare(ROOT / ".env.team")
    except (RuntimeError, OSError) as exc:
        raise SystemExit(str(exc)) from None
