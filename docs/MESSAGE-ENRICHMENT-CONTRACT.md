# Message enrichment — isolated schema 1 (#81)

Base: PR #79 `cb7fa6efcf7fc48b1b676af86d2929330c5c4995`, containing #77/#75. Main remains separate. #80 is an open release-preparation issue, not a merged PR. No production integration or workflow inspection/execution is performed.

## Boundaries

FastAPI resolves business/user/role from its existing authenticated session. Human writes retain Origin/CSRF. Owners/admins manage synthetic RAG documents; owners/admins/members may create synthetic messages, request enrichment and review drafts. Viewers only read. IDs supplied by a browser never establish tenancy. All responses are no-store and all reads filter workspace. Missing schema or disabled mode fails closed.

The isolated namespace stores only explicitly labelled synthetic conversations, immutable incoming messages, enrichment jobs, events/replay protection and plain-text documents. Legacy channel tables and browser conversations are neither migrated nor ingested automatically. Conversation identity is workspace + channel + synthetic connected-account reference + external contact reference, never display name. Legacy name-based synchronization is blocked in authenticated mode; local legacy conversations stay intact. The synthetic source never writes its messages, results or drafts to browser storage.

## HTTP contract

Prefix `/api/v1/message-enrichment`:

- `GET /capabilities`: `{schema_version:1, workspace_id:server_identity, mode:"disabled"|"stub", transport:"none"}`. Default disabled; no real HTTP transport is implemented.
- `GET /conversations`: `{workspace_id:server_identity,items:[{id, channel, account_ref, contact_ref, contact_name, revision, messages:[{id, external_message_id, text, occurred_at, revision, enrichment: object|null}]}]}`. Numeric IDs are safe integers. All data is synthetic and belongs to the authenticated workspace.
- `POST /synthetic-messages`: `{schema_version:1, operation_id:UUID, channel:"whatsapp"|"instagram", account_ref:string, contact_ref:string, contact_name:string, external_message_id:string, text:string}`. Account/contact references are synthetic identifiers, not phone numbers or live account IDs. Returns `{conversation_id,message_id,revision,replayed}`. Persistent operation and external-message deduplication: identical replay returns the original result; changed content under a reused key returns 409. Conversation revisions increment only on a new message.
- `POST /messages/{id}/enrich`: `{schema_version:1,operation_id:UUID,expected_revision:int}`. Creates/replays a persisted job and invokes only the deterministic stub. Returns the persisted enrichment envelope: `{id,message_id,revision,status,sentiment,confidence,explanation,suggested_reply,citations,transport:"none"}`. Status is `pending_review` when processed; final decisions are immutable (new analysis is required to create another review); `expired`, `invalidated` and `superseded` results are unavailable; sentiment positive/negative/neutral/uncertain, confidence low/medium/high is heuristic, not statistical. No send API exists.
- `GET /conversations/{id}/enrichments`: `{items:[enrichment...]}` for the same workspace, bounded history.
- `PATCH /jobs/{id}/review`: `{schema_version:1,expected_revision:int,decision:"approved"|"rejected",suggested_reply:string}`. CAS preserves concurrent human decisions. Approval stores a draft only, never sends it.
- `GET /documents`: `{workspace_id:server_identity,items:[{id,title,revision,expires_at}]}`. No private URL/file fetching.
- `POST /documents`: `{schema_version:1,operation_id:UUID,title:string,mime_type:"text/plain",content:string}`. Strict UTF-8 text, 32 KiB max, no binary/PDF/image interpretation. At most 50 active documents/business, 30-day retention; expired content must not be retrieved by RAG.
- `DELETE /documents/{id}?expected_revision=N`: explicit owner/admin removal, CAS, content purged and dependent suggestions invalidated. No shared vector memory. Retrieval is bounded lexical matching over this workspace's unexpired documents only; document text is untrusted context, never instructions or authorization.

The three GET envelopes carry the server-resolved workspace ID. It is response metadata, never an input selector; the browser verifies it against its captured identity and the existing verified browser scope before accepting results. Other tabs changing the browser scope clear synthetic rows, drafts and forms. Rejected requests include unknown fields, arbitrary workspace IDs, invalid types, overlong payloads, unsafe text, unknown channel and invalid UUID/revisions. Expected statuses: 401/403/404/409/422/429/503, with sanitized errors.

## Internal adapter protocol

Backend-only adapter: disabled or stub, no network client. Signed envelopes bind schema version, opaque job ID, event UUID, timestamp, attempt and payload hash using HMAC-SHA256; signature verified with constant-time comparison, bounded clock skew/expiry, persistent replay protection and bounded retry/rate limits. Job IDs resolve workspace on the server; callbacks cannot choose a workspace. Timeouts and late/out-of-order results cannot replace human reviews or newer revisions. A callback route may accept these envelopes only in isolated stub mode with a server-only test signing key, never the n8n API key. Production transport intentionally absent.

No HTTP callback is installed in this round: the internal signed adapter function is tested with an isolated stub only. Future connector ingestion, actual document/PDF extraction/embeddings, verified workflow binding and external sending need separate contracts and authorization. The observed workflow `K8Z9SVLEsR0yKVPc` and the conflicting REVIEW label are not assumed equivalent; their current relationship remains unconfirmed. No live hostname/credential is configured here.

## Frontend and verification

Reuse the native Inbox, thread and design tokens. Open an explicit synthetic-analysis panel; show `Sugestão da IA — não enviada`, source/heuristic explanation, editable draft and persisted review. Synthetic messages must never become real sent messages. Viewer controls read-only; network failure, including a failed explicit reload, preserves draft and no local fallback write occurs. Authenticated data stays in memory, discarded across identity changes; legacy local keys remain intact.

Tests cover two independent authenticated sessions, two workspaces/same display name, different channel/accounts/contacts, deduplication/replay/concurrency, CAS/out-of-order/expiry, HMAC tampering/retry/rate limits, RAG deletion/isolation, roles/auth/CSRF and offline UI. Run Node, Python/Postgres disposable and full browser/CI on final HEAD. Captures in native navigation, mobile/desktop, light/dark, keyboard and reduced motion. Rollout/rollback is documentation only; migration is incremental and never applied to a real database in this task.
