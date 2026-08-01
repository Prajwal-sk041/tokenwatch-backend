from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException

from dependencies import Principal, get_principal, get_tenant
from schemas.requests import AddKeyRequest
from services.audit import record_audit
from services.tenant import TenantContext
from services.entitlements import entitlement_service
from utils.database import get_db
from utils.encryption import decrypt_api_key, encrypt_api_key, mask_api_key


router = APIRouter(prefix="/keys", tags=["Provider Keys"])
logger = logging.getLogger(__name__)


@router.post("/add", status_code=201)
def add_key(data: AddKeyRequest, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=403, detail="Insufficient organization role")
    entitlement_service.enforce_count(tenant.organization_id, "provider_keys", "api_keys", key_type="provider", is_active=True)
    row = get_db().table("api_keys").insert({
        "organization_id": tenant.organization_id, "created_by": tenant.user_id, "key_type": "provider",
        "name": data.name, "provider": data.provider.value, "encrypted_key": encrypt_api_key(data.key_value),
    }).execute().data[0]
    record_audit("provider_key.created", organization_id=tenant.organization_id, actor_user_id=tenant.user_id, target_type="api_key", target_id=str(row["id"]), metadata={"provider": data.provider.value})
    return {"message": "Provider key added", "key_id": row["id"], "name": data.name, "provider": data.provider.value, "masked_key": mask_api_key(data.key_value)}


@router.get("/list")
def list_keys(tenant: TenantContext = Depends(get_tenant)):
    rows = get_db().table("api_keys").select("id,name,provider,encrypted_key,is_active,created_at").eq("organization_id", tenant.organization_id).eq("key_type", "provider").is_("deleted_at", "null").order("created_at", desc=True).execute().data or []
    return [{"id": row["id"], "name": row["name"], "provider": row["provider"], "masked_key": mask_api_key(decrypt_api_key(row["encrypted_key"])), "is_active": row["is_active"], "created_at": row["created_at"]} for row in rows]


@router.delete("/delete/{key_id}")
def delete_key(key_id: str, tenant: TenantContext = Depends(get_tenant)):
    if tenant.role not in {"owner", "admin", "member"}:
        raise HTTPException(status_code=403, detail="Insufficient organization role")
    now = datetime.now(timezone.utc).isoformat()
    rows = get_db().table("api_keys").update({"is_active": False, "revoked_at": now, "deleted_at": now}).eq("id", key_id).eq("organization_id", tenant.organization_id).eq("key_type", "provider").execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Provider key not found")
    record_audit("provider_key.deleted", organization_id=tenant.organization_id, actor_user_id=tenant.user_id, target_type="api_key", target_id=key_id)
    return {"message": "Provider key deleted", "key_id": key_id}
