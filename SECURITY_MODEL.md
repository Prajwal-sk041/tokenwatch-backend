# Security Model

## User sessions

Passwords are bcrypt hashes. Email verification is mandatory before login. Access JWTs are short lived and contain a session ID, token version, unique JWT ID, and active organization. Refresh credentials are opaque, hashed in `auth_sessions`, single-use, and rotated as a family. Logout, password reset, and account disable revoke sessions. Browsers receive Secure, HttpOnly cookies with explicit SameSite behavior; frontend JavaScript does not store tokens.

## Machine authentication

SDK keys use the `tw_live_` prefix, hashed storage, permissions, expiration, revocation, last-used timestamps, and one-time disclosure. They cannot authenticate dashboard endpoints. Login JWTs cannot authenticate ingestion or `/policy/check`.

## Data protection

Provider credentials and SDK credentials are separate key types. Provider secrets use authenticated Fernet encryption. SDK keys use one-way hashes. RLS is enabled on all public tables. Tenant ownership is checked in every service query, and foreign keys/indexes reinforce the model.

## Ingestion trust boundary

Payload schemas reject unknown fields and invalid token counts. Event timestamps use a bounded replay window. Idempotency and provider request IDs are organization-unique. Costs are calculated from the server pricing catalog; client-supplied cost is forbidden.

## Audit and notifications

Authentication and administrative actions create immutable audit events. Emails use configured SMTP, webhooks require HTTPS and bounded timeouts, and Slack/Teams are explicit non-delivering stubs in this phase. Secrets and action tokens are never logged.
