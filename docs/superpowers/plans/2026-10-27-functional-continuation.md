# Functional candidate continuation

**Base:** PR #131, `8d0318bcf4262afde9798b8ad91ce4924cf046b9`. All three CI jobs passed; preview required a retry.

**Scope:** follow the owner’s continuation brief without duplicating PRs115–130. Keep separate reviewable units: operational preparation/preview, account/team, knowledge. Existing001–031 migrations are immutable. No live credentials or SSH are available; no production/Meta/WAHA operation is attempted.

- [x] Confirm current PRs, Git ancestry and CI.
- [ ] Reproduce preview overflow; capture route, dimensions and actual overflowing elements before correcting source or readiness. Keep exact overflow assertion.
- [ ] Add failing tests for staged release preparation against the exact001–031 source: OAuth-only, photo, functional; reject gaps/unknown schemas, preserve private overlays, source checksums, flags and rollback. No migration/deploy side effects.
- [ ] Run unit, real Caddy and disposable PostgreSQL regression/backup/restore.
- [ ] Investigate account/team on a separate branch, preserving current authenticated grants and workspace restrictions.
- [ ] Review existing private PDF parsing/access and correct demonstrated flaws with tests.
- [ ] Commit complete units, open/update Draft PRs, execute CI and report only real external blockers.

**Review focus:** anonymous media shadowed by authentication; source31 with installed26; configuration drift; cross-workspace stale sessions; animation/iframe readiness before layout measurements. Real OAuth, SMTP delivery, Instagram publication/Direct and WhatsApp messages remain unverified until authorized service access.
