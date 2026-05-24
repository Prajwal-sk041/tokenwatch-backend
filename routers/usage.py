from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, date, timezone
from collections import defaultdict
import uuid
from jose import JWTError
from utils.auth import decode_token
from utils.database import get_db

router = APIRouter(prefix="/usage", tags=["Usage"])
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = decode_token(credentials.credentials)
        if not payload or "sub" not in payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

# ─── SDK Payload Schema ───────────────────────────────────────────────────────
class UsageLog(BaseModel):
    provider:          str
    model:             str
    prompt_tokens:     Optional[int]   = 0
    completion_tokens: Optional[int]   = 0
    total_tokens:      Optional[int]   = 0
    cost:              Optional[float] = 0.0
    project:           Optional[str]   = "default"
    agent:             Optional[str]   = "default"
    environment:       Optional[str]   = "development"
    latency_ms:        Optional[int]   = 0
    timestamp:         Optional[str]   = None
    extra:             Optional[dict]  = {}

@router.post("/log")
async def log_usage(
    usage: UsageLog,
    current_user: dict = Depends(get_current_user)
):
    try:
        db           = get_db()
        now_utc      = datetime.now(timezone.utc)
        log_date_str = now_utc.strftime("%Y-%m-%d")

        # Use SDK-provided timestamp if available, else server time
        logged_at = usage.timestamp or now_utc.isoformat()

        # total_tokens fallback
        total_tokens = usage.total_tokens or (
            (usage.prompt_tokens or 0) + (usage.completion_tokens or 0)
        )

        data = {
            "id":                str(uuid.uuid4()),
            "user_id":           current_user["sub"],
            "provider":          usage.provider.lower().strip(),
            "model":             usage.model,
            "tokens_used":       total_tokens,
            "prompt_tokens":     usage.prompt_tokens     or 0,
            "completion_tokens": usage.completion_tokens or 0,
            "cost":              usage.cost              or 0.0,
            "project":           usage.project           or "default",
            "agent":             usage.agent             or "default",
            "environment":       usage.environment       or "development",
            "latency_ms":        usage.latency_ms        or 0,
            "logged_at":         logged_at,
            "log_date":          log_date_str,
        }

        db.table("usage_logs").insert(data).execute()

        return {
            "message":     "Usage logged successfully! 📊",
            "usage_id":    data["id"],
            "provider":    data["provider"],
            "model":       data["model"],
            "tokens_used": total_tokens,
            "cost":        usage.cost,
            "project":     data["project"],
            "agent":       data["agent"],
            "logged_date": log_date_str,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats(current_user: dict = Depends(get_current_user)):
    try:
        db     = get_db()
        result = db.table("usage_logs").select("*").eq("user_id", current_user["sub"]).execute()
        logs   = result.data or []

        total_requests = len(logs)
        total_tokens   = sum(l.get("tokens_used", 0) for l in logs)
        total_cost     = sum(l.get("cost", 0.0) for l in logs)

        by_provider: dict = {}
        for log in logs:
            p = log.get("provider", "unknown").lower().strip()
            if p not in by_provider:
                by_provider[p] = {"calls": 0, "tokens": 0, "cost": 0.0}
            by_provider[p]["calls"]  += 1
            by_provider[p]["tokens"] += log.get("tokens_used", 0)
            by_provider[p]["cost"]   += log.get("cost", 0.0)
        for p in by_provider:
            by_provider[p]["cost"] = round(by_provider[p]["cost"], 6)

        by_agent: dict = {}
        for log in logs:
            a = log.get("agent", "default")
            if a not in by_agent:
                by_agent[a] = {"calls": 0, "tokens": 0, "cost": 0.0}
            by_agent[a]["calls"]  += 1
            by_agent[a]["tokens"] += log.get("tokens_used", 0)
            by_agent[a]["cost"]   += log.get("cost", 0.0)
        for a in by_agent:
            by_agent[a]["cost"] = round(by_agent[a]["cost"], 6)

        return {
            "total_requests": total_requests,
            "total_tokens":   total_tokens,
            "total_cost":     round(total_cost, 6),
            "by_provider":    by_provider,
            "by_agent":       by_agent,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    try:
        db     = get_db()
        result = db.table("usage_logs") \
            .select("*") \
            .eq("user_id", current_user["sub"]) \
            .order("logged_at", desc=False) \
            .execute()
        logs = result.data or []

        today_utc = datetime.now(timezone.utc).date()
        today_str = today_utc.isoformat()

        if not logs:
            return {"chart": [], "providers": [], "server_today": today_str}

        all_providers: set = set()
        for log in logs:
            all_providers.add(log.get("provider", "unknown").lower().strip())
        sorted_providers = sorted(all_providers)

        def parse_date(log: dict) -> str:
            if log.get("log_date"):
                return str(log["log_date"])[:10]
            logged_at = log.get("logged_at", "")
            return logged_at[:10] if logged_at else today_str

        def default_provider_entry():
            return {p: {"tokens": 0, "cost": 0.0, "requests": 0} for p in sorted_providers}

        date_provider_map: dict = defaultdict(default_provider_entry)
        for log in logs:
            day      = parse_date(log)
            provider = log.get("provider", "unknown").lower().strip()
            date_provider_map[day][provider]["tokens"]   += log.get("tokens_used", 0)
            date_provider_map[day][provider]["cost"]     += log.get("cost", 0.0)
            date_provider_map[day][provider]["requests"] += 1

        existing_dates = sorted(date_provider_map.keys())
        start_date     = date.fromisoformat(existing_dates[0])
        end_date       = today_utc

        all_dates = []
        current   = start_date
        while current <= end_date:
            all_dates.append(current.isoformat())
            current += timedelta(days=1)

        chart_data = []
        for day in all_dates:
            row      = {"date": day}
            day_data = date_provider_map.get(day, {})
            for provider in sorted_providers:
                entry = day_data.get(provider, {"tokens": 0, "cost": 0.0, "requests": 0})
                row[f"{provider}_tokens"]   = entry["tokens"]   if entry["tokens"]   > 0 else None
                row[f"{provider}_cost"]     = round(entry["cost"], 6) if entry["cost"] > 0 else None
                row[f"{provider}_requests"] = entry["requests"] if entry["requests"] > 0 else None
            chart_data.append(row)

        provider_summary: dict = {}
        for provider in sorted_providers:
            provider_summary[provider] = {
                "total_tokens":   sum((r.get(f"{provider}_tokens")   or 0) for r in chart_data),
                "total_cost":     round(sum((r.get(f"{provider}_cost") or 0.0) for r in chart_data), 6),
                "total_requests": sum((r.get(f"{provider}_requests") or 0) for r in chart_data),
            }

        return {
            "chart":            chart_data,
            "providers":        sorted_providers,
            "provider_summary": provider_summary,
            "server_today":     today_str,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
