# Isolated WAHA durable ingress

## Scope and official contract

This is a controlled WEBJS-shaped receiver, not an installed WhatsApp connection. No live WAHA/n8n/API call, session operation, QR, pairing, webhook configuration or sending is performed. Historical server version/edition/session evidence is not current runtime confirmation.

Official sources:

- https://github.com/devlikeapro/waha-docs/blob/main/content/docs/how-to/events/index.md — HMAC SHA512 over raw HTTP body, headers `X-Webhook-Hmac` (128 hex digits) and `X-Webhook-Hmac-Algorithm: sha512`; envelope `session/me/event/timestamp` and message/ACK shapes.
- https://github.com/devlikeapro/waha-docs/blob/main/content/docs/how-to/receive-messages/-chat-ids.md — direct `@c.us`, opaque `@lid`, group/channel/broadcast namespaces.
- https://github.com/devlikeapro/waha-docs/blob/main/static/swagger/openapi.json — event payload schemas.

The official generic message example includes fromMe=true despite describing an incoming event. Consequently event names alone never determine direction. `message` and `message.any` normalize to the same stable message identity. Envelope time is integer milliseconds; payload time is seconds, with fractions accepted only to microsecond precision. Existing timestamps and original text/spaces/newlines are preserved.

## Closed, server-owned provisioning

`/internal/waha/{instance}/webhook` depends on an injected `WahaIngressService`. Its default dependency returns503. Isolated flags `SOCIALMEI_WAHA_INGRESS_MODE=isolated` and `SOCIALMEI_WAHA_LAB_ENVIRONMENT=isolated`, shared data and authentication must all be enabled. Flags never construct a registry, load a secret or contact a provider.

The registry is an immutable copy of frozen server bindings: instance, unique HMAC key, exact session, expected own `@c.us` account, workspace/channel IDs and channel revision. Instance/session fixture prefixes are forbidden. No public owner endpoint provisions this registry. Payload workspace fields are rejected; `metadata`/names/environment are never identity or authorization. Signed session and `me.id` must match the binding exactly. The existing fixture endpoint remains synthetic and unchanged.

Raw body bounds (64KiB), signature/algorithm and unique headers are checked before JSON/SQL. Duplicate JSON keys, invalid UTF-8/JSON and malformed identifiers/timestamps are rejected. Direct text requires an explicit recipient matching the verified account, fromMe=false, hasMedia=false, a direct sender and body text <=8192 UTF-8 bytes. Internal identifiers/MID bounds are documented implementation limits, not claimed provider maxima. No credentials, payloads, message text or personal identifiers are logged or returned by ACK; only aggregate counts are returned.

## Existing storage and ordering

Migration023 adds no tables. `crm_canais.ingress_provisioned` defaultsfalse, with validated account identity and a partial unique active account across all instances. Existing channels and fixture behavior remain intact.

`crm_eventos_canal` gains account snapshot, hashed global event key, inbox message ID and explicit waha origin. Composite FKs bind channel/workspace/account and inbox workspace/origin. Existing ledger fields/statuses remain in use; normalized payload storage stays empty. Message text is stored once through the private shared inbox append, not duplicated into legacy channel message tables.

Processing locks global account, workspace and channel, then rechecks provisioned/active/not-sending flags, exact identity and revision before committing message+ledger atomically. A disconnect that commits before channel verification blocks delivery; one that loses the channel row lock waits for the admitted transaction. ACK occurs only after commit. Reconnect retains the same contact thread through stable account/contact references, not channel ID.

Global account+MID dedupe is independent of instance/session/workspace and webhook delivery ID. Replays after an operator-controlled transfer to a new channel/session cannot copy historical messages into another business. Canonical fingerprints exclude envelope delivery time/order and engine internals. Message/echo/unsupported variants share one MID family to prevent kind-changing replays. ACK identity uses MID+ack state and ignores delivery time; ACKs never create messages or claim delivery/read confirmation for an outbound job.

Transfers deactivate the old provisioned channel before enabling another binding. Existing history FKs prevent silently changing its account or reassigning a historical instance/session; same-session reassignment is not an owner operation. Existing RESTRICT retention is preserved. Explicit future hard purges would remove dedupe history and require a separate replay/deletion policy; no eternal retention guarantee is made.

## Inbox and unsupported events

The existing inbox exposes explicit origin `waha`, capability `waha_inbox` and validated `waha:<JID>` references. LIDs stay opaque and distinct from phone JIDs; there is no profile lookup, inferred phone, name matching or automatic alias merge. Generic display name avoids exposing identity as a contact name.

Echo/fromMe, ACK, media and group/non-direct messages are ignored in the ledger without creating incoming text. Unsupported event names are rejected. `_data`, QR, media URLs, metadata and raw payloads are not persisted. Unknown event types, engines, account aliases and optional provider features need explicit homologation; nothing silently becomes synthetic data.

The existing managed conversation path keeps composer/status actions blocked and synthetic analysis unavailable for provider rows. No new controls, markup structure, stylesheet, layout or animation is introduced. No workflow or outbound adapter is enabled.

## Verification and external gates

Tests use synthetic signed bodies and disposable PostgreSQL only: signature-before-DB, duplicate headers/JSON, bounds/registry isolation, concurrent duplicate/conflict, rollback, disconnect, transfer replay, unique active ownership, FKs, native read and blocked analysis/send. Node/browser fixtures verify explicit provenance, opaque LIDs, tenant scope, literal text and blocked composer. PostgreSQL/browser skips must be reported separately until exact-commit CI passes.

Before any live activation: verify actual WAHA version/edition/engine and HMAC support, approved account/chip, server-owned registry provisioning and key custody, network/proxy access policy and logging. No production configuration or import/activation is authorized by this implementation.
