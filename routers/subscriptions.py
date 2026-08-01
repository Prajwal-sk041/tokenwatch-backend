from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import Principal, get_principal
from schemas.requests import SubscriptionChange
from services.audit import record_audit
from services.tenant import require_membership
from utils.database import get_db


router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/plans")
def list_plans():
    return get_db().table("plans").select("id,code,name,monthly_price,currency,monthly_event_limit,features").eq("is_active", True).order("monthly_price").execute().data or []


@router.get("/{organization_id}")
def get_subscription(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    rows = get_db().table("subscriptions").select("*,plans(code,name,monthly_event_limit,features)").eq("organization_id", organization_id).is_("deleted_at", "null").limit(1).execute().data or []
    return rows[0] if rows else None


@router.put("/{organization_id}")
def change_subscription(organization_id: str, payload: SubscriptionChange, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "owner")
    plans = get_db().table("plans").select("id,code").eq("code", payload.plan_code).eq("is_active", True).limit(1).execute().data or []
    if not plans:
        raise HTTPException(status_code=404, detail="Plan not found")
    now = datetime.now(timezone.utc).isoformat()
    existing = get_db().table("subscriptions").select("id").eq("organization_id", organization_id).is_("deleted_at", "null").limit(1).execute().data or []
    if existing:
        row = get_db().table("subscriptions").update({"plan_id": plans[0]["id"], "status": "active"}).eq("id", existing[0]["id"]).execute().data[0]
    else:
        row = get_db().table("subscriptions").insert({"organization_id": organization_id, "plan_id": plans[0]["id"], "provider": "manual", "status": "active", "current_period_start": now}).execute().data[0]
    get_db().table("organizations").update({"plan_id": plans[0]["id"]}).eq("id", organization_id).execute()
    record_audit("subscription.changed", organization_id=organization_id, actor_user_id=principal.user_id, target_type="subscription", target_id=str(row["id"]), metadata={"plan_code": payload.plan_code})
    return row
