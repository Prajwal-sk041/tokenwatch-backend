# Rollback test

Application rollback uses the last verified Vercel deployment. Database migrations are forward-fixed unless a reviewed reversal is demonstrably data-safe. Before migration, capture backup status; after rollback, verify health, authentication, ingestion and policy checks. Replay verified Stripe events by provider event ID and retry failed alerts from stored delivery state. Counters are recoverable from immutable usage logs.
