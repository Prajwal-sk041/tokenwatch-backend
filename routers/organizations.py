from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from dependencies import Principal, get_principal, get_tenant
from schemas.requests import OrganizationCreate, OrganizationInvite
from services.audit import record_audit
from services.security import generate_opaque_token, hash_secret
from services.tenant import TenantContext, require_membership
from utils.database import get_db
from utils.email import send_action_email
from config import get_settings
from schemas.requests import TokenActionRequest


router = APIRouter(prefix="/organizations", tags=["Organizations"])


@router.post("", status_code=201)
def create_organization(payload: OrganizationCreate, principal: Principal = Depends(get_principal)):
    if get_db().table("organizations").select("id").eq("slug", payload.slug).is_("deleted_at", "null").execute().data:
        raise HTTPException(status_code=409, detail="Organization slug already exists")
    org = get_db().table("organizations").insert({"name": payload.name, "slug": payload.slug, "owner_user_id": principal.user_id}).execute().data[0]
    get_db().table("organization_members").insert({"organization_id": org["id"], "user_id": principal.user_id, "role": "owner", "status": "active", "joined_at": datetime.now(timezone.utc).isoformat()}).execute()
    record_audit("organization.created", organization_id=str(org["id"]), actor_user_id=principal.user_id, target_type="organization", target_id=str(org["id"]))
    return org


@router.get("")
def list_organizations(principal: Principal = Depends(get_principal)):
    memberships = get_db().table("organization_members").select("organization_id,role").eq("user_id", principal.user_id).eq("status", "active").is_("deleted_at", "null").execute().data or []
    result = []
    for member in memberships:
        rows = get_db().table("organizations").select("id,name,slug,status,created_at").eq("id", member["organization_id"]).is_("deleted_at", "null").limit(1).execute().data or []
        if rows:
            result.append({**rows[0], "role": member["role"]})
    return result


@router.post("/{organization_id}/invites", status_code=201)
def invite_member(organization_id: str, payload: OrganizationInvite, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    token = generate_opaque_token("twi_")
    invite = get_db().table("organization_members").insert({
        "organization_id": organization_id, "invited_email": str(payload.email).lower(), "role": payload.role,
        "status": "invited", "invitation_token_hash": hash_secret(token), "invited_by": principal.user_id,
        "invitation_expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    }).execute().data[0]
    record_audit("organization.invite_created", organization_id=organization_id, actor_user_id=principal.user_id, target_type="organization_member", target_id=str(invite["id"]), metadata={"role": payload.role})
    send_action_email("You were invited to TokenWatch", f"{str(get_settings().app_base_url).rstrip('/')}/accept-invite?token={token}", str(payload.email).lower())
    return {"id": invite["id"], "email": invite["invited_email"], "role": invite["role"], "status": invite["status"]}


@router.post("/invites/accept")
def accept_invite(payload: TokenActionRequest, principal: Principal = Depends(get_principal)):
    now = datetime.now(timezone.utc).isoformat()
    invites = get_db().table("organization_members").select("*").eq("invitation_token_hash", hash_secret(payload.token)).eq("status", "invited").gt("invitation_expires_at", now).limit(1).execute().data or []
    if not invites:
        raise HTTPException(status_code=400, detail="Invalid or expired invitation")
    invite = invites[0]
    users = get_db().table("users").select("email").eq("id", principal.user_id).limit(1).execute().data or []
    if not users or users[0]["email"] != invite["invited_email"]:
        raise HTTPException(status_code=403, detail="Invitation belongs to another email")
    get_db().table("organization_members").update({"user_id": principal.user_id, "status": "active", "joined_at": now, "invitation_token_hash": None}).eq("id", invite["id"]).execute()
    record_audit("organization.invite_accepted", organization_id=str(invite["organization_id"]), actor_user_id=principal.user_id, target_type="organization_member", target_id=str(invite["id"]))
    return {"organization_id": invite["organization_id"], "role": invite["role"]}


@router.get("/{organization_id}/members")
def list_members(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    return get_db().table("organization_members").select("id,user_id,invited_email,role,status,joined_at,created_at").eq("organization_id", organization_id).is_("deleted_at", "null").execute().data or []
