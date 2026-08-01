from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import SdkPrincipal, get_sdk_principal, require_sdk_permission
from schemas.requests import UsageLog
from services.pricing import calculate_cost
from services.entitlements import entitlement_service
from utils.database import get_db


router = APIRouter(prefix="/v1/ingest", tags=["Usage Ingestion"])


@router.post("/usage", status_code=201)
def ingest_usage(payload: UsageLog, sdk: SdkPrincipal = Depends(get_sdk_principal)):
    require_sdk_permission(sdk, "usage:write")
    duplicate = get_db().table("usage_logs").select("id").eq("organization_id", sdk.organization_id).eq("idempotency_key", payload.idempotency_key).limit(1).execute().data or []
    if duplicate:
        return {"usage_id": duplicate[0]["id"], "duplicate": True}
    try:
        cost = calculate_cost(payload.provider.value, payload.model, payload.prompt_tokens, payload.completion_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    snapshot = entitlement_service.usage_snapshot(sdk.organization_id)
    limits, usage = snapshot["limits"], snapshot["usage"]
    requested_tokens = payload.prompt_tokens + payload.completion_tokens
    for feature, current, added in (
        ("monthly_requests", int(usage.get("request_count") or 0), 1),
        ("monthly_tokens", int(usage.get("token_count") or 0), requested_tokens),
        ("monthly_spend", float(usage.get("cost") or 0), float(cost)),
    ):
        limit = limits.get(feature, 0)
        if limit != -1 and current + added > limit:
            raise HTTPException(status_code=402, detail={"code": "usage_limit_reached", "feature": feature, "limit": limit})
    timestamp = payload.timestamp or datetime.now(timezone.utc)
    if payload.attributed_user_id:
        member = get_db().table("organization_members").select("id").eq("organization_id", sdk.organization_id).eq("user_id", payload.attributed_user_id).eq("status", "active").limit(1).execute().data or []
        if not member:
            raise HTTPException(status_code=422, detail="Attributed user is not an organization member")
    record = {
        "organization_id": sdk.organization_id, "user_id": payload.attributed_user_id, "ingestion_key_id": sdk.key_id,
        "idempotency_key": payload.idempotency_key, "request_timestamp": timestamp.isoformat(),
        "provider": payload.provider.value, "model": payload.model,
        "prompt_tokens": payload.prompt_tokens, "completion_tokens": payload.completion_tokens,
        "total_tokens": payload.prompt_tokens + payload.completion_tokens,
        "calculated_cost": str(cost), "project": payload.project, "agent": payload.agent,
        "environment": payload.environment, "latency_ms": payload.latency_ms,
        "provider_request_id": payload.provider_request_id,
    }
    try:
        row = get_db().table("usage_logs").insert(record).execute().data[0]
    except Exception:
        duplicate = get_db().table("usage_logs").select("id").eq("organization_id", sdk.organization_id).eq("idempotency_key", payload.idempotency_key).limit(1).execute().data or []
        if duplicate:
            return {"usage_id": duplicate[0]["id"], "duplicate": True}
        raise
    get_db().rpc("increment_usage_counters", {
        "p_organization_id": sdk.organization_id, "p_user_id": payload.attributed_user_id,
        "p_provider": payload.provider.value, "p_model": payload.model, "p_requests": 1,
        "p_tokens": payload.prompt_tokens + payload.completion_tokens, "p_cost": str(cost),
    }).execute()
    return {"usage_id": row["id"], "duplicate": False, "calculated_cost": str(cost), "currency": "USD"}
