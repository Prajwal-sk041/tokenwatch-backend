from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()

from routers import auth, keys, usage, alerts

scheduler_instance = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler_instance
    from scheduler import start_scheduler
    scheduler_instance = start_scheduler()
    yield
    if scheduler_instance:
        scheduler_instance.shutdown(wait=False)
        print("[SCHEDULER] 🛑 Stopped")

app = FastAPI(
    title="TokenWatch API",
    description="AI-powered API token usage monitor",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(usage.router)
app.include_router(alerts.router)

@app.get("/")
def root():
    return {"message": "TokenWatch API is running 🚀"}

@app.get("/test-alerts")
def test_alerts():
    from routers.alerts import check_alerts_for_all_users
    check_alerts_for_all_users()
    return {"message": "✅ Alert check triggered! Check your email."}