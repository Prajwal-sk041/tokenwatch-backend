from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import get_tenant
from services.tenant import TenantContext
from utils.database import get_db


router = APIRouter(prefix="/usage", tags=["Usage"])


@router.post("/log", status_code=410)
def legacy_log_disabled():
    raise HTTPException(status_code=410, detail="Use /v1/ingest/usage with a TokenWatch SDK key")


@router.get("/stats")
def get_stats(tenant: TenantContext = Depends(get_tenant)):
    logs = get_db().table("usage_logs").select("provider,total_tokens,calculated_cost,agent").eq("organization_id", tenant.organization_id).is_("deleted_at", "null").execute().data or []
    by_provider, by_agent = {}, {}
    for log in logs:
        for bucket, name in ((by_provider, log.get("provider", "unknown")), (by_agent, log.get("agent", "default"))):
            entry = bucket.setdefault(name, {"calls": 0, "tokens": 0, "cost": 0.0})
            entry["calls"] += 1; entry["tokens"] += int(log.get("total_tokens") or 0); entry["cost"] += float(log.get("calculated_cost") or 0)
    return {"total_requests": len(logs), "total_tokens": sum(int(x.get("total_tokens") or 0) for x in logs), "total_cost": round(sum(float(x.get("calculated_cost") or 0) for x in logs), 6), "by_provider": by_provider, "by_agent": by_agent}


@router.get("/history")
def get_history(tenant: TenantContext = Depends(get_tenant)):
    logs = get_db().table("usage_logs").select("provider,total_tokens,calculated_cost,created_at").eq("organization_id", tenant.organization_id).is_("deleted_at", "null").order("created_at").execute().data or []
    today = datetime.now(timezone.utc).date()
    providers = sorted({x["provider"] for x in logs})
    grouped = defaultdict(dict)
    for log in logs:
        day = str(log["created_at"])[:10]; entry = grouped[day].setdefault(log["provider"], {"tokens": 0, "cost": 0.0, "requests": 0})
        entry["tokens"] += int(log["total_tokens"]); entry["cost"] += float(log["calculated_cost"]); entry["requests"] += 1
    if not grouped: return {"chart": [], "providers": [], "provider_summary": {}, "server_today": today.isoformat()}
    current, chart = date.fromisoformat(min(grouped)), []
    while current <= today:
        row = {"date": current.isoformat()}
        for provider in providers:
            entry = grouped.get(current.isoformat(), {}).get(provider, {"tokens": 0, "cost": 0.0, "requests": 0})
            row.update({f"{provider}_tokens": entry["tokens"] or None, f"{provider}_cost": round(entry["cost"], 6) or None, f"{provider}_requests": entry["requests"] or None})
        chart.append(row); current += timedelta(days=1)
    return {"chart": chart, "providers": providers, "server_today": today.isoformat()}
