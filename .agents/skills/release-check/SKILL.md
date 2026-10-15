---
name: release-check
description: Perform a pre-merge or pre-release SocialMEI readiness check covering diff scope, tests, secrets, migrations, docs and operational risk.
---

Check:
- diff matches requested scope;
- no secrets/private config were added;
- relevant tests pass;
- skips/blocked tests are explicit;
- migrations are additive and justified;
- API/localStorage/UI contracts were not accidentally renamed;
- docs reflect changed behavior/procedure;
- deployment impact and rollback are known when runtime changes exist;
- no unrelated redesign/refactor is bundled.

Return READY, BLOCKED or NEEDS DECISION. Do not merge/deploy unless separately authorized.
