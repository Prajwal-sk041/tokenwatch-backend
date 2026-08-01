# Disaster Recovery

- Recovery targets: RPO 24 hours initially; RTO 4 hours. Tighten before enterprise commitments.
- Keep automated Supabase backups and periodically restore into an isolated project.
- Preserve Stripe as billing source of truth and replay signed events into an idempotent endpoint after recovery.
- Revoke and rotate compromised SDK, provider, session, Stripe, Resend, Supabase, and Sentry credentials.
- Rebuild Vercel from immutable Git commits and reapply migrations in order.
- During an incident, publish status updates, preserve audit evidence, and avoid destructive cleanup until containment is complete.
