from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import get_tenant
from services.tenant import TenantContext
from utils.database import get_db


router = APIRouter(prefix="/usage", tags=["Usage"])


def _filtered_query(tenant: TenantContext, start: datetime | None, end: datetime | None, provider: str | None, model: str | None):
    query = get_db().table("usage_logs").select("*").eq("organization_id", tenant.organization_id).is_("deleted_at", "null")
    if start: query = query.gte("created_at", start.isoformat())
    if end: query = query.lte("created_at", end.isoformat())
    if provider: query = query.eq("provider", provider)
    if model: query = query.eq("model", model)
    return query


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


@router.get("/events")
def list_events(
    page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=100),
    start: datetime | None = None, end: datetime | None = None, provider: str | None = None, model: str | None = None,
    tenant: TenantContext = Depends(get_tenant),
):
    query = _filtered_query(tenant, start, end, provider, model)
    rows = query.order("created_at", desc=True).range((page - 1) * page_size, page * page_size).execute().data or []
    return {"items": rows[:page_size], "page": page, "page_size": page_size, "has_more": len(rows) > page_size}


@router.get("/aggregate")
def aggregate_usage(
    start: datetime | None = None, end: datetime | None = None, provider: str | None = None, model: str | None = None,
    tenant: TenantContext = Depends(get_tenant),
):
    logs = _filtered_query(tenant, start, end, provider, model).execute().data or []
    dimensions = {name: {} for name in ("provider", "model", "project", "environment")}
    daily: dict[str, dict] = {}
    for log in logs:
        cost = float(log.get("calculated_cost") or 0); tokens = int(log.get("total_tokens") or 0)
        for dimension in dimensions:
            key = log.get(dimension) or "unknown"
            bucket = dimensions[dimension].setdefault(key, {"requests": 0, "tokens": 0, "cost": 0.0})
            bucket["requests"] += 1; bucket["tokens"] += tokens; bucket["cost"] += cost
        day = str(log["created_at"])[:10]
        bucket = daily.setdefault(day, {"date": day, "requests": 0, "tokens": 0, "cost": 0.0})
        bucket["requests"] += 1; bucket["tokens"] += tokens; bucket["cost"] += cost
    for groups in dimensions.values():
        for value in groups.values(): value["cost"] = round(value["cost"], 8)
    total_cost = sum(float(x.get("calculated_cost") or 0) for x in logs)
    days = max(1, len(daily)); elapsed = max(1, datetime.now(timezone.utc).day)
    return {
        "totals": {"requests": len(logs), "tokens": sum(int(x.get("total_tokens") or 0) for x in logs), "cost": round(total_cost, 8)},
        "breakdowns": dimensions, "daily": sorted(daily.values(), key=lambda x: x["date"]),
        "current_month_projection": round(total_cost / elapsed * 30, 8), "timezone": "UTC",
    }
