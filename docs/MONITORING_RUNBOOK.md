# Monitoring Runbook

## Signals

- Availability: `/health/live`; dependency readiness: `/health/ready`; public components/incidents: `/status`.
- Structured JSON logs include request IDs and redact authorization/cookie/key data.
- Sentry FastAPI integration is enabled when `SENTRY_DSN` exists, with PII disabled and 10% tracing.
- Admin metrics cover subscriptions, conversion, churn and revenue; usage counters cover ingestion volume/cost.

## Recommended dashboards and alerts

Track request rate, 4xx/5xx, p50/p95/p99 latency, function duration/timeouts, database latency/errors, ingestion duplicate rate, counter reconciliation drift, scheduler success/age, alert and email retry/dead-letter counts, Stripe webhook failures/age, checkout conversion, frontend Core Web Vitals and client errors.

Page immediately on readiness failure, sustained 5xx, scheduler silence over 26 hours, reconciliation mismatch, webhook backlog, or payment processing errors. Create tickets for latency/error-budget trends and dead letters. Production currently lacks an independent monitoring destination; activate Sentry plus an external uptime check before public launch.
