---
name: feature-plan
description: Plan a non-trivial SocialMEI feature before implementation, especially when it crosses frontend, API, database, integrations or product decisions.
---

1. Read only the relevant architecture/project-structure docs and target code.
2. State the user problem and definition of done.
3. Map affected modules and contracts.
4. Separate blocking product decisions from implementation choices.
5. Identify whether schema, API, integration or deployment changes are truly required.
6. Define focused tests and rollback/compatibility concerns.
7. Prefer the smallest design with a clear future extension point.
8. For large UI concepts require prototype-first.

Output a concise plan. Do not implement unless implementation was also requested.
