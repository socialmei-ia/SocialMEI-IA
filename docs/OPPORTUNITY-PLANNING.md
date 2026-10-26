# Shared opportunity planning

## Contract

Migration022 extends `crm_opportunities` with `estimated_amount` (0..1e9, cents), `follow_up_date` (calendar DATE or null), `planning_note` (140 UTF-16 units), `contacted`, `planning_initialized` and optional `legacy_planning` provenance. Defaults preserve the old absence of planning. `outcome_note` remains a separate closing reason of up to1000 characters; planning never changes a sale, payment or stock.

Create can save opportunity and planning atomically. PATCH uses the existing `operation_id` and `expected_revision`, history and operation ledger. Explicit zero/empty/false values initialize planning intentionally. Pure planning edits can update a closed opportunity without changing its commercial outcome. Commercial title/interest edits retain the existing state restrictions.

Decimal validation rejects negative, nonfinite, excessive or fractional-cent amounts without rounding. Dates accept only exact ASCII YYYY-MM-DD calendar values; null/empty clears the date, timestamps and date-time strings are rejected. Notes preserve their original Unicode/spacing. Unpaired surrogates, NUL and excess UTF-16 units are rejected instead of truncating. Emoji occupy two UTF-16 units, matching the existing browser maxlength.

Request fingerprints preserve the old canonical payload for requests without planning fields. Explicit new fields are included, so omitted amount and explicitly-zero amount cannot reuse the same operation key with different semantics. Existing operation replay returns the current authorized row, preserving the previous API contract without another history entry.

## Remote controls and compatibility

The existing opportunity controls read/write shared planning when authenticated remote mode is active. Create is one atomic operation; saves, date moves and contact registration use PATCH. Undo issues another expected-revision mutation and refuses intervening edits. A remote error preserves submitted controls and never writes browser fallback. No markup structure, styles, layout, animation or new screen is introduced; provenance wording on existing nodes reflects shared persistence.

The local/demo sidecar repository and its normalization/undo remain unchanged. `rawCandidates()` is an additional read-only interface which returns exact legacy metadata; it does not run the old truncating normalizer. Existing key: `socialmei-op8-local-v1:` plus encoded identity scope, envelope `{v:1,scope,items}`.

## Explicit legacy import only

There is no automatic import, new button or production migration of browser data. An authorized operator can review `SocialMEIOpportunityV8Bridge.listLegacyCandidates()` and explicitly call `importLegacyPlanning(id, legacy)` for one selected opportunity. The server resolves workspace exclusively from the authenticated session and requires `expected_revision` plus `planning_initialized=false`. Intentional remote zeros are protected exactly like nonzero values. Concurrent/stale imports receive conflict rather than overwriting remote work.

The raw v1 object must contain exactly `amount,date,note,contacted,updatedAt,events`. Missing/unknown fields, fractional cents, invalid dates/Unicode, note >140 UTF-16 units, more than20 events or event text >250 units are rejected, preserving the raw copy. No partial object is silently completed with defaults. Invalid candidates require explicit human review outside this unit.

The optional bounded provenance object retains client `updatedAt`/events as **untrusted legacy history**, not authenticated server events. The server records one ordinary edit event with reason `planning_import`, its own actor/time and before/after snapshots. Existing browser entries are never deleted or rewritten by candidates/import, on success, failure or identity switch. The regular browser JSON backup continues to include this key.

Operator review and explicit import in a live environment remain pending. This change does not authorize data import or production deployment.

## Verification

Deterministic Node tests cover raw-copy preservation, strict complete legacy objects, invalid values, lost responses/idempotency and account switching. Python tests cover money/calendar/Unicode contracts; disposable PostgreSQL tests cover atomic create/import rollback, revisions/replay, intentional-zero guard, tenants/viewers, history separation and SQL Unicode limits. The existing browser suite adds functional shared-control save/undo/conflict checks without weakening its original assertions.

Local PostgreSQL/browser execution may be unavailable; report their skips separately and require real CI results before claiming those checks passed.
