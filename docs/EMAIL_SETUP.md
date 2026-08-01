# Email setup

TokenWatch sends email verification, password-reset, and organization-invitation messages through generic SMTP configuration. No provider-specific integration is required.

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_USE_TLS` in the backend runtime. Keep credentials server-only and scope them independently for development, preview, and production.

When SMTP is unavailable, production APIs return a safe delivery status without exposing action tokens. Password-reset requests always use the same non-enumerating response. Local development can expose a preview URL only when `EMAIL_PREVIEW_ENABLED=true`; this must remain disabled in production. Tokens and message bodies are never written to ordinary logs.

After configuration, verify sender-domain requirements with the selected provider, request a new verification message, and check backend delivery-status logs for success or failure metadata.
