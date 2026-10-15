---
name: team-deploy
description: Prepare or execute an authorized SocialMEI team/AWS deployment with source SHA, minimal blast radius, backup gates, rollback and verification.
---

Use only when the current task explicitly authorizes deployment.

1. Confirm target, checkout path, source branch/SHA and known working tree.
2. Determine exactly which services changed.
3. Back up data/configuration when needed.
4. Record previous and target SHAs/images.
5. Update using the approved team deployment path.
6. Rebuild/restart only necessary services.
7. Verify health/readiness and focused smoke tests.
8. If critical validation fails, stop and use rollback.
9. Record changed and intentionally untouched areas.

Never print secrets.
