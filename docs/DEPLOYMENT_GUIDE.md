# Deployment Guide

Deploy database migration `202608010004_phase4_monetization.sql` before the application build. Validate RLS and database advisors. Then configure server-only Stripe, Resend/SMTP, and Sentry variables in the backend deployment and public site/API URLs in the frontend deployment.

Deploy preview artifacts from the Phase 4 branches. Run API, browser, webhook-signature, tenant-isolation, and entitlement checks against preview. Merge only after both builds and checks succeed. Production deployment must be followed by health checks and a runtime-error scan.
