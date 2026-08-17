from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, HTTPException

from config import get_settings
from dependencies import Principal, get_optional_principal, require_platform_admin
from schemas.requests import SupportTicketCreate
from services.audit import record_audit
from services.rate_limit import consume
from services.alerts import evaluate_alerts
import secrets
from utils.database import check_database_connection, get_db


router = APIRouter(tags=["Operations"])


@router.get("/internal/jobs/alerts")
def run_alert_job(request: Request):
    configured = get_settings().cron_secret
    supplied = request.headers.get("authorization", "").removeprefix("Bearer ")
    if not configured or not secrets.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Invalid scheduled-job credential")
    return evaluate_alerts()


@router.get("/status")
def public_status(response: Response):
    settings = get_settings()
    response.headers["Cache-Control"] = f"public, max-age={settings.public_status_cache_seconds}, stale-while-revalidate=60"
    database_ok = check_database_connection()
    incidents = get_db().table("service_incidents").select("service,title,message,status,impact,started_at,resolved_at").order("started_at", desc=True).limit(50).execute().data or [] if database_ok else []
    active = {x["service"] for x in incidents if x["status"] != "resolved"}
    configured = {"api": True, "database": database_ok, "scheduler": bool(settings.cron_secret),
        "email": bool((settings.resend_api_key and settings.smtp_from_email) or (settings.smtp_host and settings.smtp_username and settings.smtp_password and settings.smtp_from_email)), "billing": bool(settings.stripe_secret_key),
        "webhook": bool(settings.stripe_webhook_secret)}
    services = [{"name": name, "status": "outage" if name in active else ("operational" if ready else "not_configured")} for name, ready in configured.items()]
    overall = "operational" if all(x["status"] == "operational" for x in services if x["name"] in {"api","database"}) and not active else "degraded"
    return {"status": overall, "checked_at": datetime.now(timezone.utc).isoformat(), "services": services, "incidents": incidents}


@router.post("/support/contact", status_code=201)
def contact(payload: SupportTicketCreate, request: Request, principal: Principal | None = Depends(get_optional_principal)):
    consume(request, "support", 5, 3600)
    if principal is None and payload.email is None:
        raise HTTPException(status_code=422, detail="Email is required when contacting support without signing in")
    organization_id = principal.organization_id if principal else None
    user_id = principal.user_id if principal else None
    row = get_db().table("support_tickets").insert({"organization_id": organization_id, "user_id": user_id,
        "category": payload.category, "subject": payload.subject, "message": payload.message,
        "metadata": {"page_url": payload.page_url, "contact_email": str(payload.email) if payload.email else None}}).execute().data[0]
    record_audit("support.ticket_created", organization_id=organization_id, actor_user_id=user_id, target_type="support_ticket", target_id=str(row["id"]), metadata={"category": payload.category})
    return {"id": row["id"], "status": row["status"]}


@router.get("/internal/metrics", dependencies=[Depends(require_platform_admin)])
def metrics():
    db = get_db()
    subscriptions = db.table("subscriptions").select("status,plans(monthly_price)").is_("deleted_at", "null").execute().data or []
    active = [x for x in subscriptions if x["status"] == "active"]
    mrr = sum(float((x.get("plans") or {}).get("monthly_price") or 0) for x in active)
    trials = sum(1 for x in subscriptions if x["status"] == "trialing")
    canceled = sum(1 for x in subscriptions if x["status"] == "canceled")
    converted_rows = db.table("subscriptions").select("id,conversion_at").execute().data or []
    converted = sum(1 for x in converted_rows if x.get("conversion_at"))
    return {"mrr": round(mrr,2), "arr": round(mrr*12,2), "active_subscriptions": len(active), "trials": trials,
        "conversions": converted, "churned_subscriptions": canceled, "conversion_rate": round(converted/max(1,trials+converted)*100,2),
        "churn_rate": round(canceled/max(1,len(active)+canceled)*100,2), "ltv": None, "cac": None}
