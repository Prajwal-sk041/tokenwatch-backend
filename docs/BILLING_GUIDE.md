# Billing Guide

TokenWatch treats Stripe as an external payment provider behind `BillingProvider`. Plans and entitlements are stored server-side. Checkout creates a hosted Stripe session; only signed, idempotently processed webhooks change subscription and invoice state.

Owners can start checkout and open the billing portal. Browser redirects never activate a plan. Failed payments retain `past_due` state for recovery while hard entitlement decisions use the synchronized subscription record.

Supported events: `checkout.session.completed`, subscription created/updated/deleted, invoice paid/failed, and trial-ending notices.
