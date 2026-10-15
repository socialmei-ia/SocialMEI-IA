# SocialMEI.IA repository instructions

## Product and scope

SocialMEI.IA is a CRM and operations product for MEIs and small businesses. Keep it simple for non-technical users while preserving room for multiple business profiles, channels, automations and future commercial intelligence.

The current application is the baseline. Do not turn a focused task into a redesign, framework migration or architecture rewrite.

## Working rules

- Use `ARCHITECTURE.md`, `docs/PROJECT-STRUCTURE.md` and `docs/ENVIRONMENTS.md` as canonical maps before broad changes.
- Preserve behavior unless the task explicitly changes it.
- Large visual features follow prototype-first: isolated prototype -> review -> explicit approval -> integration.
- Prefer small reviewable changes.
- Do not mutate AWS, live n8n, production/team databases, Docker runtime, GitHub administration or deployment config unless explicitly authorized.
- Git is the source of truth for code and reproducible configuration.
- Never expose secrets or use production data in automated tests.

## Agent routing

- Use `coordinator` for substantial cross-module work.
- Use `code-mapper` before changes when ownership or execution flow is unclear.
- Prefer specialized agents over generic ones: `fastapi-developer` for API, `postgres-pro` for PostgreSQL, `javascript-pro` for JS runtime behavior, `integrations` for n8n/WAHA, and `devops` / `aws-solutions-architect` for runtime architecture.
- For major UI work: product/UX -> UI design -> implementation -> QA -> finish gate.
- For AI work: architecture/requirements -> AI/NLP implementation -> evals -> observability.
- Do not run several implementation agents on overlapping files. Three concurrent agents is the normal upper bound for this repository.

## Code style

- Technical identifiers: English. UI copy: Brazilian Portuguese.
- Comments: short, useful, no emojis.
- Prefer simple names and direct control flow.
- Avoid artificial verbosity and speculative abstractions.
- Do not make code intentionally imperfect to look human.

## Contracts

- Do not rename API fields, routes, DB columns, localStorage keys, IDs, data attributes or externally referenced selectors without checking consumers.
- Preserve workspace isolation.
- Do not silently fall back from failed remote writes to browser persistence.
- Applied migrations are immutable; use incremental migrations.
- Git n8n exports and live n8n are separate evidence.

## Testing

Start with focused tests, then broader regression. Report failures/skips honestly. Common checks include `npm test`, `npm run format:check`, `npm run test:browser`, and Python unittest suites that exist in the checkout.

## Risky changes

Before live database/deploy/auth/n8n/infra changes, establish current state, target, backup when needed, rollback, smallest blast radius and post-change verification. Stop if these cannot be established.
