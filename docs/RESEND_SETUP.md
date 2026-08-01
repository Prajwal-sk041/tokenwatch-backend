# Resend Setup

Configure `RESEND_API_KEY` and a verified `SMTP_FROM_EMAIL`. Resend is the primary channel; configured SMTP is the automatic fallback. Neither credential may use a public/frontend environment-variable prefix.

Templates cover verification, password reset, invitations, trial ending, payment failure, invoices, and subscription activation. Delivery logs store a recipient hash rather than the address.
