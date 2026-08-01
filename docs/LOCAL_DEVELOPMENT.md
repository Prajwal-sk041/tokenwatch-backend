# Local development

## Backend

Copy `tokenwatch-backend/.env.example` to `.env`. Supply a development Supabase project, a server-only service key, a random JWT secret of at least 32 characters, and a Fernet key. SMTP may remain blank when email delivery is not being tested.

```bash
cd tokenwatch-backend
python -m venv .venv
.venv/Scripts/activate
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

`ALERT_SCHEDULER_ENABLED=false` is the safe default. If enabled locally, exactly one API process should run. Production scheduling belongs in a dedicated worker or platform scheduler.

## Frontend

Copy `tokenwatch-frontend/.env.example` to `.env.local` and keep only the public API URL there.

```bash
cd tokenwatch-frontend
npm install
npm run dev
```

## Checks

Backend: `python -m pytest`, syntax compilation, application import, and route discovery.

Frontend: `npm test`, `npm run lint`, `npm run typecheck`, and `npm run build`.

Readiness requires database connectivity; liveness does not.
