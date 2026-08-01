# RC-1 Launch Blockers

Audit date: 2026-08-01. Evidence: production Vercel projects, public probes, Supabase migrations/advisors, database reconciliation, and local release suites.

## Critical

- **Email delivery — MANUAL ACTIVATION.** Software supports Resend, SMTP fallback, encrypted retry payloads and dead-lettering. Production reports `email: not_configured`; a verified sender and provider credential are still required.
- **Paid billing — MANUAL ACTIVATION.** Checkout, portal, signed webhooks, replay protection, invoices, trials and entitlements are implemented. Production reports billing and webhook `not_configured`; Stripe account/test configuration and end-to-end acceptance remain required before charging customers.
- **Backups — MANUAL ACTIVATION.** Supabase project is healthy but the Free plan does not provide launch-grade backups/PITR or a restore rehearsal.
- **External alerting — MANUAL ACTIVATION.** Application health/logging exist; no independent uptime/error notification channel is activated.

## High

- **Custom domain — MANUAL ACTIVATION.** Only `vercel.app` domains are configured. A customer-facing domain and matching email sender domain are required.
- **Legal/business review — MANUAL ACTIVATION.** Published legal pages are product placeholders and require founder/legal approval before paid launch.

## Medium

- **Cold latency — COMPLETE WITH WARNING.** Observed public probes were 0.34–1.48 seconds. This is acceptable for RC-1 functional validation, not a capacity SLO. Run staged load after deployment and monitor p95.
- **Legacy database advisories — COMPLETE.** Server-only tables intentionally have RLS with no client policies. RC-1 fixes the two legacy per-row auth policy warnings and missing support-ticket foreign-key indexes.

## Low

- **Custom analytics — DEFERRED.** Not required for RC-1. Operational counters and Sentry hooks exist.

## Completed gates

- Backend and frontend production deployments READY.
- `/health/live`, `/health/ready`, `/status`, plans and critical frontend pages returned HTTP 200.
- Database, API and scheduler reported operational.
- Phase 5.6 migration applied; all 1,500 current usage rows reconcile exactly with monthly counters across two organizations (5,999,615 tokens, $250.27846660, zero mismatched organizations).
- Backend 52 tests and frontend 13 tests, lint and type-check pass after RC-1 remediation.
