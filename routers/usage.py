from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from routers.auth import get_current_user
from schemas.requests import UsageLog
from utils.database import get_db

router = APIRouter(prefix="/usage", tags=["Usage"])
logger = logging.getLogger(__name__)

@router.post("/log", status_code=201)
async def log_usage(usage: UsageLog, user_id: str = Depends(get_current_user)):
    try:
        now = datetime.now(timezone.utc)
        total = usage.total_tokens or usage.prompt_tokens + usage.completion_tokens
        record = {"id": str(uuid.uuid4()), "user_id": user_id, "provider": usage.provider.value,
                  "model": usage.model, "tokens_used": total, "prompt_tokens": usage.prompt_tokens,
                  "completion_tokens": usage.completion_tokens, "cost": usage.cost,
                  "project": usage.project, "agent": usage.agent, "environment": usage.environment,
                  "latency_ms": usage.latency_ms,
                  "logged_at": usage.timestamp.isoformat() if usage.timestamp else now.isoformat(),
                  "log_date": now.date().isoformat()}
        get_db().table("usage_logs").insert(record).execute()
        return {"message": "Usage logged successfully", "usage_id": record["id"],
                "provider": record["provider"], "model": record["model"], "tokens_used": total,
                "cost": usage.cost, "project": usage.project, "agent": usage.agent,
                "logged_date": record["log_date"]}
    except Exception:
        logger.exception("usage logging failed")
        raise HTTPException(status_code=500, detail="Unable to log usage") from None

@router.get("/stats")
async def get_stats(user_id: str = Depends(get_current_user)):
    try:
        logs = get_db().table("usage_logs").select("*").eq("user_id", user_id).execute().data or []
        by_provider, by_agent = {}, {}
        for log in logs:
            for bucket, name in ((by_provider, log.get("provider", "unknown")), (by_agent, log.get("agent", "default"))):
                entry = bucket.setdefault(name, {"calls": 0, "tokens": 0, "cost": 0.0})
                entry["calls"] += 1
                entry["tokens"] += log.get("tokens_used", 0)
                entry["cost"] += log.get("cost", 0.0)
        for bucket in (by_provider, by_agent):
            for entry in bucket.values():
                entry["cost"] = round(entry["cost"], 6)
        return {"total_requests": len(logs), "total_tokens": sum(x.get("tokens_used", 0) for x in logs),
                "total_cost": round(sum(x.get("cost", 0.0) for x in logs), 6),
                "by_provider": by_provider, "by_agent": by_agent}
    except Exception:
        logger.exception("usage stats failed")
        raise HTTPException(status_code=500, detail="Unable to load usage statistics") from None

@router.get("/history")
async def get_history(user_id: str = Depends(get_current_user)):
    try:
        logs = get_db().table("usage_logs").select("*").eq("user_id", user_id).order("logged_at", desc=False).execute().data or []
        today = datetime.now(timezone.utc).date()
        if not logs:
            return {"chart": [], "providers": [], "provider_summary": {}, "server_today": today.isoformat()}
        providers = sorted({x.get("provider", "unknown") for x in logs})
        grouped = defaultdict(dict)
        for log in logs:
            day = str(log.get("log_date") or log.get("logged_at") or today.isoformat())[:10]
            entry = grouped[day].setdefault(log.get("provider", "unknown"), {"tokens": 0, "cost": 0.0, "requests": 0})
            entry["tokens"] += log.get("tokens_used", 0)
            entry["cost"] += log.get("cost", 0.0)
            entry["requests"] += 1
        current, chart = date.fromisoformat(min(grouped)), []
        while current <= today:
            row = {"date": current.isoformat()}
            for provider in providers:
                entry = grouped.get(current.isoformat(), {}).get(provider, {"tokens": 0, "cost": 0.0, "requests": 0})
                row[f"{provider}_tokens"] = entry["tokens"] or None
                row[f"{provider}_cost"] = round(entry["cost"], 6) or None
                row[f"{provider}_requests"] = entry["requests"] or None
            chart.append(row)
            current += timedelta(days=1)
        summary = {provider: {"total_tokens": sum(row.get(f"{provider}_tokens") or 0 for row in chart),
                              "total_cost": round(sum(row.get(f"{provider}_cost") or 0 for row in chart), 6),
                              "total_requests": sum(row.get(f"{provider}_requests") or 0 for row in chart)} for provider in providers}
        return {"chart": chart, "providers": providers, "provider_summary": summary, "server_today": today.isoformat()}
    except Exception:
        logger.exception("usage history failed")
        raise HTTPException(status_code=500, detail="Unable to load usage history") from None
