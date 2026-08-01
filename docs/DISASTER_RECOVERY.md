# Disaster Recovery

Targets for initial paid launch: document RPO/RTO with the selected Supabase plan; recommended starting targets are RPO 24 hours with daily backups and RTO 8 hours, tightening with PITR when business requirements demand it.

## Recovery order

1. Declare incident, freeze writes where corruption is possible, preserve Vercel/Supabase/Stripe logs and timestamps.
2. Restore Supabase to a separate project or PITR point; never overwrite the only recoverable source during diagnosis.
3. Apply repository migrations in order and validate security advisors.
4. Repoint a preview deployment, run health, auth, tenant isolation, ingestion and dashboard acceptance.
5. Rebuild derived counters with `reconcile_usage_counters(..., true, actor)` and require zero drift.
6. Replay Stripe webhooks from Stripe; unique provider event IDs make replay safe. Re-drive failed alert/email records only after dependencies recover.
7. Promote the validated deployment, monitor, and publish an incident update.

Migration rollback uses a new forward migration unless the go-live runbook explicitly identifies a reversible deployment rollback. Backup/PITR purchase and a restore-to-new-project rehearsal remain owner-controlled launch blockers.
