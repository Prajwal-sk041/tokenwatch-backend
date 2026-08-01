# Email Production Guide

## Supported flows

Registration verification, password reset, organization invite, welcome, trial ending, subscription activation/cancellation, invoice paid, payment failed, and budget/alert messages use the shared email abstraction. Authentication responses remain enumeration-safe and action tokens are opaque, hashed at rest, expiring and single-use.

## Delivery behavior

Resend is primary when `RESEND_API_KEY` and `SMTP_FROM_EMAIL` are present. SMTP over TLS is the fallback. Logs contain provider/message identifiers and recipient hashes, never tokens, message bodies, email addresses or credentials. Failed payloads are Fernet-encrypted using the existing server encryption key, retried by the authenticated daily scheduler, then moved to `dead_letter` after three attempts.

## Remaining activation

1. Verify a sender domain in Resend (recommended) or configure a TLS SMTP account.
2. Set `SMTP_FROM_EMAIL` and the selected provider variables in Vercel Production and Preview; never use `NEXT_PUBLIC_` names.
3. Redeploy, confirm `/status` reports email operational, then exercise registration verification, reset, invite, warning, hard-limit, trial, subscription and payment-failure templates to controlled test recipients.
4. Confirm `email_deliveries` records `sent`, provider IDs and hashed recipients; confirm no secrets or addresses appear in runtime logs.
5. Trigger one controlled failure, verify retry timing and `dead_letter` after exhaustion, then resolve/replay according to the support runbook.

Do not enable production marketing/bulk email through this transactional channel.
