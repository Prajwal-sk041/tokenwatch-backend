# Security baseline

Production secrets are supplied through the deployment environment and never committed or printed. The Supabase service key remains backend-only. JWT and encryption keys must be independently generated and rotated under an operational plan.

Provider credentials are encrypted using Fernet authenticated encryption before storage. List responses decrypt only to derive a masked value and never return plaintext or ciphertext.

## Authentication and API behavior

- Access tokens expire after 30 minutes by default.
- Protected routes reject missing or invalid bearer tokens.
- Internal exceptions are logged without request credentials and returned as generic client messages.
- Request IDs are accepted/generated and returned in `X-Request-ID`.
- CORS origins are explicit and environment-controlled.
- Input models reject unsupported providers, malformed emails, weak passwords, negative usage, invalid alert values, oversized strings, and future timestamps.

## Operations

- `/health/live` confirms process liveness.
- `/health/ready` performs a safe database check.
- The alert scheduler is off by default and must have a single production owner.
- Logs must not contain authorization headers, JWT payloads, API keys, passwords, or SMTP credentials.

## Remaining Phase 1 work

Database migrations/RLS, login rate limiting, email verification, password recovery, refresh/revocation, cookie-based sessions, key rotation tooling, observability, and deployment manifests remain outside Phase 1A.
