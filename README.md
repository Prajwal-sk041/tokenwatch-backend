# TokenWatch Backend

FastAPI service for TokenWatch authentication, usage reporting, encrypted provider credentials, and alerts.

## Local setup

1. Copy `.env.example` to `.env` and replace every required placeholder locally.
2. Generate `API_KEY_ENCRYPTION_KEY` with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
3. Install dependencies: `python -m pip install -r requirements.txt`.
4. Start the API: `uvicorn main:app --reload --port 8000`.

Never commit `.env`. `SUPABASE_SERVICE_KEY`, `JWT_SECRET`, SMTP credentials, and the encryption key are server-only.

## Validation

```bash
python -m compileall -q .
python -m pytest
python -c "import main"
```

Health probes are `GET /health/live` and `GET /health/ready`. The readiness probe performs a minimal database query and returns no internal error details.

The in-process alert scheduler is disabled by default. Production should invoke alert processing from one dedicated worker or scheduled job, not every web process.

Provider API keys are encrypted with Fernet before Supabase storage. API responses expose only metadata and a masked display value. Rotating `API_KEY_ENCRYPTION_KEY` requires a planned ciphertext migration.

## Account security

Registration, password reset, and authenticated password changes share one policy: at least 5 characters, including at least one uppercase letter, one number, and one special character. Changing or resetting a password revokes existing sessions.

Email verification is mandatory. Production must configure either `RESEND_API_KEY` plus a verified `SMTP_FROM_EMAIL` domain, or all SMTP settings. When delivery is unavailable, registration succeeds in a pending-verification state and reports that delivery could not be confirmed; it never pretends an email was sent.
