---
name: diagnosing-codex-network-access
description: Use when a SocialMEI Codex cloud task gets proxy HTTP 403, cannot reach an approved service, or behaves differently from another task using network secrets.
---

# Diagnosing Codex network access

## Principle
Treat **Codex execution environment**, **network proxy**, **target server**, and **API authentication** as separate layers. A proxy 403 is not proof that the n8n API key is invalid.

## Read-only diagnosis
1. Identify the task's actual execution mode (cloud or local), selected repository and published cloud environment. An isolated managed development environment is normal; it does not have to run inside AWS.
2. Inspect the environment's internet-access setting, the precise hostname allowlist and the network-secret **binding**. Verify that edits were saved/published **before** the task started. Settings in another task do not prove settings in this one.
3. Compare requests using the same method, exact origin and minimal path. First, if allowed, run one unauthenticated `GET /healthz`. Record whether the status came from the proxy or the service.
4. Only if connectivity succeeds and the user approved API inspection, try a single authenticated, read-only n8n `GET /api/v1/workflows?limit=1` with the secure `N8N_API_KEY` network-secret mechanism and `X-N8N-API-KEY` header.
5. On **proxy 403**, stop. Ask for a freshly created task selecting the intended published environment; re-check allowlist and secret-host association. Do not keep retrying or try to bypass policy.
6. On a response **from n8n**, diagnose the returned status separately (authentication, authorization, route or server error). A successful `/healthz` does not prove authenticated API access.
7. Report only task/environment identity, sanitized request path, status, origin of error and next safe action. Mark unverified claims `NÃO CONFIRMADO`.

## Guardrails
- Never read, print, copy to chat or commit credential values. Do not test secret access via environment-variable dumps.
- Do not widen to all domains, disable proxy controls, switch to raw IPs, or use alternate hosts to evade restrictions.
- Do not execute, activate, import, edit or delete live workflows as part of diagnosis.
- Keep Git exports, live n8n state, Codex cloud environment and AWS runtime distinct; never infer one from another.
- Escalate any proposed permission or production change for explicit approval.

## Related guidance
Read `docs/CODEX-TOOLING.md`, `docs/ENVIRONMENTS.md`, and use `n8n-workflow-review` only when inspecting n8n workflow structures.
