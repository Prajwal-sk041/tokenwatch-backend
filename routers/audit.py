from fastapi import APIRouter, Depends

from dependencies import Principal, get_principal
from services.tenant import require_membership
from utils.database import get_db


router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("/{organization_id}")
def list_audit_logs(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    return get_db().table("audit_logs").select("id,actor_user_id,action,target_type,target_id,request_id,metadata,created_at").eq("organization_id", organization_id).order("created_at", desc=True).limit(200).execute().data or []
