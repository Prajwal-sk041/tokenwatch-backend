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
