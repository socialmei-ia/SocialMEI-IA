---
name: incident-triage
description: Diagnose a SocialMEI failure such as a broken integration, Python/n8n error, API outage or deployment regression before attempting a fix.
---

1. Capture exact symptom and environment.
2. Reproduce safely when possible.
3. Identify code, config, dependency, network, data or runtime drift.
4. Collect minimal sanitized logs/state.
5. Compare source-of-truth config with live runtime.
6. Propose the smallest reproducible fix and test outside production when possible.
7. For live fixes require explicit authorization and rollback.

Do not repair missing dependencies by manually installing them in a live container unless that is intentionally versioned and reproducible.
