# Operational scripts instructions

- Scripts must be explicit about target environment and destructive effects.
- Prefer dry-run/read-only inspection when practical.
- Never print secrets or complete .env contents.
- Refuse production-targeted operations when target is ambiguous.
- Deployment/backup/migration helpers should record non-sensitive source SHA and result.
- Prefer idempotent operations; document non-idempotent ones.
- Destructive scripts require clear confirmation and recovery procedure.
