from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_tenant
from schemas.requests import AlertCreate, AlertUpdate
from services.audit import record_audit
from services.tenant import TenantContext
from services.entitlements import entitlement_service
from utils.database import get_db


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/list")
def list_alerts(tenant: TenantContext = Depends(get_tenant)):
    return get_db().table("alert_rules").select("*").eq("organization_id", tenant.organization_id).is_("deleted_at", "null").order("created_at", desc=True).execute().data or []


@router.post("/create", status_code=201)
def create_alert(payload: AlertCreate, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role == "viewer": raise HTTPException(status_code=403, detail="Viewer cannot create alerts")
    entitlement_service.enforce_count(tenant.organization_id, "alerts", "alert_rules", is_active=True)
    destination = payload.destination or (str(payload.notify_email) if payload.notify_email else None)
    if payload.channel == "email" and not destination:
        users = get_db().table("users").select("email").eq("id", tenant.user_id).limit(1).execute().data or []
        destination = users[0]["email"] if users else None
    row = get_db().table("alert_rules").insert({"organization_id": tenant.organization_id, "created_by": tenant.user_id, "name": f"{payload.period.value} {payload.alert_type.value} alert", "metric": payload.alert_type.value, "threshold": payload.threshold, "provider": None if payload.provider.value == "all" else payload.provider.value, "period": payload.period.value, "channel": payload.channel, "destination": destination}).execute().data[0]
    record_audit("alert.created", organization_id=tenant.organization_id, actor_user_id=tenant.user_id, target_type="alert_rule", target_id=str(row["id"]))
    return row


@router.patch("/toggle/{alert_id}")
def toggle_alert(alert_id: str, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role == "viewer": raise HTTPException(status_code=403, detail="Viewer cannot change alerts")
    rows = get_db().table("alert_rules").select("is_active").eq("id", alert_id).eq("organization_id", tenant.organization_id).limit(1).execute().data or []
    if not rows: raise HTTPException(status_code=404, detail="Alert not found")
    state = not rows[0]["is_active"]
    get_db().table("alert_rules").update({"is_active": state}).eq("id", alert_id).eq("organization_id", tenant.organization_id).execute()
    return {"id": alert_id, "is_active": state}


@router.delete("/delete/{alert_id}")
def delete_alert(alert_id: str, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role == "viewer": raise HTTPException(status_code=403, detail="Viewer cannot delete alerts")
    now = datetime.now(timezone.utc).isoformat()
    get_db().table("alert_rules").update({"is_active": False, "deleted_at": now}).eq("id", alert_id).eq("organization_id", tenant.organization_id).execute()
    return {"message": "Alert deleted"}


@router.patch("/{alert_id}")
def update_alert(alert_id: str, payload: AlertUpdate, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role == "viewer": raise HTTPException(status_code=403, detail="Viewer cannot change alerts")
    values = payload.model_dump(exclude_none=True)
    if values.get("destination") and not values["destination"].startswith("https://"):
        rows = get_db().table("alert_rules").select("channel").eq("id", alert_id).eq("organization_id", tenant.organization_id).limit(1).execute().data or []
        if rows and rows[0]["channel"] == "webhook": raise HTTPException(status_code=422, detail="Webhook destination must use HTTPS")
    rows = get_db().table("alert_rules").update(values).eq("id", alert_id).eq("organization_id", tenant.organization_id).is_("deleted_at", "null").execute().data or []
    if not rows: raise HTTPException(status_code=404, detail="Alert not found")
    record_audit("alert.updated", organization_id=tenant.organization_id, actor_user_id=tenant.user_id, target_type="alert_rule", target_id=alert_id)
    return rows[0]


@router.get("/history")
def history(tenant: TenantContext = Depends(get_tenant)):
    return get_db().table("alert_history").select("*").eq("organization_id", tenant.organization_id).order("triggered_at", desc=True).limit(50).execute().data or []


def check_alerts_for_all_users():
    # Email and webhook delivery are active channels; Slack and Teams are recorded as stubs.
    return None
