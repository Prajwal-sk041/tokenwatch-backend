# Scaling Guide

- Move high-volume ingestion counters to batched database functions or a durable queue when write contention appears.
- Monitor usage index hit rates, connection saturation, webhook backlog, and p95/p99 latency.
- Partition `usage_logs`, `audit_logs`, and `billing_events` by time before they reach tens of millions of rows.
- Archive according to plan retention and legal requirements.
- Run schedulers and retry workers as singleton durable jobs, not per serverless instance.
- Add regional strategy only after measuring customer latency and data-residency requirements.
