---
name: agent-routing
description: Choose the smallest useful SocialMEI specialist team for a task and prevent unnecessary multi-agent fan-out or overlapping edits.
---

1. Classify the task: product/UX, frontend, API, database, integration, AWS/runtime, AI, research or review.
2. Use code-mapper first only when ownership/execution flow is unclear.
3. Pick one primary implementer and only the reviewers/specialists that materially reduce risk.
4. Keep concurrent implementation scopes file-disjoint.
5. Prefer 2-4 agents for a normal task.
6. Require independent review for security/data/deploy/large-feature changes.
7. Never let a coordinator implicitly authorize live AWS, database, n8n or WAHA mutation.

Return the selected agents, their order, why each is needed and which agents are intentionally not used.
