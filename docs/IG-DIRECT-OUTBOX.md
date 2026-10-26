# Instagram Direct outbox — isolated contract

## Plan and scope

1. Add deterministic tests for text bounds, strict provider confirmation and closed defaults; demonstrate missing behavior before implementation.
2. Add migration 021 for a Direct-only outbox, operation ledger, attempt history and tenant/session/source constraints. Existing media preparation and fake publication queues stay unchanged.
3. Implement authenticated draft/edit/approve/cancel/read endpoints and an explicit responsible-user run endpoint. No frontend or scheduler.
4. Claim and attempt are committed before the injected HTTP boundary. Confirm only a validated recipient/message receipt. Unknown outcomes and expired dispatch leases are quarantined without retry.
5. Test disposable PostgreSQL concurrency, replay, approval invalidation, authorization, expiry/revocation, encryption failures and crash recovery; report local database skips separately from CI results.

## Safety contract

Only validated processed Instagram incoming messages in the current workspace can select the recipient/account/conversation. The client supplies a source message ID and reply text, never a provider recipient or workspace. Replies preserve original text, require nonblank UTF-8 of at most 1000 bytes and reject unsafe control characters. The normal reply window is 24 hours from the earlier of the referenced incoming event time and durable receive time; no HUMAN_AGENT exception. A newer incoming message requires a new or revised draft, not implicit extension of approval.

Approval records the exact revision/payload, approving user and authenticated session hash snapshot. Session snapshots deliberately have no foreign key so normal session cleanup and membership deletion remain possible. Actor membership references use ON DELETE SET NULL; a missing actor/session prevents future claims while preserving completed/uncertain history. Editing invalidates approval. Run rechecks the approving session/membership, runner rights, source window, exact connection identity, granted messaging scopes, token expiry and vault decryption before committing a dispatch claim. Rotating the encryption key does not change the destination, but reconnecting changes the connection and requires a new draft.

The run endpoint is manual and requires owner/admin; drafting and approval allow owner/admin/member. Viewer, expired/revoked sessions and removed memberships cannot authorize dispatch. After the durable claim commits, a second dispatch-gate transaction revalidates the runner, approver, complete destination binding, connection, scopes, vault and window. It acquires membership/session locks for runner and approver before locking the job row, avoiding FK cleanup lock inversion when they are different users. It holds workspace/session/membership/connection locks across the bounded injected HTTP call. Logout/disconnect that commits before this gate prevents HTTP; if the gate wins first, revocation serializes behind that call and cannot cancel an already-started effect. Its actual receipt is recorded truthfully. Claim durability is independent of gate rollback or process loss. There is no claimed exactly-once Meta delivery guarantee.

Every attempted dispatch is durable before HTTP. A timeout, malformed receipt, unexpected informational/redirect status, HTTP 408, server error or crash after claim is uncertain. Expired claims become uncertain, never automatically available again. Only a documented explicit 429 rejection can be retried after its bounded delay, with a maximum of three attempts; no arbitrary exceptions qualify as pre-effect failure. A local idempotency key prevents duplicate local operations, not duplicate provider effects.

Default service dependency returns 503. Enabling isolated flags does not create a transport, configure credentials or contact Meta. Only injected adapter/vault dependencies can execute tests. Provider tokens and raw provider responses never appear in product output, audit rows or logs. No credential fields are added to public configuration.

## Official references

- https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/messaging-api — `POST /<IG_ID>/messages`, recipient IGSID, UTF-8 text <=1000 bytes, receipt recipient_id/message_id.
- https://developers.facebook.com/documentation/instagram-platform/overview — normal 24-hour reply window. No provider idempotency key guarantee was established.

Live account/app review, transport installation, proxy/secret configuration and any production activation remain separate authorization gates. This unit neither publishes media nor changes n8n/WAHA.

## Verification status

Local PostgreSQL is unavailable; database cases remain skips pending disposable PostgreSQL16 CI. Focused tests include destination tampering, logout/disconnect before dispatch gate, serialized competing workers, crash after fake send, and late receipts after uncertain recovery. No skipped database case is counted as a pass.

`confirmed` means a validated provider acceptance receipt, not proof of delivery or reading. Incoming read/echo events are not currently reconciled as outbox confirmations. Expired dispatch quarantine requires a valid responsible runner but deliberately does not require the old approver session to remain active; it can never authorize another HTTP call.
