# Dashboard Functional Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver the approved functional dashboard list in an isolated testable branch, with real commercial persistence and truthful connector preparation.

**Architecture:** Extend existing feature routers and frontend stores. Keep opportunity lifecycle separate from heuristic analysis, sales/payment and connector transport. Reuse content preparation APIs and templates; no framework or visual-system migration.

**Tech Stack:** Vanilla classic JavaScript, HTML/CSS, FastAPI/Pydantic, PostgreSQL16, Node tests, unittest and Playwright.

**Spec:** docs/superpowers/specs/2026-10-21-dashboard-functional-readiness.md

## Global Constraints

- Branch from ecaa4bd, no ancestry rewrite/reapplication; main and existing PRs unchanged.
- Migrations016/017 immutable and disposable-only; workspace from authenticated session.
- Existing Origin/CSRF, viewer restrictions and failure-without-local-fallback are mandatory.
- No live connector calls or credentials, no deployment or redesign; user-reported readiness is not connected state.

## Review Focus

- Account switch during an outstanding read/write must not leak rows or apply an old response.
- Repeated close/reopen/link operations and stale revisions must not duplicate history or overwrite newer decisions.
- Closed opportunities must never remain in active hot/warm/cold counters; reopening cannot delete history.
- Cross-workspace/client or cancelled sale links must be rejected without changing inventory/payment.
- Setup edits and simulated receipts must never claim a verified connection, generated image or external send.

### Task 1: Persistent opportunity lifecycle

Files: python-service/opportunities.py, test_opportunities.py, app.py (router registration only), database/migrations/016_opportunity_lifecycle.sql.

- [ ] Write tests for auth/roles/Origin/CSRF, two businesses, transitions, CAS/replay, history and sale integrity; observe red.
- [ ] Implement GET/POST /api/v1/opportunities, PATCH /{id}, POST /{id}/close, /reopen, /sale and GET /{id}/history.
- [ ] All writes accept operation_id; existing-record writes accept expected_revision. Use transaction/row locking, immutable events and durable idempotency.
- [ ] Verify focused backend tests against disposable PostgreSQL and review constraints.

### Task 2: Content workspace and navigation

Files: frontend/socialmei-app.html, scripts/app.js (navigation only), content-preparation-store.js/content-studio.js, new content-workspace.js/integration-setup.js, focused CSS/tests.

- [ ] Write navigation and behavior tests, observe red.
- [ ] Move Divulgação to sidebar while preserving hooks; Create/Drafts/Agenda accessible panels, state/day filtering and existing edit/cancel semantics.
- [ ] Add exact review context and persistence feedback, preserving input on errors; optional compact Home summary from the same source.
- [ ] Add preparation-only setup UI consuming Task3, without credential fields; clear data and discard late replies on identity changes.
- [ ] Focused browser coverage desktop/mobile, light/dark, keyboard and source failures.

### Task 3: Server-backed connector preparation and opportunities UI

Files: python-service/integration_setup.py/test_integration_setup.py, migration017_integration_setup.sql; frontend/scripts/opportunity-lifecycle-store.js/opportunity-lifecycle.js; tests/opportunity-lifecycle*.cjs.

- [ ] Test setup persistence/roles/CAS, secret/unknown-field rejection and disconnected invariants; observe red.
- [ ] GET/PUT /api/v1/integrations/setup: response {workspace_id,revision,instagram,connected:false,transport:'none',readiness}; PUT {expected_revision,instagram:{username,account_type,meta_app_status,test_participants,reply_mode:'review'}}. Owner/admin writes only.
- [ ] Implement opportunities store against Task1 with identity-safe requests, no local fallback; render real opportunities separately from demonstration analysis in the existing view.
- [ ] Expose create/classify/close(reason)/reopen/history/link-existing-sale with explicit payment independence and closed counters. Preserve heuristic demo behavior.
- [ ] Test counter transitions, reload, conflict, failure and two identities through real isolated preview.

### Task 4: Workflow audit, integration, QA and delivery

Files: docs/DASHBOARD-FUNCTIONAL-READINESS.md, docs/N8N-CAPABILITY-MATRIX.md, tests/release-candidate-db.py, preview smoke and CI filters as needed.

- [ ] Catalogue all Git exports without credential values; record live login barrier separately. Map capabilities and missing verified contracts.
- [ ] Extend migration/restore rehearsal to016/017 and add preservation checks for new tables.
- [ ] Independently review security/data changes, fix findings and verify final source.
- [ ] Run Node, format, backend/Postgres, focused/real preview and complete browser checks; retain final-SHA evidence and honest skips.
- [ ] Create coherent Draft PR based on feat/isolated-preview, attach it, report exactly what is functional, simulated and blocked externally.
