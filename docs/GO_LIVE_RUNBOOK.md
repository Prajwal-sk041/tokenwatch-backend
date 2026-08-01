# Go-Live Runbook

1. Freeze release branches and confirm all checks pass.
2. Back up Supabase and verify restore instructions.
3. Apply migrations before application promotion; run security/performance advisors.
4. Verify live Stripe key/webhook environment, synchronize catalog, and complete a low-value live purchase/refund.
5. Verify Resend domain and SMTP fallback with a controlled recipient.
6. Confirm Sentry traces, alerts, and request IDs.
7. Smoke-test registration, onboarding, SDK policy/ingestion, checkout, portal, invoice, cancellation, support, and status.
8. Monitor 5xx, latency, webhook failures, payment failures, email failures, and database saturation.
9. Roll back the application artifact if errors rise; use a forward database migration rather than destructive down migrations.
