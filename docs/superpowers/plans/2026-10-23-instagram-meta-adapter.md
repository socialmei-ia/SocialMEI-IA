# Instagram Meta HTTP adapter implementation plan

Goal: implement the next functional, independently testable unit after PR103: Instagram Login token exchange and identity contracts with an injected transport. No network transport, router registration, frontend, database or production changes.

Spec: owner's attached PROMPT MESTRE, delivery A. The owner explicitly requests autonomous implementation and defers real connections, publishing, merge and deploy. Implement inline; coordinator reviewed the boundary before coding.

Architecture: retain existing fake laboratory and pure Meta contracts. A new adapter accepts a mandatory transport callable, fixed HTTPS endpoints, an explicit Graph version and registered callback. Requests keep secret-bearing form/query values out of repr and URL strings. No requests can occur from application startup or endpoints.

Base: PR103 e947d731f630fd01401d59ad66868d248c5fbd58, verified tree 114a8a7d478d9898b70af0aad59248773b9a2d3d. Local sparse snapshot reconstructed through GitHub, because direct git fetch is unavailable; publishing must use the exact native parent. PR101's subsequent commit only changes CI base-branch routing.

## Tasks

- [ ] Add failing tests in python-service/test_instagram_meta_adapter.py for code exchange, fixed hosts/callback, requested permissions, malformed and oversized responses, error redaction, no retry, redirect rejection, identity matching and professional account validation.
- [ ] Implement python-service/instagram_meta_adapter.py with mandatory injected transport, bounded HTTP metadata, typed secret-safe grants, exchange_code/get_identity/extend_token/refresh_token. Validate lifetime and refresh eligibility locally. Never add a default real transport.
- [ ] Expand tests for 429/5xx and bounded Retry-After metadata, expired grants, secret-safe repr and unknown outcomes; run focused and available backend suites. Report unavailable PostgreSQL/Docker separately.
- [ ] Document integration boundary, official sources, fake-provider verification and remaining OAuth/vault/webhook/outbox work in docs/INSTAGRAM-META-ADAPTER.md. No completion claim for entire Instagram integration.
- [ ] Fresh code review, resolve substantive findings, publish dependent Draft PR with only adapter/tests/docs/this plan. Run complete CI against native head.

## Review focus

1. Never retry code exchange automatically after timeout/unknown outcome.
2. No provider body or transport exception text in public errors/repr.
3. No arbitrary host, redirect or version-path injection.
4. No identity binding from untrusted browser workspace/account IDs.
5. No configured transport, external operation, token persistence or network side effect by importing/starting the application.

## Evidence and decisions

- Baseline pure Meta contracts: 8 tests passed.
- Full local backend dependencies/PostgreSQL/Docker are unavailable initially; CI must close those gaps.
- Direct Meta pages returned429. Official Meta documentation indexed by Context7 provided OAuth token, /me, exchange and refresh contracts. Treat API eligibility/version/scopes as unhomologated until staging with authorized test accounts.
