# Stripe Setup

1. Create recurring monthly and annual prices for Starter, Pro, and Team.
2. Store price identifiers in the `plans` rows (`stripe_price_id`; annual IDs in `features.stripe_annual_price_id`). Do not put price IDs in browser code.
3. Configure server-only `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`.
4. Register `POST /billing/webhooks/stripe` and select the supported events listed in `BILLING_GUIDE.md`.
5. Keep the webhook endpoint API version aligned with the pinned Stripe Python SDK.
6. Enable `STRIPE_TAX_ENABLED=true` only after Stripe Tax registrations and product tax codes are configured.

Test in Stripe test mode first. Confirm duplicated events are acknowledged without duplicate subscriptions or invoices, invalid signatures return 400, and payment failures appear in both billing state and audit history.
