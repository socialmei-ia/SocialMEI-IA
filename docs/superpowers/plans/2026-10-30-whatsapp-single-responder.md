# WhatsApp pilot: persisted inputs and human control

**Goal:** Connect persisted WAHA references to the existing planner and let an owner pause automation from the native inbox.

**Architecture:** PostgreSQL remains the source of messages, channel identity and conversation state. The API exposes recent unplanned references to a private, inactive n8n poller; the existing planner, exclusive claim and receipt remain the only sending path. Pausing a conversation increments its revision and invalidates unclaimed decisions. An already acquired claim may be in flight and is never retried automatically.

**Constraints:** No migrations, fabricated products, real sends, public internal routes, workflow replacement or service restarts. Preserve private overlays, WAHA identity/history and existing workflows. The pilot sender stays closed until an explicit contact allowlist and approved response content are configured.

**Approach:** A private poller reuses persisted references without forwarding raw message bodies or racing the ingress transaction. Calling n8n synchronously from ingress would couple reception to n8n availability; a new queue/schema is unnecessary because unique decisions already provide a durable consumption record.

- [ ] Add focused API tests for pause before first decision, tenant/channel isolation, stale claim invalidation, explicit resume and bounded pending references.
- [ ] Add API status/pause and pending-reference endpoints using existing schema and auth protections.
- [ ] Add a small owner/admin control to the native V22 WhatsApp inbox; test failed writes and account changes.
- [ ] Prepare an inactive private n8n bridge with empty recipient allowlist and existing claim/receipt flow; test reference-only inputs and no default sends.
- [ ] Prepare reversible WAHA hook isolation with private backup, exact config comparison and health verification. Keep n8n workflow untouched.
- [ ] Run focused checks, open a PR against the release branch, verify CI and image provenance before any new API/gateway deployment.
- [ ] Only after reception isolation passes, request one inbound test from the authorized telephone. Verify persisted row and inbox without exposing content. Real catalog remains blocked on business data.

Recovery restores only the changed WAHA configuration or API/gateway images/overlays from a verified snapshot. Never restore the production database to undo a code deployment. Claimed and uncertain decisions remain terminal for automatic sending.
