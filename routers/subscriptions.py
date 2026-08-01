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


@router.put("/{organization_id}", include_in_schema=False)
def change_subscription_disabled(organization_id: str, payload: SubscriptionChange, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "owner")
    raise HTTPException(status_code=403, detail="Plan changes require the trusted billing service")
