# Phase 1A changes

Phase 1A establishes a secure, runnable baseline without adding billing, organizations, teams, or gateway features.

## Backend

- Consolidated environment loading into typed settings with startup validation.
- Consolidated Supabase access into one lazy server-only client.
- Removed token and secret-presence logging and the public alert trigger.
- Added JSON logging and request IDs.
- Restricted CORS to configured explicit origins.
- Added authenticated Fernet encryption for stored provider keys and masked responses.
- Added strict Pydantic request models for authentication, keys, usage, and alerts.
- Added liveness/readiness probes.
- Disabled in-process scheduling by default.
- Added security-focused tests.

## Frontend

- Reconstructed the corrupted landing page as valid TSX.
- Added validated API-base configuration, timeouts, session cleanup, and safe errors.
- Added error, not-found, loading, empty, and API-error UI.
- Added lint, type-check, build, and foundation-test commands.

## Known limitations

- Existing provider-key rows stored before Phase 1A must be migrated or recreated before the new list endpoint can decrypt them.
- Authentication still uses browser local storage; hardened cookie sessions remain Phase 1 work.
- Database migrations and RLS definitions are not introduced in 1A.
- The scheduler must be deployed separately when alerts are enabled.
