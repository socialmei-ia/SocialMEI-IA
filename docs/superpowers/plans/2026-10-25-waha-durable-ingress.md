# WAHA Durable Ingress Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven development; preserve the repository coordinator routing and request a fresh whole-branch review.

**Goal:** Receive authenticated, controlled WAHA-shaped Direct text events durably into the existing Unified Inbox without enabling real sessions or sending.

**Architecture:** Extend `crm_canais` and `crm_eventos_canal` from migration009, using the private shared inbox append from migration020. A server-injected immutable registry binds instance, HMAC secret, session, account and workspace; payloads and browser users cannot claim a channel. No new queue, conversation CRUD, token vault or tables.

**Tech Stack:** FastAPI, psycopg, PostgreSQL16, standard-library HMAC SHA512, existing JavaScript stores and Node/Playwright tests.

**Spec:** The user-authorized functional integration roadmap (Etapa E), `docs/INSTAGRAM-DURABLE-WEBHOOK.md`, migration009 and the official WAHA events/OpenAPI documentation linked in the feature contract.

## Global Constraints

- No real WAHA, AWS, n8n, database, pairing, messages or deployment.
- No HTML, CSS, layout, animation or new controls; functional origin projection only.
- Disabled by default, explicit isolated flag and injected trusted registry; no environment secret or real transport added.
- No client-selected workspace, contact-name matching, inferred phone from LID, raw payload storage or secrets in responses/logs.
- Additive migration023; preserve old rows, fixture paths, keys and synthetic behavior.

## Review Focus

1. Signed but mismatched session/account must not select another workspace.
2. Same MID delivered as message/message.any or after transfer must never duplicate into another business.
3. Concurrent disconnect or revocation must be rechecked under locks before commit.
4. Malformed envelopes, timestamps, identifiers and unsupported media must not become incoming text.
5. Origin changes must never unlock synthetic analysis or outbound composer for provider messages.

## Task 1: Trusted contract and durable receive

Files: create `python-service/waha_ingress.py`, `python-service/test_waha_ingress.py`, `database/migrations/023_waha_durable_ingress.sql`; modify `settings.py`, `app.py`, `message_enrichment.py`.

Interface: `WahaIngressService` receives an injected immutable server registry; `receive(instance, raw_body, signature, algorithm)` verifies bounded raw bytes before JSON/SQL. The route resolves an instance key, not a workspace or secret. A disabled dependency returns503; registered instance identity and session/me binding are exact and cannot use the fixture account creation path.

- [ ] Write/run RED contract tests for SHA512 hex signature, duplicate/missing headers, altered raw body, duplicate JSON keys, limits, unsupported event shapes and fail-closed dependency.
- [ ] Implement narrow incoming text for direct `@c.us`/opaque `@lid`; normalize message/message.any to one MID identity. Ignore echoes/ACK/media/groups without creating incoming messages; reject invalid timestamps/identity/structure. Envelope timestamp is milliseconds, payload timestamp seconds.
- [ ] Extend existing channel/event tables with real-origin binding/snapshots and global account+MID dedupe; composite workspace/origin FKs link the existing inbox. Never duplicate message bodies in the legacy message table. Lock account then workspace/channel, recheck authorization and commit ledger+inbox atomically.
- [ ] Add disposable PostgreSQL tests for tenant/fixture isolation, duplicate/replay/concurrent receive, conflicting content, transfer/reconnect/disconnect, rollback and FKs. Run contract tests locally; record DB skips separately until CI.

## Task 2: Existing inbox integration

Files: `frontend/scripts/message-enrichment-store.js`, `message-enrichment.js`, existing managed inbox path if necessary; relevant Node/browser tests.

Interface: additive `waha_inbox` capability and explicit `origin='waha'`; use existing managed conversation IDs and controls. Provider text is read-only; no synthetic enrichment or sending.

- [ ] Write/run RED tests for exact account/contact namespaces, LID isolation, origin validation, account switches and refusal of local fallback/send/enrichment.
- [ ] Extend the existing projection without changing markup or styles; preserve original assertions.
- [ ] Run focused Node and syntax/format checks.

## Task 3: Review and recovery evidence

Files: `docs/WAHA-DURABLE-INGRESS.md`, `.github/workflows/repository-checks.yml`, `tests/release-candidate-db.py` and this plan.

- [ ] Document official signature contract, bounds, unsupported events, retention/dedupe limitations, server provisioning and live homologation gates without credentials.
- [ ] Add migration023 replay/preservation/ledger-FK/dump-restore fixtures to the existing disposable harness; CI base is `feat/opportunity-planning-persistence` at d1833182f24b2fa23b54ae163192bddfe02b38ec, tree1ccde6195b5fdada215c11a3d80ddcc7f7359762.
- [ ] Request fresh review, fix Important/Critical findings with RED→GREEN evidence, run Node/format/backend/migrations/backup-restore/preview/browser CI on the exact native commit, and open one stacked Draft PR. No merge or deploy.

## Execution record

- Baseline PR109 exact head d1833182f24b2fa23b54ae163192bddfe02b38ec: CI40196927347 validate/browser/preview all passed; backend367/367, Node330/330. Existing Settings/Agenda intermittent issues remain tracked, not declared fixed.
- Live provider version, edition, HMAC configuration and approved chip are external gates; none is inferred from historical runtime evidence.
- Fresh review found malformed event/Decimal inputs could raise500 and context-sensitive timestamp arithmetic could round unsupported precision. Signed regression cases reproduced both; the fix validates UTF-8/type and exact Decimal digits/exponent before integer microsecond conversion, including low-precision Decimal contexts.
- The reviewer classified the rollback-test gap as Minor; it is treated as Important here because atomic recovery is an explicit acceptance criterion. The test now performs the real inbox writes before injected failure and compares conversations, messages, external IDs, ledger and revisions before retry.
- Local backend383 registered:144 passed/239 PostgreSQL skips. Focused Node20 passed. No skip is claimed as a pass; exact native-commit CI remains the PostgreSQL/browser/recovery gate before completion.
