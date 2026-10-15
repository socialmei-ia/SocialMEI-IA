---
name: n8n-workflow-review
description: Review or prepare a SocialMEI n8n workflow while keeping Git exports, live runtime, credentials and multi-tenant messaging contracts distinct.
---

- Determine whether evidence comes from Git export or live runtime.
- Map trigger, input, output, systems, API calls, writes, credential needs and error paths.
- Classify the workflow.
- Check authenticated ingress, workspace identity, external IDs, idempotency/deduplication and retries for real channels.
- Prefer n8n as orchestrator; keep substantial reusable Python logic in a versioned/testable runtime when appropriate.
- Never expose credentials or mutate live workflows without explicit authorization.
