from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import Principal, get_principal
from schemas.requests import IngestionKeyCreate
from services.audit import record_audit
from services.security import generate_opaque_token, hash_secret
from services.tenant import require_membership
from services.entitlements import entitlement_service
from utils.database import get_db


router = APIRouter(prefix="/sdk-keys", tags=["TokenWatch SDK Keys"])


@router.post("/{organization_id}", status_code=201)
def create_sdk_key(organization_id: str, payload: IngestionKeyCreate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    entitlement_service.enforce_count(organization_id, "sdk_keys", "api_keys", key_type="ingestion", is_active=True)
    raw = generate_opaque_token("tw_live_")
    key = get_db().table("api_keys").insert({
        "organization_id": organization_id, "created_by": principal.user_id, "key_type": "ingestion",
        "name": payload.name, "key_prefix": raw[:16], "key_hash": hash_secret(raw),
        "permissions": payload.permissions, "expires_at": payload.expires_at.isoformat() if payload.expires_at else None,
    }).execute().data[0]
    record_audit("sdk_key.created", organization_id=organization_id, actor_user_id=principal.user_id, target_type="api_key", target_id=str(key["id"]), metadata={"permissions": payload.permissions})
    return {"id": key["id"], "name": key["name"], "key": raw, "prefix": key["key_prefix"], "permissions": key["permissions"]}


@router.get("/{organization_id}")
def list_sdk_keys(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    return get_db().table("api_keys").select("id,name,key_prefix,permissions,last_used_at,expires_at,revoked_at,is_active,created_at").eq("organization_id", organization_id).eq("key_type", "ingestion").is_("deleted_at", "null").execute().data or []


@router.post("/{organization_id}/{key_id}/rotate", status_code=201)
def rotate_sdk_key(organization_id: str, key_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    rows = get_db().table("api_keys").select("*").eq("id", key_id).eq("organization_id", organization_id).eq("key_type", "ingestion").eq("is_active", True).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="SDK key not found")
    old = rows[0]
    now = datetime.now(timezone.utc).isoformat()
    get_db().table("api_keys").update({"is_active": False, "revoked_at": now}).eq("id", key_id).execute()
    raw = generate_opaque_token("tw_live_")
    new = get_db().table("api_keys").insert({"organization_id": organization_id, "created_by": principal.user_id, "key_type": "ingestion", "name": old["name"], "key_prefix": raw[:16], "key_hash": hash_secret(raw), "permissions": old["permissions"], "expires_at": old.get("expires_at"), "rotated_from_id": key_id}).execute().data[0]
    record_audit("sdk_key.rotated", organization_id=organization_id, actor_user_id=principal.user_id, target_type="api_key", target_id=str(new["id"]), metadata={"rotated_from": key_id})
    return {"id": new["id"], "key": raw, "prefix": new["key_prefix"]}


@router.delete("/{organization_id}/{key_id}", status_code=204)
def revoke_sdk_key(organization_id: str, key_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    now = datetime.now(timezone.utc).isoformat()
    result = get_db().table("api_keys").update({"is_active": False, "revoked_at": now}).eq("id", key_id).eq("organization_id", organization_id).eq("key_type", "ingestion").execute().data or []
    if not result:
        raise HTTPException(status_code=404, detail="SDK key not found")
    record_audit("sdk_key.revoked", organization_id=organization_id, actor_user_id=principal.user_id, target_type="api_key", target_id=key_id)
