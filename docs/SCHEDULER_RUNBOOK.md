# Scheduler Runbook

Vercel invokes `GET /internal/jobs/alerts` at `0 0 * * *` UTC. The route requires a constant-time comparison against `Authorization: Bearer CRON_SECRET`. Production scheduler registration and a successful invocation were previously verified.

Each run retries failed alerts, evaluates active rules from daily/monthly counters, suppresses duplicates with a deterministic unique key, delivers email/webhooks, records history, and processes due email retries/dead letters. Webhook targets must resolve only to public HTTPS addresses, limiting SSRF.

On failure: inspect the invocation request ID and structured logs; verify health/readiness; check `alert_history.next_retry_at`, `attempt_count`, and `email_deliveries`; do not delete history. Re-run once with the scheduler credential only after the dependency is healthy. Escalate repeated failures, preserve evidence, and rotate `CRON_SECRET` if exposure is suspected.
