# n8n instructions

- Treat Git workflow exports and live n8n as different evidence.
- Do not activate/delete/rename/import/publish live workflows unless explicitly authorized.
- Back up/export before modifying live workflows.
- Preserve IDs, webhook contracts and credential references unless deliberately migrating.
- Never commit credentials/tokens/secrets.
- Use descriptive node/workflow names.
- Use n8n as orchestration; substantial reusable Python logic should normally live in a versioned/testable Python runtime or officially supported mechanism.
- Real messaging requires workspace/channel/conversation/message identity, authenticated ingress, external IDs, dedup/idempotency, retries and clear errors.
- Do not convert legacy flows to multi-tenant by renaming fields.
- Google Sheets remains paused unless explicitly resumed.
