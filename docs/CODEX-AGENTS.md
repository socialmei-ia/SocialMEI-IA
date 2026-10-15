# Codex agents and skills

This repository includes project-specific Codex instructions.

## Persistent instructions

- Root: `AGENTS.md`
- Frontend: `frontend/AGENTS.md`
- API: `python-service/AGENTS.md`
- Database: `database/AGENTS.md`
- n8n: `n8n-workflows/AGENTS.md`
- Operations: `tools/AGENTS.md`
- GitHub automation: `.github/AGENTS.md`

## Agents

Project-scoped agents live in `.codex/agents/`:
`scout`, `architect`, `product-designer`, `frontend`, `backend`, `database`, `integrations`, `devops`, `qa`, `security-reviewer` and `code-reviewer`.

The project config enables multi-agent mode and limits concurrent subagents to 3 to reduce conflicting edits.

## Skills

Reusable workflows live in `.agents/skills/`:
`feature-plan`, `prototype-first`, `visual-qa`, `database-migration`, `n8n-workflow-review`, `team-deploy`, `release-check`, `maintainability-review` and `incident-triage`.

## First test

Restart/reopen Codex on this branch and ask:

```text
Use the scout to map only the files related to Clientes. Do not change anything. Return paths, contracts, tests and risks.
```

Expected: read-only mapping and no working-tree changes.

Then ask:

```text
Use the architect to propose a plan for a small feature. Do not edit files.
```

Recommended flow for larger changes:
Architect -> specialist implementation -> QA -> security/code review -> release check.

Avoid running several implementation agents against the same files concurrently.
