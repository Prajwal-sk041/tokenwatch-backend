# Email setup

TokenWatch uses Resend first and SMTP as a fallback. Configure `RESEND_API_KEY` and `SMTP_FROM_EMAIL`, or the SMTP host, port, username, password and sender variables. `EMAIL_PREVIEW_ENABLED` is permitted only outside production and never logs action tokens. Delivery attempts are recorded in `email_deliveries` using a recipient hash.

Production activation requires a verified sending domain, SPF/DKIM/DMARC, provider credentials, and bounce/complaint monitoring. Do not use a personal mailbox sender.
