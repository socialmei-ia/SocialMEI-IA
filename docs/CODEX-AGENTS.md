# Codex agents and skills

This repository includes project-specific Codex instructions and a curated agent team for SocialMEI.IA.

The team was designed from the project's actual stack and workflows, with patterns adapted from:
- OpenAI Codex custom-agent conventions;
- VoltAgent/awesome-codex-subagents;
- aws-samples/sample-codex-agent-team;
- wshobson/agents.

The repository keeps its own smaller instructions instead of copying entire public agent libraries.

## Persistent instructions

- Root: `AGENTS.md`
- Frontend: `frontend/AGENTS.md`
- API: `python-service/AGENTS.md`
- Database: `database/AGENTS.md`
- n8n: `n8n-workflows/AGENTS.md`
- Operations: `tools/AGENTS.md`
- GitHub automation: `.github/AGENTS.md`

## Core orchestration

- `coordinator`: substantial cross-module work and specialist routing.
- `code-mapper`: read-only code path and ownership mapping.
- `architect`: software architecture and implementation planning.
- `reviewer`: independent PASS / CONDITIONAL PASS / FAIL review.
- `code-reviewer`: maintainability and correctness review.

## Product and interface

- `product-designer`: product flows and prototype-first design.
- `ux-researcher`: turns real MEI feedback into product decisions.
- `ui-designer`: implementation-ready interface and interaction guidance.
- `frontend`: focused frontend implementation in the existing app.
- `javascript-pro`: browser runtime, async/state/event behavior.
- `browser-debugger`: evidence-driven browser reproduction and fixes.
- `ui-ux-tester`: end-to-end UI/UX flow testing.
- `accessibility-tester`: keyboard, semantics, ARIA, focus and contrast.
- `anti-ui-slop-reviewer`: finish gate against generic AI-looking UI.
- `performance-engineer`: measured frontend/backend/database performance review.
- `qa`: general regression validation.

## Backend, data and integration

- `fastapi-developer`: FastAPI contracts, auth-aware logic and API implementation.
- `postgres-pro`: PostgreSQL schema/query/locking/migration review.
- `integrations`: n8n, WAHA, webhooks and channel boundaries.
- `security-auditor`: auth, tenant isolation, secrets, exposure and webhook security.
- `devops`: Docker, Caddy, CI/CD, AWS runtime, backup and rollback.
- `aws-solutions-architect`: AWS reliability, security, cost and architecture review.

## AI, scoring and chatbot

- `ai-engineer`: model/tool/retrieval orchestration and runtime behavior.
- `nlp-engineer`: PT-BR message understanding and purchase-intent analysis.
- `prompt-engineer`: prompts and structured-output contracts after architecture is defined.
- `eval-engineer`: regression and go/no-go evaluation design for AI behavior.
- `ai-observability-engineer`: AI traces, metrics, privacy-safe telemetry and debugging.
- `data-analyst`: funnel, pilot, conversion and score outcome analysis.

## Research

- `market-researcher`: CRM/MEI competitor and positioning research.
- `research-analyst`: technical research and architecture tradeoffs from current sources.

## Concurrency

`.codex/config.toml` enables multi-agent operation, limits the session to 3 concurrent subagents and allows nesting depth 2 where supported.

The existence of many specialists does not mean they should all run. Normal tasks should use only 2-4 relevant agents.

## Recommended workflows

### New visual feature

```text
coordinator
-> product-designer / ux-researcher when product decisions are unclear
-> ui-designer
-> prototype-first
-> user approval
-> frontend + javascript-pro when needed
-> qa / ui-ux-tester
-> accessibility-tester
-> anti-ui-slop-reviewer
-> reviewer
```

### Bug in current interface

```text
code-mapper
-> browser-debugger
-> frontend or javascript-pro
-> qa
-> reviewer
```

### FastAPI / database feature

```text
architect
-> fastapi-developer
-> postgres-pro only if schema/query behavior changes
-> qa
-> security-auditor when auth/data boundary changes
-> reviewer
```

### WhatsApp / n8n

```text
code-mapper
-> integrations
-> fastapi-developer when API changes are needed
-> devops when runtime/container changes are needed
-> security-auditor
-> qa
-> reviewer
```

### Customer Score / purchase intent

```text
ux-researcher
-> data-analyst
-> architect
-> nlp-engineer + ai-engineer
-> prompt-engineer only when prompt behavior is involved
-> eval-engineer
-> ai-observability-engineer
-> security-auditor
-> reviewer
```

### AWS / deployment

```text
aws-solutions-architect
-> devops
-> qa/smoke validation
-> reviewer
```

## Skills

Reusable workflows live in `.agents/skills/`:
`feature-plan`, `prototype-first`, `visual-qa`, `database-migration`, `n8n-workflow-review`, `team-deploy`, `release-check`, `maintainability-review`, `incident-triage`, `agent-routing`, `mei-pilot-research`, `ai-eval-gate` and `interface-finish-gate`.

## First test

Restart/reopen Codex on this branch and ask:

```text
Use code-mapper to map only the files related to Clientes. Do not change anything. Return the execution path, owning files, contracts, tests and risks.
```

Expected: read-only mapping and no working-tree changes.

Then:

```text
Use coordinator to plan a small feature. Delegate only if a specialist materially improves the plan. Do not edit files.
```

Do not merge this configuration until these discovery tests work in the Codex version being used.
