import hashlib
from datetime import date, datetime, timedelta, timezone

from services.alert_delivery import deliver_alert
from utils.database import get_db
from utils.email import retry_failed_email_deliveries


def _period_start(period: str) -> date:
    today = datetime.now(timezone.utc).date()
    return today if period == "daily" else today.replace(day=1)


def evaluate_alerts() -> dict:
    db = get_db(); processed = sent = failed = suppressed = 0
    now = datetime.now(timezone.utc)
    retries = db.table("alert_history").select("*").eq("status", "failed").lte("next_retry_at", now.isoformat()).lt("attempt_count", 3).execute().data or []
    for history in retries:
        rules_for_retry = db.table("alert_rules").select("channel,destination,metric").eq("id", history["rule_id"]).eq("is_active", True).limit(1).execute().data or []
        if not rules_for_retry: continue
        rule = rules_for_retry[0]
        status, error = deliver_alert(rule["channel"], rule.get("destination"), f'TokenWatch {rule["metric"]} threshold reached', history["payload"])
        attempts = int(history.get("attempt_count") or 0) + 1
        db.table("alert_history").update({"status": status, "error_message": error, "attempt_count": attempts,
            "next_retry_at": (now + timedelta(minutes=2 ** attempts)).isoformat() if status == "failed" and attempts < 3 else None,
            "updated_at": now.isoformat()}).eq("id", history["id"]).execute()
    rules = db.table("alert_rules").select("*").eq("is_active", True).is_("deleted_at", "null").execute().data or []
    for rule in rules:
        start = _period_start(rule["period"])
        query = db.table("usage_counters").select("request_count,token_count,cost").eq("organization_id", rule["organization_id"]).is_("user_id", "null").is_("model", "null").eq("period_type", rule["period"]).eq("period_start", start.isoformat())
        query = query.is_("provider", "null") if not rule.get("provider") else query.eq("provider", rule["provider"])
        rows = query.limit(1).execute().data or []
        current = float((rows[0] if rows else {}).get({"cost":"cost","tokens":"token_count","requests":"request_count"}[rule["metric"]]) or 0)
        if current < float(rule["threshold"]): continue
        key = hashlib.sha256(f'{rule["id"]}:{start.isoformat()}:{rule["threshold"]}'.encode()).hexdigest()
        try:
            history = db.table("alert_history").insert({"organization_id": rule["organization_id"], "rule_id": rule["id"],
                "status": "queued", "channel": rule["channel"], "current_value": current, "threshold": rule["threshold"],
                "deduplication_key": key, "payload": {"metric": rule["metric"], "period": rule["period"], "period_start": start.isoformat()}}).execute().data[0]
        except Exception:
            suppressed += 1; continue
        processed += 1
        status, error = deliver_alert(rule["channel"], rule.get("destination"), f'TokenWatch {rule["metric"]} threshold reached', history["payload"] | {"current": current, "threshold": rule["threshold"]})
        update = {"status": status, "error_message": error, "attempt_count": 1,
            "next_retry_at": (now + timedelta(minutes=2)).isoformat() if status == "failed" else None,
            "updated_at": now.isoformat()}
        db.table("alert_history").update(update).eq("id", history["id"]).execute()
        if status in {"sent", "stubbed"}: sent += 1
        else: failed += 1
    return {"rules": len(rules), "processed": processed, "sent": sent, "failed": failed, "suppressed": suppressed,
            "email_retries": retry_failed_email_deliveries()}
