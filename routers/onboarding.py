from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, HTTPException

from dependencies import Principal, get_principal
from schemas.requests import OnboardingTestEvent, OnboardingUpdate
from services.audit import record_audit
from services.pricing import calculate_cost
from services.security import hash_secret
from services.tenant import require_membership
from utils.database import get_db


router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/{organization_id}")
def get_progress(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    rows = get_db().table("onboarding_progress").select("*").eq("organization_id", organization_id).limit(1).execute().data or []
    if rows:
        return rows[0]
    return get_db().table("onboarding_progress").insert({"organization_id": organization_id}).execute().data[0]


@router.put("/{organization_id}")
def update_progress(organization_id: str, payload: OnboardingUpdate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "member")
    now = datetime.now(timezone.utc).isoformat()
    values = payload.model_dump(exclude={"completed", "skipped"}, mode="json")
    if payload.completed:
        values["completed_at"] = now
        values["current_step"] = 11
    if payload.skipped:
        values["skipped_at"] = now
    existing = get_db().table("onboarding_progress").select("id").eq("organization_id", organization_id).limit(1).execute().data or []
    row = (get_db().table("onboarding_progress").update(values).eq("organization_id", organization_id) if existing else get_db().table("onboarding_progress").insert({"organization_id": organization_id, **values})).execute().data[0]
    if payload.completed:
        record_audit("onboarding.completed", organization_id=organization_id, actor_user_id=principal.user_id)
    return row


@router.post("/{organization_id}/test-event", status_code=201)
def create_test_event(organization_id: str, payload: OnboardingTestEvent, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "member")
    keys = get_db().table("api_keys").select("id,permissions").eq("organization_id", organization_id).eq("key_hash", hash_secret(payload.sdk_key)).eq("key_type", "ingestion").eq("is_active", True).is_("revoked_at", "null").limit(1).execute().data or []
    if not keys or "usage:write" not in (keys[0].get("permissions") or []):
        raise HTTPException(status_code=401, detail="Invalid SDK key")
    now = datetime.now(timezone.utc).isoformat()
    prompt_tokens, completion_tokens = 12, 8
    row = get_db().table("usage_logs").insert({
        "organization_id": organization_id, "user_id": principal.user_id, "ingestion_key_id": keys[0]["id"],
        "idempotency_key": f"onboarding:{uuid.uuid4()}", "request_timestamp": now,
        "provider": payload.provider.value, "model": payload.model,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": 20,
        "calculated_cost": str(calculate_cost(payload.provider.value, payload.model, prompt_tokens, completion_tokens)),
        "project": "tokenwatch-onboarding", "agent": "setup-wizard", "environment": "test",
        "metadata": {"onboarding_test": True},
    }).execute().data[0]
    get_db().table("api_keys").update({"last_used_at": now}).eq("id", keys[0]["id"]).execute()
    progress = get_progress(organization_id, principal)
    get_db().table("onboarding_progress").update({"test_usage_log_id": row["id"]}).eq("id", progress["id"]).execute()
    record_audit("onboarding.test_event", organization_id=organization_id, actor_user_id=principal.user_id, target_type="usage_log", target_id=str(row["id"]))
    return {"received": True, "usage_log_id": row["id"], "created_at": row["created_at"]}


@router.get("/{organization_id}/test-event")
def verify_test_event(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    progress = get_progress(organization_id, principal)
    event_id = progress.get("test_usage_log_id")
    if not event_id:
        return {"received": False}
    rows = get_db().table("usage_logs").select("id,provider,model,created_at").eq("id", event_id).eq("organization_id", organization_id).limit(1).execute().data or []
    return {"received": bool(rows), "event": rows[0] if rows else None}
