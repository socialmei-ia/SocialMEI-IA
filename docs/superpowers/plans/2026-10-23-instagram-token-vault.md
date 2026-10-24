# Instagram token vault implementation plan

Goal: add authenticated encryption for the future durable Instagram connection store, without connecting accounts, reading configuration, storing production tokens or changing database/frontend/routes.

Spec: owner functional delivery A, encrypted token requirement. Previous isolated HTTP adapter PR104 is the dependency. Inline execution, no product/infra approval needed for local implementation; merge/deploy/real credentials remain unauthorized.

Architecture: AES-256-GCM with random12-byte nonce, versioned envelope and key identifier. Authenticate provider/workspace UUID/connection UUID/external account ID/version/key ID as AAD. Require an explicit immutable keyring, active key and server-established identity binding. No default key or environment loading.

- [x] Define failing tests for roundtrip, random nonce, workspace/account/connection tampering, key rotation, missing/invalid keys, malformed envelopes, bounds and safe errors.
- [ ] Implement python-service/instagram_token_vault.py and pin the installed cryptography dependency (50.0.2) in requirements.txt. No handwritten crypto or key derivation.
- [ ] Run focused and backend tests; independent review of encryption boundary.
- [ ] Document key separation, rotation, loss/recovery, no logging/DTO serialization and remaining durable persistence/state/binding. Publish dependent Draft PR and verify CI on final head.

Review focus: stale/retired keys must fail closed; ciphertext cannot move across businesses/connections/accounts; envelope metadata must be authenticated; no token/key in repr/errors; no module import or app startup writes or network calls.

Verification environment: local PostgreSQL/Docker unavailable; full CI must close those gaps. No schema change needed for this encryption-only unit. Ruling: durable binding and state require their own DB transaction unit; an encryption helper alone must never be described as completed OAuth or persisted connections.
