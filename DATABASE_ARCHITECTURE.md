# Database Architecture

TokenWatch uses PostgreSQL through Supabase. The authoritative schema is the ordered SQL in `migrations/`; dashboard-created tables are not a dependency.

## Tenancy and identity

`users` stores application identities and account security state. `organizations` is the tenant boundary. `organization_members` links identities to tenants with `owner`, `admin`, `member`, or `viewer` roles. Every operational resource contains `organization_id`; foreign keys, application authorization, and RLS all enforce that boundary.

## Keys and ingestion

`api_keys.key_type` separates encrypted provider credentials from hashed TokenWatch ingestion credentials. Provider secrets are recoverable only by the backend because they are encrypted. SDK keys are never recoverable: only a SHA-256 hash and non-secret prefix are stored. Rotation creates a new row and revokes the previous row.

`usage_logs` contains immutable ingestion events with organization-scoped idempotency and provider-request uniqueness. `usage_counters` contains atomic daily and monthly rollups. Cost is calculated by the backend pricing catalog.

## Commercial and policy data

`plans` and `subscriptions` represent commercial entitlements. `budget_policies` supports organization, user, provider, and model scopes. `alert_rules` and `alert_history` represent notification configuration and delivery outcomes. `audit_logs` records security and administrative activity.

## Integrity

All tables use UUID primary keys and timezone-aware timestamps. Foreign-key columns and tenant query paths are indexed. Soft deletion is used for organizations, users, keys, policies, alerts, and subscriptions. Cascades remove organization-owned operational data; identity and plan references use restrictive or nullifying deletion where history must survive.

## Migration compatibility

The Phase 2 migration preserves incompatible Phase 1 tables under `*_phase1_legacy` names before creating the canonical schema. No legacy table is silently dropped.
