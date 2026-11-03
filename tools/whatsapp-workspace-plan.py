#!/usr/bin/env python3
"""Offline receive-only binding plan. Never connects, provisions or writes files.

Read an administrator-approved metadata file, without HMACs or provider secrets:
{"version":1,"bindings":[{"workspace_id":17,"channel_id":27,"instance":"approved-alias",
"session":"approved-session","account_id":"551199998888@c.us","revision":1}]}
This is NOT a runtime registry. Private keys must be created by a separately
reviewed provisioning operation, which this tool deliberately cannot execute.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

FIELDS = {"workspace_id", "channel_id", "instance", "session", "account_id", "revision"}


def unique_fields(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_field")
        value[key] = item
    return value


def inspect_plan(value):
    if (not isinstance(value, dict) or set(value) != {"version", "bindings"}
            or type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["bindings"], list)
            or not 1 <= len(value["bindings"]) <= 100):
        raise ValueError("invalid_plan")
    seen = {key: set() for key in ("channel_id", "instance", "session", "account_id")}
    public = []
    for binding in value["bindings"]:
        if not isinstance(binding, dict) or set(binding) != FIELDS:
            raise ValueError("invalid_binding_fields")
        if any(type(binding[key]) is not int or not 1 <= binding[key] <= 2**63 - 1
               for key in ("workspace_id", "channel_id", "revision")):
            raise ValueError("invalid_binding_identity")
        instance, session, account = (binding[k] for k in ("instance", "session", "account_id"))
        if (not isinstance(instance, str)
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", instance)
                or instance.startswith("fixture-")
                or not isinstance(session, str) or not re.fullmatch(r"[!-~]{1,160}", session)
                or session.startswith("fixture-")
                or not isinstance(account, str) or not re.fullmatch(r"[0-9]{1,40}@c\.us", account)):
            raise ValueError("invalid_binding_identity")
        # Session names refer to the one existing WAHA service, not new instances.
        for key, identities in seen.items():
            if binding[key] in identities:
                raise ValueError("conflicting_binding")
            identities.add(binding[key])
        public.append({"workspace_id": binding["workspace_id"],
                       "channel_id": binding["channel_id"],
                       "account_suffix": account.split("@", 1)[0][-4:]})
    return {
        "mode": "offline-inspect-only", "plan_valid": True, "deployment_ready": False,
        "production_changed": False, "messages_sent": 0, "bindings": public,
        "runtime_mode_proposed": "workspace-inbox",
        "sending_available": False, "bot_available": False,
        "requires": ["administrator_approval_of_exact_account_session_workspace_channel_revision",
                     "workspace_owner_or_admin_identified", "existing_registry_and_history_preservation",
                     "exact_database_binding_read_only_check", "private_root_owned_registry_and_independent_hmac",
                     "working_authorized_waha_session", "signed_private_webhook_route_review",
                     "legacy_responders_disabled_or_single_owner_verified",
                     "explicit_provisioning_and_deployment_approval", "real_receive_persist_inbox_homologation"],
    }


def load_plan(path):
    if path.is_symlink():
        raise ValueError("invalid_plan_file")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= 65536:
            raise ValueError("invalid_plan_file")
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("invalid_plan_file")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bindings-file", required=True, type=Path)
    args = parser.parse_args()
    result = inspect_plan(load_plan(args.bindings_file))
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"],
                                      cwd=Path(__file__).resolve().parents[1],
                                      stderr=subprocess.DEVNULL, text=True, timeout=5).strip()
        result["source_sha"] = sha if re.fullmatch(r"[0-9a-f]{40}", sha) else "unavailable"
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        result["source_sha"] = "unavailable"
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never echo input, private paths, accounts, endpoints or parser diagnostics.
        print(json.dumps({"plan_valid": False, "code": "binding_plan_invalid", "production_changed": False}))
        sys.exit(2)
