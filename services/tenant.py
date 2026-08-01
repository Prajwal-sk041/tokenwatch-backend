from dataclasses import dataclass

from fastapi import HTTPException

from utils.database import get_db


ROLE_RANK = {"viewer": 0, "member": 1, "admin": 2, "owner": 3}


@dataclass(frozen=True)
class TenantContext:
    organization_id: str
    user_id: str
    role: str


def require_membership(user_id: str, organization_id: str, minimum_role: str = "viewer") -> TenantContext:
    rows = get_db().table("organization_members").select("role,status").eq(
        "organization_id", organization_id
    ).eq("user_id", user_id).eq("status", "active").is_("deleted_at", "null").limit(1).execute().data or []
    if not rows or ROLE_RANK.get(rows[0]["role"], -1) < ROLE_RANK[minimum_role]:
        raise HTTPException(status_code=403, detail="Organization access denied")
    return TenantContext(organization_id=organization_id, user_id=user_id, role=rows[0]["role"])
