# Profile synchronization API (schema 1)

Only authenticated account mode enables these routes. Workspace and user are resolved from the server session and membership; requests cannot select either ID. Unknown query parameters are rejected with 422. All responses, including errors, use `Cache-Control: no-store`. Existing session, Origin and CSRF protections apply. No files, logos, drafts, credentials, tokens, theme definitions or custom theme data are accepted.

`GET /api/v1/workspace-profile` returns `{schema_version: 1, revision: 0, profile: null}` when no profile exists. Reads never create rows. A saved profile is returned with its positive revision. All members may read; only business owners and admins may write. Platform administrator status does not bypass this role check.

`PATCH /api/v1/workspace-profile` accepts exactly `{schema_version: 1, expected_revision: 0, profile: {...}}`. The full profile contains `version` (1), `businessName`, `segment`, `activity`, `offers`, `services`, `productCategories`, `capabilities`, `modules`, `ignoredSuggestions` and `completed`.

The 23 segment IDs, nine capability names and 13 module IDs match `frontend/scripts/business-profile.js`. Offers must contain at least one of `products` and/or `services` after normalization. Every capability and `completed` is a strict JSON boolean. Text fields and service/category/module items are at most 120 characters; lists contain at most 30 items, offers at most two. Ignored suggestion IDs are at most 160 characters and 60 items. The serialized profile is limited to 32 KiB. Unknown fields, unknown IDs, nulls, incorrect types and oversized values return 422 without reflecting submitted data.

Normalization trims and deduplicates strings; unavailable offers clear the related categories/services and inventory/appointment capabilities. Modules unavailable for the resulting offers or capabilities are removed. Ignored suggestion IDs are deduplicated without trimming, matching the browser normalizer. `businessName` is always the canonical account workspace name (trimmed to the existing profile's 120-character bound); submitting another name never renames the workspace. GET applies the current canonical name as well. `completed` must be `true`. Empty offers and incomplete profiles return 422 without creating a row or changing a saved revision. A null GET profile is the only representation of a not-yet-saved profile; onboarding drafts remain in the browser.

`GET /api/v1/auth/preferences` returns `{schema_version: 1, revision: 0, preferences: {...}}` when missing. Defaults are `theme: "auto"`, `notificationsEnabled: true`, and notifications `{message: true, payment: true, pending: true, routine: true, channel: "app", quietFrom: "", quietTo: ""}`.

`PATCH /api/v1/auth/preferences` accepts exactly `{schema_version: 1, expected_revision: 0, preferences: {...}}` with the full preference object. Theme is `auto`, `light` or `dark`. Notification switches are strict booleans, channel is `app`, and both quiet-time fields are empty or both are valid 24-hour `HH:MM` strings. Overnight ranges are valid. Each user's preferences are private to their membership, including when the same user belongs to multiple workspaces. Viewers may update their own preferences.

Both PATCH routes return the same envelope as GET with the incremented revision. `expected_revision` is a strict nonnegative JSON integer (maximum 9007199254740990); zero creates only an absent row. Atomic insert-if-absent or conditional update prevents concurrent callers from overwriting each other. A stale revision returns 409 with a Portuguese detail string. The browser must reload, present the current state and obtain a new explicit save decision. It must never automatically retry using the newly fetched revision. No remote failure falls back to local browser writes.

Unauthenticated requests return 401, unauthorized writes and invalid Origin/CSRF return 403, malformed bodies return 422, disabled or misconfigured authentication and unavailable database/schema return 503. Migration `013_workspace_profile_sync.sql` is incremental and does not seed or import local profiles. The two tables separate workspace profile state from membership-scoped preferences, with FK cascade and JSON/version/revision constraints.

Run focused integration tests using a strictly disposable PostgreSQL database via `TEST_DATABASE_URL`:

```sh
cd python-service
python -m unittest test_workspace_profile -v
```

The suite applies repository migrations and truncates test data; never point it at a team or production database.
