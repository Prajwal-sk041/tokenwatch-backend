from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import get_tenant
from services.tenant import TenantContext
from schemas.requests import ReconciliationRequest
from services.reporting import local_day, report_range, timezone_or_422
from services.insights import build_cost_insights
from services.entitlements import entitlement_service
from services.pricing import pricing_catalog
from utils.database import get_db


router = APIRouter(prefix="/usage", tags=["Usage"])


@router.get("/pricing-catalog")
def get_pricing_catalog(tenant: TenantContext = Depends(get_tenant)):
    return pricing_catalog()


@router.post("/reconcile")
def reconcile(payload: ReconciliationRequest, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Owner or admin role required")
    result = get_db().rpc("reconcile_usage_counters", {
        "p_organization_id": tenant.organization_id, "p_repair": payload.repair,
        "p_actor_user_id": tenant.user_id}).execute().data
    return result


def _filtered_query(tenant: TenantContext, start: datetime | None, end: datetime | None, provider: str | None, model: str | None, columns: str = "*"):
    query = get_db().table("usage_logs").select(columns).eq("organization_id", tenant.organization_id).is_("deleted_at", "null")
    if start: query = query.gte("request_timestamp", start.isoformat())
    if end: query = query.lt("request_timestamp", end.isoformat())
    if provider: query = query.eq("provider", provider)
    if model: query = query.eq("model", model)
    return query


def _all_filtered_logs(tenant: TenantContext, start: datetime | None = None, end: datetime | None = None,
                       provider: str | None = None, model: str | None = None, columns: str = "*",
                       order_by: str | None = None) -> list[dict]:
    rows, offset, page_size = [], 0, 1000
    while True:
        query = _filtered_query(tenant, start, end, provider, model, columns)
        if order_by:
            query = query.order(order_by)
        batch = query.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            return rows
        offset += page_size


@router.post("/log", status_code=410)
def legacy_log_disabled():
    raise HTTPException(status_code=410, detail="Use /v1/ingest/usage with a TokenWatch SDK key")


@router.get("/stats")
def get_stats(tenant: TenantContext = Depends(get_tenant)):
    logs = _all_filtered_logs(tenant, columns="provider,total_tokens,calculated_cost,agent")
    by_provider, by_agent = {}, {}
    for log in logs:
        for bucket, name in ((by_provider, log.get("provider", "unknown")), (by_agent, log.get("agent", "default"))):
            entry = bucket.setdefault(name, {"calls": 0, "tokens": 0, "cost": 0.0})
            entry["calls"] += 1; entry["tokens"] += int(log.get("total_tokens") or 0); entry["cost"] += float(log.get("calculated_cost") or 0)
    return {"total_requests": len(logs), "total_tokens": sum(int(x.get("total_tokens") or 0) for x in logs), "total_cost": round(sum(float(x.get("calculated_cost") or 0) for x in logs), 6), "by_provider": by_provider, "by_agent": by_agent}


@router.get("/history")
def get_history(timezone_name: str = Query(default="UTC", alias="timezone"), tenant: TenantContext = Depends(get_tenant)):
    logs = _all_filtered_logs(tenant, columns="provider,total_tokens,calculated_cost,request_timestamp", order_by="request_timestamp")
    today = datetime.now(timezone.utc).astimezone(timezone_or_422(timezone_name)).date()
    providers = sorted({x["provider"] for x in logs})
    grouped = defaultdict(dict)
    for log in logs:
        day = local_day(str(log["request_timestamp"]), timezone_name); entry = grouped[day].setdefault(log["provider"], {"tokens": 0, "cost": 0.0, "requests": 0})
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
    start: datetime | None = None, end: datetime | None = None, preset: str | None = None,
    timezone_name: str = Query(default="UTC", alias="timezone"), provider: str | None = None, model: str | None = None,
    tenant: TenantContext = Depends(get_tenant),
):
    if preset:
        selected = report_range(timezone_name, preset, start.date() if start else None, end.date() if end else None)
        start, end = selected.start_utc, selected.end_utc
    query = _filtered_query(tenant, start, end, provider, model)
    rows = query.order("request_timestamp", desc=True).range((page - 1) * page_size, page * page_size).execute().data or []
    return {"items": rows[:page_size], "page": page, "page_size": page_size, "has_more": len(rows) > page_size}


@router.get("/aggregate")
def aggregate_usage(
    start: date | None = None, end: date | None = None, preset: str = "30d",
    timezone_name: str = Query(default="UTC", alias="timezone"), provider: str | None = None, model: str | None = None,
    tenant: TenantContext = Depends(get_tenant),
):
    selected = report_range(timezone_name, preset, start, end)
    logs = _all_filtered_logs(tenant, selected.start_utc, selected.end_utc, provider, model)
    dimensions = {name: {} for name in ("provider", "model", "project", "environment")}
    daily: dict[str, dict] = {}
    for log in logs:
        cost = float(log.get("calculated_cost") or 0); tokens = int(log.get("total_tokens") or 0)
        for dimension in dimensions:
            key = log.get(dimension) or "unknown"
            bucket = dimensions[dimension].setdefault(key, {"requests": 0, "tokens": 0, "cost": 0.0})
            bucket["requests"] += 1; bucket["tokens"] += tokens; bucket["cost"] += cost
        day = local_day(str(log["request_timestamp"]), timezone_name)
        bucket = daily.setdefault(day, {"date": day, "requests": 0, "tokens": 0, "cost": 0.0})
        bucket["requests"] += 1; bucket["tokens"] += tokens; bucket["cost"] += cost
    for groups in dimensions.values():
        for value in groups.values(): value["cost"] = round(value["cost"], 8)
    total_cost = sum(float(x.get("calculated_cost") or 0) for x in logs)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_cost = sum(
        float(x.get("calculated_cost") or 0)
        for x in logs
        if datetime.fromisoformat(str(x["request_timestamp"]).replace("Z", "+00:00")) >= month_start
    )
    elapsed = max(1, now.day)
    return {
        "totals": {"requests": len(logs), "tokens": sum(int(x.get("total_tokens") or 0) for x in logs), "cost": round(total_cost, 8)},
        "breakdowns": dimensions, "daily": sorted(daily.values(), key=lambda x: x["date"]),
        "current_month_projection": round(month_cost / elapsed * 30, 8), "timezone": timezone_name,
        "range": {"preset": preset, "start_utc": selected.start_utc.isoformat(), "end_utc_exclusive": selected.end_utc.isoformat()},
    }


@router.get("/insights")
def get_insights(tenant: TenantContext = Depends(get_tenant)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    logs = _all_filtered_logs(tenant, start=month_start, columns="provider,model,total_tokens,calculated_cost,request_timestamp")
    policy_events = get_db().table("audit_logs").select("metadata,created_at").eq(
        "organization_id", tenant.organization_id
    ).eq("action", "policy.request_blocked").gte("created_at", month_start.isoformat()).execute().data or []
    result = build_cost_insights(logs, policy_events, now=now)
    forecast_enabled = entitlement_service.limit(tenant.organization_id, "spend_forecast") is True
    ledger_enabled = entitlement_service.limit(tenant.organization_id, "savings_ledger") is True
    optimization_enabled = entitlement_service.limit(tenant.organization_id, "optimization_recommendations") is True
    if not forecast_enabled:
        result["month"]["projected_cost"] = None
        result["risk"] = {**result["risk"], "level": "normal", "anomaly_ratio": None}
    if not ledger_enabled:
        result["value"]["blocked_requests"] = 0
        result["value"]["estimated_spend_prevented"] = 0
    if not optimization_enabled:
        result["value"]["estimated_optimization_opportunity"] = 0
        result["recommendations"] = []
    result["features"] = {
        "spend_forecast": forecast_enabled,
        "savings_ledger": ledger_enabled,
        "optimization_recommendations": optimization_enabled,
    }
    return result
