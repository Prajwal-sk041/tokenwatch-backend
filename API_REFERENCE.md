# API Reference

All JSON request models reject unknown fields. Browser routes use HttpOnly session cookies (Bearer access tokens remain supported for non-browser clients). Tenant browser routes use the active organization embedded in the session.

## Authentication

- `POST /auth/register` — create user, default organization, and verification challenge.
- `POST /auth/verify-email` — consume an email-verification token.
- `POST /auth/login` — create access and refresh cookies.
- `POST /auth/refresh` — rotate the refresh session and access JWT.
- `POST /auth/logout` — revoke the current session.
- `POST /auth/password-reset/request` — issue reset instructions without account enumeration.
- `POST /auth/password-reset/confirm` — update password and revoke all sessions.
- `POST /auth/disable` — disable the account and revoke sessions.
- `GET /auth/me` — current identity and organization.

## Organizations

- `POST /organizations`, `GET /organizations`
- `POST /organizations/{organization_id}/invites`
- `POST /organizations/invites/accept`
- `GET /organizations/{organization_id}/members`

## Keys

- Provider keys: `POST /keys/add`, `GET /keys/list`, `DELETE /keys/delete/{id}`.
- SDK keys: `POST /sdk-keys/{organization_id}`, `GET /sdk-keys/{organization_id}`, `POST /sdk-keys/{organization_id}/{id}/rotate`, `DELETE /sdk-keys/{organization_id}/{id}`.

## Ingestion and policy

- `POST /v1/ingest/usage` requires `X-TokenWatch-Key` with `usage:write`.
- `GET /policy/check` requires `X-TokenWatch-Key` with `policy:check` and returns `allowed`, `blocked`, `reason`, `remaining_budget`, `current_usage`, and `action`.

## Budgets, alerts, and audit

- `POST/GET /budgets/{organization_id}`
- `POST /alerts/create`, `GET /alerts/list`, `PATCH /alerts/toggle/{id}`, `DELETE /alerts/delete/{id}`, `GET /alerts/history`
- `GET /audit-logs/{organization_id}` requires admin or owner.

## Plans and subscriptions

- `GET /subscriptions/plans`
- `GET /subscriptions/{organization_id}`
- `PUT /subscriptions/{organization_id}` always returns `403`; paid-plan changes require the trusted Phase 4 billing service.

## Phase 3 product APIs

- `GET|PUT /onboarding/{organization_id}` resumes or persists onboarding progress.
- `POST|GET /onboarding/{organization_id}/test-event` records and verifies a real SDK-authenticated onboarding event.
- `GET /usage/events` returns paginated tenant usage with date, provider, and model filters.
- `GET /usage/aggregate` returns dashboard totals, breakdowns, trends, and a UTC projection.
- `PATCH|DELETE /budgets/{organization_id}/{budget_id}` manages the budget lifecycle.
- `PATCH|DELETE /organizations/{organization_id}/members/{member_id}` provides owner-controlled role and removal actions.
- `POST /organizations/{organization_id}/invites/{member_id}/resend` rotates and resends a pending invitation.
- `POST /auth/verify-email/resend` returns a non-enumerating resend response.
