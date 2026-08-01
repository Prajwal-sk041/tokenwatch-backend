# Admin Guide

Platform administration is separate from organization roles. Grant access using the database `users.is_platform_admin` flag or the server-only `ADMIN_EMAILS` allowlist. The backend enforces access for all `/admin` routes; hiding navigation is not an authorization control.

Admin endpoints expose paginated users, organizations, subscriptions, usage, alerts, audit records, and invoices plus aggregate MRR, ARR, trials, requests, and tokens. Administrative access should be audited and restricted to named operators.
