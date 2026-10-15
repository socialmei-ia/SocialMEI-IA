# FastAPI instructions

- Keep routers, validation, database operations and authorization boundaries easy to follow.
- Preserve routes and request/response contracts unless explicitly changed.
- Resolve workspace from authenticated server-side identity.
- Preserve session, Origin and CSRF protections for writes.
- Use parameterized DB access and explicit validation.
- Never log secrets, passwords or session tokens.
- Centralize environment configuration.
- Python logic that must run in AWS must be versioned with declared dependencies.
- Prefer reusable/testable Python service logic over opaque n8n scripts when appropriate.
- Add focused tests for changed behavior.
