# Database instructions

- Never edit an applied migration; add a new incremental migration.
- Preserve tenant/workspace integrity.
- Do not make live data changes as part of refactors.
- Never truncate, bulk-delete or silently normalize business data without explicit approval and recovery plan.
- Before live schema changes: inspect compatibility, back up, define rollback/failure handling, then use the repository migration mechanism.
- Add indexes/constraints only for concrete integrity/query reasons.
- Keep PostgreSQL private and least-privilege; never expose 5432 publicly or commit credentials.
- Automated DB tests use disposable databases.
