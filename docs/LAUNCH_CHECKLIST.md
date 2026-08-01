# Launch Checklist

- [ ] Stripe products and monthly/annual prices created in test and live mode
- [ ] Plan price IDs stored server-side
- [ ] Signed Stripe webhook configured and replay tested
- [ ] Resend domain verified; SMTP fallback tested
- [ ] Sentry DSN configured and test event received
- [ ] Database migration applied; RLS and advisors clean of new blockers
- [ ] Checkout, trial, invoice, failure, portal, upgrade, downgrade, and cancellation acceptance-tested
- [ ] Resource and usage entitlements verified for every plan
- [ ] Privacy, terms, cookie, refund, and security pages reviewed for the operating business/jurisdiction
- [ ] Backup, restore, incident response, support, tax, and refund ownership assigned
- [ ] Production health, logs, analytics, and alerting monitored after release
- [ ] Official Node and Python SDK artifacts signed and published from tagged commits
- [ ] Dependency, secret, OWASP, webhook replay, SSRF, CSRF, CSP, and tenant-isolation reviews passed
- [ ] Status page and support escalation tested during a simulated incident
