# Phase 5 Security Review

- Broken access control: organization membership and platform-admin dependencies cover protected routes.
- Cryptography: provider keys are encrypted; SDK/session/action tokens are hashed; TLS is mandatory outside localhost.
- Injection: Pydantic forbids unknown fields, PostgREST parameterizes database operations, and no raw user SQL is used.
- Design: subscription state is webhook-driven; price and cost values are server-owned.
- Misconfiguration: typed fail-fast settings, explicit CORS, CSP/security headers, and test/live Stripe key checks.
- Dependencies: pinned application dependencies and CI audit gates.
- Authentication: secure HTTP-only cookies, rotation, revocation, CSRF origin validation, and short access tokens.
- Integrity: Stripe raw-body signature verification, five-minute signature tolerance, environment validation, and idempotent event IDs.
- Logging: request IDs and structured logs avoid secret values; audit records cover sensitive actions.
- SSRF: user webhook destinations require HTTPS. Future delivery must also resolve and block private/link-local addresses before connecting.

Open risk: production secrets, DNS/email-domain state, Stripe configuration, and external alert destinations require live acceptance testing after configuration.
