from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query

from dependencies import Principal, require_platform_admin
from utils.database import get_db
from services.billing import billing_service
from services.audit import record_audit


router = APIRouter(prefix="/admin", tags=["Administration"], dependencies=[Depends(require_platform_admin)])


@router.get("/overview")
def overview():
    db = get_db()
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    users = db.table("users").select("id", count="exact").is_("deleted_at", "null").execute().count or 0
    organizations = db.table("organizations").select("id", count="exact").is_("deleted_at", "null").execute().count or 0
    active = db.table("subscriptions").select("id,plans(monthly_price)").in_("status", ["active", "trialing"]).is_("deleted_at", "null").execute().data or []
    paid = [x for x in active if float((x.get("plans") or {}).get("monthly_price") or 0) > 0 and x.get("status") == "active"]
    mrr = sum(float((x.get("plans") or {}).get("monthly_price") or 0) for x in paid)
    trials = db.table("subscriptions").select("id", count="exact").eq("status", "trialing").is_("deleted_at", "null").execute().count or 0
    usage = db.table("usage_logs").select("id,total_tokens", count="exact").gte("created_at", since).execute()
    return {"users": users, "organizations": organizations, "active_subscriptions": len(paid), "trials": trials, "mrr": round(mrr, 2), "arr": round(mrr * 12, 2), "monthly_requests": usage.count or 0, "monthly_tokens": sum(int(x.get("total_tokens") or 0) for x in (usage.data or []))}


@router.post("/billing/catalog", status_code=201)
def provision_billing_catalog(principal: Principal = Depends(require_platform_admin)):
    result = billing_service.provision_catalog()
    record_audit("billing.catalog_provisioned", actor_user_id=principal.user_id, target_type="billing_catalog", metadata={"plans": [x["plan"] for x in result]})
    return result


def _page(table: str, page: int, page_size: int):
    start = (page - 1) * page_size
    result = get_db().table(table).select("*", count="exact").order("created_at", desc=True).range(start, start + page_size - 1).execute()
    return {"items": result.data or [], "total": result.count or 0, "page": page, "page_size": page_size}


@router.get("/{resource}")
def list_resource(resource: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100)):
    allowed = {"users": "users", "organizations": "organizations", "subscriptions": "subscriptions", "usage": "usage_logs", "alerts": "alert_rules", "audit": "audit_logs", "payments": "invoices", "plans": "plans", "feature-flags": "feature_flags", "support": "support_tickets", "email-queue": "email_deliveries", "webhooks": "billing_events"}
    if resource not in allowed:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Admin resource not found")
    return _page(allowed[resource], page, page_size)
