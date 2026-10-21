# Dashboard functional readiness

## Authorized outcome

The user approved implementing the functional change list with minimal interaction. Build on PR90/ecaa4bd, preserving #83/#89/#90 ancestry. Use existing product structure and design tokens. The later visual redesign is explicitly outside this work. Real Instagram connection waits for an authorized professional test account and Meta app; WhatsApp waits for a dedicated number.

## Deliverables

1. Divulgação becomes a first-class sidebar item on desktop/mobile. Preserve selectors and script order; remove the hidden-tools discovery dependency.
2. Existing editor, local drafts and authenticated simulated preparation become an understandable Create/Drafts/Agenda flow, with filters, explicit persistence mode, review, edit/cancel and failures preserving input. Home may show a compact summary from the same source, without a new layout system.
3. Persist commercial opportunities separately from heuristic message analysis. Associate a manually created opportunity with an existing customer in the authenticated workspace. Interest is unknown/cold/warm/hot; outcome is open/won/lost. Won is not payment; lost captures gave_up/other_supplier/price/timing/other. Closed records leave active-interest counters. History, reopen and a separate new opportunity preserve earlier decisions.
4. An explicit sale association selects an existing sale of the same customer/workspace. Do not create sales, reduce inventory, mark payment or infer purchase success from sentiment. Unique association prevents duplicate attribution; changing a sale must not silently rewrite opportunity outcome.
5. Persist an Instagram preparation checklist: public username, reported account type, reported Meta app existence, test participants and review-only reply mode. These are user-reported setup data, not verification or a connected account. No passwords, tokens or connector URLs in the form. Server responses always say connected=false and transport=none until a separately implemented real connector is authorized and tested.
6. Inventory n8n Git exports and accessible live evidence separately. Reuse existing workflow contracts where demonstrated; account for publishing, captions, images, sentiment/RAG and message ingestion separately. Do not infer that a publishing workflow generates media or captions.

## Boundaries and failure behavior

- Existing Vanilla JS/classic scripts, FastAPI and PostgreSQL16 remain.
- PT-BR UI, English identifiers; existing API/routes/selectors remain compatible.
- Authenticated workspace comes from server session. Writes require existing Origin/CSRF/role boundaries. Viewer reads only; integration setup writes owner/admin only.
- New immutable migrations016/017 only, applied in disposable environments. No production migrations, AWS, Caddy/team changes, live n8n writes, credential reads, Meta/WhatsApp send or publication.
- CAS and idempotent operation IDs protect opportunity writes. Append-only history records actor, action, previous/new state and notes. Identity changes invalidate frontend requests and clear account-scoped state.
- Failed remote writes never become browser-only success. Demonstration records never silently become remote opportunities. Missing setup/provider capability remains visibly unavailable.
- Message-generated suggestions remain drafts. Automatic replies, OAuth, real webhook subscription, hosted media, credentials and operational workers require the future account/provider stage. Preparatory UI does not imply homologation.

## Acceptance

Sidebar access works with keyboard/mobile. Create/drafts/agenda share truthful status. Two authenticated businesses cannot read or mutate each other's opportunity/setup records. Closing and reopening adjust counts and survive reload/two sessions. Same operation replay cannot duplicate changes; stale revisions conflict. Sale linking does not change sales/inventory/finance. Setup saving cannot enable connectors. Default flags retain no transport. Unit, backend/Postgres, focused browser and full regression evidence belongs to the final SHA. Live n8n audit remains unconfirmed if authentication is absent.
