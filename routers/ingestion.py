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
    try:
        cost = calculate_cost(payload.provider.value, payload.model, payload.prompt_tokens, payload.completion_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    snapshot = entitlement_service.usage_snapshot(sdk.organization_id)
    limits = snapshot["limits"]
    timestamp = payload.timestamp or datetime.now(timezone.utc)
    if payload.attributed_user_id:
        member = get_db().table("organization_members").select("id").eq("organization_id", sdk.organization_id).eq("user_id", payload.attributed_user_id).eq("status", "active").limit(1).execute().data or []
        if not member:
            raise HTTPException(status_code=422, detail="Attributed user is not an organization member")
    event = {
        "organization_id": sdk.organization_id, "user_id": payload.attributed_user_id, "ingestion_key_id": sdk.key_id,
        "idempotency_key": payload.idempotency_key, "request_timestamp": timestamp.isoformat(),
        "provider": payload.provider.value, "model": payload.model,
        "prompt_tokens": payload.prompt_tokens, "completion_tokens": payload.completion_tokens,
        "total_tokens": payload.prompt_tokens + payload.completion_tokens,
        "calculated_cost": str(cost), "project": payload.project, "agent": payload.agent,
        "environment": payload.environment, "latency_ms": payload.latency_ms,
        "provider_request_id": payload.provider_request_id, "metadata": {},
        "limit_requests": limits.get("monthly_requests", 0), "limit_tokens": limits.get("monthly_tokens", 0),
        "limit_spend": limits.get("monthly_spend", 0),
    }
    try:
        result = get_db().rpc("ingest_usage_atomic", {"p_event": event}).execute().data
    except Exception as exc:
        message = str(exc)
        if "usage_limit_reached:" in message:
            feature = message.split("usage_limit_reached:",1)[1].split()[0].strip("'\"")
            raise HTTPException(status_code=402, detail={"code":"usage_limit_reached","feature":feature}) from None
        raise
    if isinstance(result, list): result = result[0] if result else {}
    return {"usage_id": result["usage_id"], "duplicate": bool(result.get("duplicate")),
        "calculated_cost": str(cost), "currency": "USD"}
