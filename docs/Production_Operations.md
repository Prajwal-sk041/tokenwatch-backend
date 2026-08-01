# Production Operations

Daily: check uptime, readiness, errors, scheduler age, failed/dead-letter email/alerts, Stripe webhook failures and reconciliation drift. Weekly: review dependency/security advisories, latency trends, audit anomalies, support queue and backup status. Monthly: test session/key revocation, restore evidence, counter rebuild in a non-production target, Stripe replay, access lists and incident contacts.

Deploy only reviewed commits through preview → acceptance → merge → production. Database DDL must be an ordered migration and precede code that requires it. Roll back the application alias for code-only regressions; use forward migrations for schema correction. Never paste secrets into tickets, logs, PRs or browser-visible variables.
