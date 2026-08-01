# Stripe production setup

Set `STRIPE_ENVIRONMENT=live` only with live `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, and live product/price IDs. Configure the webhook to the backend billing webhook route, enable required event types, configure tax and customer portal policy, and complete one low-value live transaction followed by refund before accepting customers. Test and live identifiers are intentionally separate.
