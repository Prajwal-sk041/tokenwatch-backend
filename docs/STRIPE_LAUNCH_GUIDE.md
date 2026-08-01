# Stripe Launch Guide

## Software verification

Stripe Checkout uses server-selected price IDs, a 14-day trial, hosted payment collection and organization metadata. The customer portal controls downgrade/cancellation. Webhooks require the raw body, Stripe signature verification with 300-second tolerance and environment matching. `billing_events(provider, provider_event_id)` prevents duplicates; failed events can be retried and notification emails are idempotent per Stripe event. Subscription, entitlement and invoice state is synchronized server-side.

## Remaining test activation

1. Complete Stripe account sign-in and accept provider terms.
2. In test mode, create/provision Starter, Pro and Team products/prices using the guarded admin catalog operation.
3. Configure `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_ENVIRONMENT=test`, and optional tax behavior in Vercel Production/Preview.
4. Register `https://tokenwatch-backend.vercel.app/billing/webhooks/stripe` for the handled event set documented in `services/billing.py`.
5. Redeploy and prove checkout success/cancel, trial, portal upgrade/downgrade/cancel/resume, invoice paid, payment failed, duplicate delivery and retry.
6. Compare Stripe objects with `subscriptions`, `invoices`, `billing_events`, audit logs and displayed entitlements.

## Live activation

Complete business/KYC/bank/tax information, create live products/prices, install a separate live webhook secret, switch all three Stripe settings atomically, redeploy, and run a low-value live acceptance transaction. Never copy test keys into live configuration or store card data in TokenWatch.
