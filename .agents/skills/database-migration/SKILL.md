---
name: database-migration
description: Prepare or review a SocialMEI PostgreSQL schema change using an additive migration, compatibility checks and data-safety gates.
---

1. Inspect current migrations and affected relationships.
2. Never edit an applied migration.
3. Define compatibility and existing-row preconditions.
4. Add a new incremental migration only when justified.
5. Test on a disposable PostgreSQL database, including incompatible-data failure behavior.
6. Before live application require explicit authorization, backup, target confirmation and rollback/failure plan.
7. Never silently delete, round or normalize business data to make a migration pass.
