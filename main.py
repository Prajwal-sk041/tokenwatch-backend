from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from logging_config import configure_logging, csrf_origin_middleware, request_id_middleware
from routers import alerts, audit, auth, budgets, ingestion, keys, onboarding, organizations, policy, sdk_keys, subscriptions, usage
from utils.database import check_database_connection


configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = None
    if settings.alert_scheduler_enabled:
        from scheduler import start_scheduler

        scheduler = start_scheduler()
        logger.info("alert scheduler started")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
        logger.info("alert scheduler stopped")


settings = get_settings()
app = FastAPI(
    title="TokenWatch API",
    description="API token usage monitor",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": False},
    lifespan=lifespan,
)
app.middleware("http")(request_id_middleware)
app.middleware("http")(csrf_origin_middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-TokenWatch-Key"],
)

app.include_router(auth.router)
app.include_router(keys.router)
app.include_router(usage.router)
app.include_router(alerts.router)
app.include_router(organizations.router)
app.include_router(onboarding.router)
app.include_router(sdk_keys.router)
app.include_router(ingestion.router)
app.include_router(policy.router)
app.include_router(budgets.router)
app.include_router(audit.router)
app.include_router(subscriptions.router)


@app.get("/")
def root():
    return {"message": "TokenWatch API is running"}


@app.get("/health/live", tags=["Health"])
def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["Health"])
def health_ready():
    if not check_database_connection():
        raise HTTPException(status_code=503, detail="Service is not ready")
    return {"status": "ready"}
