from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date, timezone
import os

from supabase import create_client, Client
from routers.auth import get_current_user

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# ── Supabase client ───────────────────────────────────────
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    return create_client(url, key)

# ── Helper: extract user_id regardless of return type ─────
def extract_user_id(current_user) -> str:
    if isinstance(current_user, dict):
        return str(current_user.get("id") or current_user.get("sub") or current_user.get("user_id"))
    return str(current_user)

# ── Schemas ───────────────────────────────────────────────
class AlertCreate(BaseModel):
    alert_type:   str
    threshold:    float
    provider:     Optional[str] = "all"
    period:       Optional[str] = "daily"
    notify_email: Optional[str] = None

# ── Helper: compute current usage ─────────────────────────
def get_current_usage(supabase: Client, user_id: str, provider: str,
                      alert_type: str, period: str) -> float:

    # ✅ Always use UTC to match Supabase stored timestamps
    now_utc     = datetime.now(timezone.utc)
    today       = now_utc.date().isoformat()                    # 2026-05-17 (UTC)
    month_start = now_utc.date().replace(day=1).isoformat()     # 2026-05-01 (UTC)

    q = (
        supabase.table("usage_logs")
        .select("tokens_used, prompt_tokens, completion_tokens, cost, id")
        .eq("user_id", user_id)
    )

    if provider and provider != "all":
        q = q.eq("provider", provider)

    # ✅ Use UTC-aware timestamps
    if period == "daily":
        q = q.gte("logged_at", f"{today}T00:00:00+00:00")
    else:
        q = q.gte("logged_at", f"{month_start}T00:00:00+00:00")

    rows = q.execute().data or []

    print(f"[ALERTS] Found {len(rows)} rows | user={user_id} | provider={provider} | period={period} | UTC date={today}")

    if alert_type == "cost":
        return sum(float(r.get("cost") or 0) for r in rows)

    elif alert_type == "tokens":
        total = 0
        for r in rows:
            if r.get("tokens_used") is not None:
                total += int(r.get("tokens_used") or 0)
            else:
                total += int(r.get("prompt_tokens") or 0) + int(r.get("completion_tokens") or 0)
        return float(total)

    else:  # requests
        return float(len(rows))


# ── Routes ────────────────────────────────────────────────

@router.get("/list")
def list_alerts(current_user=Depends(get_current_user)):
    supabase = get_supabase()
    user_id  = extract_user_id(current_user)
    res = supabase.table("alert_rules") \
                  .select("*") \
                  .eq("user_id", user_id) \
                  .order("created_at", desc=True) \
                  .execute()
    return res.data or []

@router.post("/create")
def create_alert(payload: AlertCreate, current_user=Depends(get_current_user)):
    supabase = get_supabase()
    user_id  = extract_user_id(current_user)

    valid_types = ["cost", "tokens", "requests"]
    if payload.alert_type not in valid_types:
        raise HTTPException(400, f"alert_type must be one of {valid_types}")

    data = {
        "user_id":      user_id,
        "alert_type":   payload.alert_type,
        "threshold":    payload.threshold,
        "provider":     payload.provider or "all",
        "period":       payload.period   or "daily",
        "notify_email": payload.notify_email,
        "is_active":    True,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }
    res = supabase.table("alert_rules").insert(data).execute()
    if not res.data:
        raise HTTPException(500, "Failed to create alert")
    return res.data[0]

@router.patch("/toggle/{alert_id}")
def toggle_alert(alert_id: str, current_user=Depends(get_current_user)):
    supabase = get_supabase()
    user_id  = extract_user_id(current_user)

    existing = supabase.table("alert_rules") \
                       .select("is_active") \
                       .eq("id", alert_id) \
                       .eq("user_id", user_id) \
                       .single() \
                       .execute()
    if not existing.data:
        raise HTTPException(404, "Alert not found")

    new_state = not existing.data["is_active"]
    supabase.table("alert_rules") \
            .update({"is_active": new_state}) \
            .eq("id", alert_id) \
            .eq("user_id", user_id) \
            .execute()
    return {"id": alert_id, "is_active": new_state}

@router.delete("/delete/{alert_id}")
def delete_alert(alert_id: str, current_user=Depends(get_current_user)):
    supabase = get_supabase()
    user_id  = extract_user_id(current_user)
    supabase.table("alert_rules") \
            .delete() \
            .eq("id", alert_id) \
            .eq("user_id", user_id) \
            .execute()
    return {"message": "Alert deleted"}

@router.get("/history")
def get_history(current_user=Depends(get_current_user)):
    supabase = get_supabase()
    user_id  = extract_user_id(current_user)
    res = supabase.table("alert_history") \
                  .select("*") \
                  .eq("user_id", user_id) \
                  .order("triggered_at", desc=True) \
                  .limit(50) \
                  .execute()
    return res.data or []

# ── Scheduler checker ─────────────────────────────────────
def check_alerts_for_all_users():
    from utils.email import send_alert_email, build_alert_email

    supabase = get_supabase()
    today    = date.today().isoformat()

    rules = supabase.table("alert_rules") \
                    .select("*") \
                    .eq("is_active", True) \
                    .execute().data or []

    print(f"[ALERTS] 🔍 Checking {len(rules)} active rule(s)...")

    for rule in rules:
        user_id    = str(rule["user_id"])
        alert_type = rule["alert_type"]
        threshold  = float(rule["threshold"])
        provider   = rule.get("provider", "all")
        period     = rule.get("period",   "daily")

        current_val = get_current_usage(supabase, user_id, provider, alert_type, period)
        print(f"[ALERTS] 📊 {provider} | {alert_type} | {period} → {current_val} / {threshold}")

        if current_val < threshold * 0.8:
            print(f"[ALERTS] ⏭ Below 80% threshold — skipping")
            continue

        # Avoid duplicate alerts same day
        dup = supabase.table("alert_history") \
                      .select("id") \
                      .eq("rule_id", rule["id"]) \
                      .gte("triggered_at", f"{today}T00:00:00") \
                      .execute()
        if dup.data:
            print(f"[ALERTS] ⏭ Already alerted today — skipping")
            continue

        unit         = "$" if alert_type == "cost" else ""
        period_label = f"Today ({today})" if period == "daily" \
                       else f"This Month ({date.today().strftime('%B %Y')})"

        subject, body = build_alert_email(
            alert_type  = f"{period.title()} {alert_type.title()}",
            provider    = provider,
            current_val = current_val,
            limit_val   = threshold,
            unit        = unit,
            period      = period_label,
        )

        receiver   = rule.get("notify_email") or os.getenv("ALERT_RECEIVER")
        email_sent = send_alert_email(subject, body, receiver)

        supabase.table("alert_history").insert({
            "rule_id":      rule["id"],
            "user_id":      user_id,
            "provider":     provider,
            "alert_type":   alert_type,
            "current_val":  current_val,
            "threshold":    threshold,
            "email_sent":   email_sent,
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        print(f"[ALERTS] ✅ Email sent → {provider} {alert_type}: {current_val} / {threshold}")