#!/usr/bin/env python3
"""Offline structural gate for the pinned Instagram receive-only candidate.

This NEVER deploys, contacts Meta/AWS/n8n, prints private file content, or
authorizes cutover. GitHub CI supplies a checkout of the exact candidate SHA.
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

CANDIDATE = "345a074310673640084c7634e3da75dd72491813"
BASELINE = "a4720f8b7ea98a67cb40b7b3208acdd7e8bcd510"
N8N_PATH = "/webhooks/instagram/n8n"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def source(root, rel):
    path = root / rel
    require(path.is_file() and not path.is_symlink(), "candidate_file_unavailable")
    require(path.stat().st_size <= 200000, "candidate_file_unexpected")
    return path.read_text(encoding="utf-8")


def git_revision(root):
    try:
        value = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        raise ValueError("candidate_revision_unavailable") from None
    require(value == CANDIDATE, "candidate_sha_mismatch")
    return value


def inspect_sources(files):
    ingress = files["python-service/instagram_n8n_ingress.py"]
    gateway = files["deploy/team/Caddyfile"]
    app = files["python-service/app.py"]
    settings = files["python-service/settings.py"]
    helper = files["tools/prepare-instagram-persistence.mjs"]

    checks = {
        "n8n_api_route_declared": (
            f'PATH = "{N8N_PATH}"' in ingress
            and "@router.post(PATH)" in ingress
            and "def ingress_service()" in ingress
        ),
        "n8n_endpoint_protected": (
            "settings.instagram_n8n_ingress_enabled()" in ingress
            and "settings.instagram_n8n_ingress_configuration()" in ingress
            and "parse_message_events(raw, meta_signature" in ingress
            and "persist_authenticated_events(events, canonical_bindings)" in ingress
        ),
        "endpoint_registered": (
            "router as instagram_n8n_ingress_router" in app
            and "app.include_router(instagram_n8n_ingress_router)" in app
        ),
        "gateway_post_only_n8n_path": (
            re.search(
                r"@instagram_n8n_ingress\s*\{\s*method POST\s*"
                r"path /webhooks/instagram/n8n\s*\}",
                gateway
            ) is not None
            and "handle @instagram_n8n_ingress" in gateway
            and "reverse_proxy team-api:8000" in gateway
        ),
        "explicit_feature_flag_in_settings": (
            "def instagram_n8n_ingress_enabled(" in settings
            and "def instagram_n8n_ingress_configuration(" in settings
        ),
        "workflow_prepared_not_published": (
            "automatically_publish: false" in helper
            and "resumeLegacy = false" in helper
            and "responseMode = \"responseNode\"" in helper
            and "rawBody: true" in helper
            and 'apiOrigin + "/webhooks/instagram/n8n"' in helper
        ),
        "legacy_ai_unreachable_by_default": (
            'candidate.connections[NAMES.ack] = { main: resumeLegacy ? [[edge(NAMES.resume)]] : [[]] };' in helper
            and 'candidate.connections[NAMES.resume] = resumeLegacy ? old : { main: [[]] };' in helper
        ),
    }
    return checks


def inspect(root, revision=None):
    root = Path(root)
    # Without a recognized exact source revision, do not characterize a candidate.
    revision = revision or git_revision(root)
    require(revision == CANDIDATE, "candidate_sha_mismatch")
    names = (
        "python-service/instagram_n8n_ingress.py",
        "deploy/team/Caddyfile",
        "python-service/app.py",
        "python-service/settings.py",
        "tools/prepare-instagram-persistence.mjs",
    )
    files = {name: source(root, name) for name in names}
    checks = inspect_sources(files)
    return {
        "candidate": CANDIDATE,
        "baseline_documentada": BASELINE,
        "modo": "source_inspection_only",
        "checks": checks,
        "contracts_ok": all(checks.values()),
        "cutover_approved": False,
        "aws_changed": False,
        "pending_manual_gates": [
            "runtime_image_and_compose_overlay_match",
            "candidate_bundle_images_verified",
            "backup_restore_in_isolated_target",
            "public_caddy_forwarding",
            "published_n8n_workflow_snapshot_and_diff",
            "private_n8n_bearer_and_oauth_account_bindings",
            "meta_callback_subscription_and_scope",
            "authorized_real_inbox_test",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-root", required=True)
    args = parser.parse_args()
    try:
        report = inspect(args.candidate_root)
    except (ValueError, UnicodeError, OSError):
        print(json.dumps({
            "modo": "source_inspection_only", "contracts_ok": False,
            "cutover_approved": False, "aws_changed": False,
            "resultado": "BLOQUEADO"
        }))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if report["contracts_ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
