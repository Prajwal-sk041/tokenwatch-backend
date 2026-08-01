from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException
from routers.auth import get_current_user
from schemas.requests import AlertCreate
from utils.database import get_db

router = APIRouter(prefix="/alerts", tags=["Alerts"])
logger = logging.getLogger(__name__)

def get_current_usage(db, user_id: str, provider: str, alert_type: str, period: str) -> float:
    now = datetime.now(timezone.utc)
    start = now.date() if period == "daily" else now.date().replace(day=1)
    query = db.table("usage_logs").select("tokens_used,cost,id").eq("user_id", user_id).gte(
        "logged_at", f"{start.isoformat()}T00:00:00+00:00")
    if provider != "all":
        query = query.eq("provider", provider)
    rows = query.execute().data or []
    if alert_type == "cost":
        return sum(float(row.get("cost") or 0) for row in rows)
    if alert_type == "tokens":
        return float(sum(int(row.get("tokens_used") or 0) for row in rows))
    return float(len(rows))

@router.get("/list")
def list_alerts(user_id: str = Depends(get_current_user)):
    try:
        return get_db().table("alert_rules").select("*").eq("user_id", user_id).order("created_at", desc=True).execute().data or []
    except Exception:
        logger.exception("alert listing failed")
        raise HTTPException(status_code=500, detail="Unable to load alerts") from None

@router.post("/create", status_code=201)
def create_alert(payload: AlertCreate, user_id: str = Depends(get_current_user)):
    try:
        record = {"user_id": user_id, "alert_type": payload.alert_type.value,
                  "threshold": payload.threshold, "provider": payload.provider.value,
                  "period": payload.period.value,
                  "notify_email": str(payload.notify_email) if payload.notify_email else None,
                  "is_active": True, "created_at": datetime.now(timezone.utc).isoformat()}
        result = get_db().table("alert_rules").insert(record).execute()
        if not result.data:
            raise RuntimeError("insert returned no data")
        return result.data[0]
    except Exception:
        logger.exception("alert creation failed")
        raise HTTPException(status_code=500, detail="Unable to create alert") from None

@router.patch("/toggle/{alert_id}")
def toggle_alert(alert_id: str, user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        existing = db.table("alert_rules").select("is_active").eq("id", alert_id).eq("user_id", user_id).single().execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Alert not found")
        new_state = not existing.data["is_active"]
        db.table("alert_rules").update({"is_active": new_state}).eq("id", alert_id).eq("user_id", user_id).execute()
        return {"id": alert_id, "is_active": new_state}
    except HTTPException:
        raise
    except Exception:
        logger.exception("alert toggle failed")
        raise HTTPException(status_code=500, detail="Unable to update alert") from None

@router.delete("/delete/{alert_id}")
def delete_alert(alert_id: str, user_id: str = Depends(get_current_user)):
    try:
        get_db().table("alert_rules").delete().eq("id", alert_id).eq("user_id", user_id).execute()
        return {"message": "Alert deleted"}
    except Exception:
        logger.exception("alert deletion failed")
        raise HTTPException(status_code=500, detail="Unable to delete alert") from None

@router.get("/history")
def get_history(user_id: str = Depends(get_current_user)):
    try:
        return get_db().table("alert_history").select("*").eq("user_id", user_id).order("triggered_at", desc=True).limit(50).execute().data or []
    except Exception:
        logger.exception("alert history failed")
        raise HTTPException(status_code=500, detail="Unable to load alert history") from None

def check_alerts_for_all_users():
    from utils.email import build_alert_email, send_alert_email
    db = get_db()
    today = datetime.now(timezone.utc).date().isoformat()
    rules = db.table("alert_rules").select("*").eq("is_active", True).execute().data or []
    for rule in rules:
        current = get_current_usage(db, str(rule["user_id"]), rule.get("provider", "all"), rule["alert_type"], rule["period"])
        threshold = float(rule["threshold"])
        if current < threshold * 0.8:
            continue
        duplicate = db.table("alert_history").select("id").eq("rule_id", rule["id"]).gte("triggered_at", f"{today}T00:00:00+00:00").execute()
        if duplicate.data:
            continue
        subject, body = build_alert_email(rule["alert_type"], rule.get("provider", "all"), current, threshold,
                                          "$" if rule["alert_type"] == "cost" else "", rule["period"])
        sent = send_alert_email(subject, body, rule.get("notify_email"))
        db.table("alert_history").insert({"rule_id": rule["id"], "user_id": str(rule["user_id"]),
            "provider": rule.get("provider", "all"), "alert_type": rule["alert_type"],
            "current_val": current, "threshold": threshold, "email_sent": sent,
            "triggered_at": datetime.now(timezone.utc).isoformat()}).execute()
