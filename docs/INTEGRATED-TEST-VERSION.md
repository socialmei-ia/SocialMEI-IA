# Integrated test version — PRs #69, #70, #71 and #74

This branch is a review/test candidate, not a production release. No deployment or merge into main is authorized here.

## History

Created from main `4336181fc9156d386cc46158ced708b6efda7be5`.
Git ancestry was verified before integration:

- #69 `a4b00e5ddece886235b610883cf2caa8216313dc` is an ancestor of #70 `46822cbc1a2f138043c02fd459b6dbbbd43c1d98`.
- #70 is an ancestor of #71 `57c735f4e9a82ea2d6f7b836ad885a4bab131b95`.
- Merge #74 `7e925dbc5a6c63d0904805b09326d466159e8082`, then #71. Both merged cleanly, preserving original commit identities. #69 and #70 were not cherry-picked again.
- Existing PR branches remain unchanged; #72 is separate. No force-push or history rewrite.

## Functional state

| Area                               | Integrated state                                                                   | Limit                                                                              |
| ---------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Frontend / Reports                 | Mobile financial charts, controls and report-tab focus safeguards                  | Financial definitions, exports, snapshots and identity/workspace storage preserved |
| Opportunities                      | Existing analysis and human review preserved                                       | Experimental heuristics; no conversion probability                                 |
| Onboarding / personalization       | Existing account, profile and catalog flows preserved                              | Business profile remains local as documented                                       |
| Divulgação                         | Native local editor/drafts and media preview                                       | No upload or publication; real publish action remains disabled                     |
| External Instagram pilot           | Inherited opt-in preparation, hidden/disabled by default                           | Do not enable: workflow/account authorization and isolation remain unapproved      |
| Authenticated Instagram simulation | Explicit frontend/backend opt-in, mock accounts, metadata and `simulated` receipts | Test database only; no binary upload, worker, n8n or Meta transport                |
| n8n protocol                       | Strict offline payload and HMAC validation library                                 | No HTTP sender, webhook activation or real account binding                         |

Both public configuration flags `instagramPublisher.mode` and `instagramSimulation.mode` remain `disabled`. An absent backend `SOCIALMEI_INSTAGRAM_MODE` blocks the API with 503 before database access. Migration 012 is versioned for testing, but has not been applied to any real database.

## Verification

- Node: 258 tests passed; formatting passed.
- Python backend and disposable PostgreSQL: 160 passed, no skips. Container/network removed after use; no public DB port.
- Python repository contracts: 25 passed, five opt-in skips; all five gateway tests passed in the explicit isolated gateway execution.
- Instagram: 13 tests passed with non-database socket destinations blocked; no unexpected connections.
- New browser integration test uses only controlled same-origin mocks: authenticated opt-in, account creation by keyboard, local PNG metadata, simulated 503, retry preserving idempotency, receipt/history and 1440/390 light/dark. No default feature activation or real transport.
- 28 native-app captures cover Home, Inbox, Opportunities, Finance, Reports, Divulgação and Settings in 1440/390 light/dark, with viewport overflow checks. Sample data is explicitly marked as fictitious. Simulation has four additional captures.
- The full browser and remote CI results, artifact link and exact final SHA are recorded in the Draft PR, rather than inferring success from partial checks.

One initial local full-browser run timed out at `account-browser.cjs:622`, waiting for the authentication screen after reload. Two focused executions then passed. No authentication behavior, timeout or assertion was changed speculatively; the original cause is not confirmed. Keep this observation distinct from the unresolved Finance edit timeout in Issue #73. The Issue must remain open.

## Local review

From this branch's repository root:

```sh
npm ci
python3 -m http.server 5500 --bind 127.0.0.1
```

Open `http://127.0.0.1:5500/frontend/socialmei-app.html`, enter the local demonstration and use Settings to enable the explicitly fictitious sample if desired. This is the official HTML/navigation, not a separate application. Remote account features require the documented isolated backend; never point a local review at production. Automated simulation evidence uses in-memory API fixtures, not a connected account.

## Human gates

- Review this integrated Draft PR before any merge. Existing PRs are not merged/closed by this task.
- Investigate Issue #73 Finance diagnostics if the original timeout recurs; green CI does not establish its cause.
- Real Instagram publication remains blocked pending account/instance authorization, private media storage, worker/status persistence, replay/idempotency/callback contracts and homologation. No live publishing test is part of this delivery.
- Production database migrations, backup/restore operations, credentials, AWS/n8n/Meta changes and deployment require separate explicit authorization. Disposable database tests are not evidence of a real environment's readiness.
