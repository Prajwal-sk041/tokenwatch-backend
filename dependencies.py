from dataclasses import dataclass

from fastapi import Cookie, Depends, Header, HTTPException
from datetime import datetime, timezone
from jwt import InvalidTokenError

from services.security import decode_access_token, hash_secret
from services.tenant import TenantContext, require_membership
from utils.database import get_db
from config import get_settings


@dataclass(frozen=True)
class Principal:
    user_id: str
    session_id: str
    organization_id: str | None


def get_principal(
    authorization: str | None = Header(default=None),
    tw_access: str | None = Cookie(default=None),
) -> Principal:
    token = tw_access
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_access_token(token)
        user_rows = get_db().table("users").select("id,is_active,token_version").eq("id", payload["sub"]).is_("deleted_at", "null").limit(1).execute().data or []
        session_rows = get_db().table("auth_sessions").select("id").eq("id", payload["sid"]).is_("revoked_at", "null").gt("expires_at", datetime.now(timezone.utc).isoformat()).limit(1).execute().data or []
        if not user_rows or not user_rows[0]["is_active"] or not session_rows or int(payload.get("ver", 0)) != int(user_rows[0]["token_version"]):
            raise ValueError("Revoked session")
        return Principal(str(payload["sub"]), str(payload["sid"]), payload.get("org"))
    except (InvalidTokenError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or revoked session") from None


def get_optional_principal(
    authorization: str | None = Header(default=None),
    tw_access: str | None = Cookie(default=None),
) -> Principal | None:
    """Return a valid session when present while allowing public requests."""
    if not tw_access and not (authorization and authorization.lower().startswith("bearer ")):
        return None
    try:
        return get_principal(authorization=authorization, tw_access=tw_access)
    except HTTPException:
        return None


def get_tenant(principal: Principal = Depends(get_principal)) -> TenantContext:
    if not principal.organization_id:
        raise HTTPException(status_code=400, detail="No active organization")
    return require_membership(principal.user_id, principal.organization_id)


def require_platform_admin(principal: Principal = Depends(get_principal)) -> Principal:
    rows = get_db().table("users").select("email,is_platform_admin").eq("id", principal.user_id).limit(1).execute().data or []
    if not rows or not (rows[0].get("is_platform_admin") or rows[0].get("email", "").lower() in get_settings().admin_emails):
        raise HTTPException(status_code=403, detail="Platform administrator access required")
    return principal


@dataclass(frozen=True)
class SdkPrincipal:
    key_id: str
    organization_id: str
    permissions: tuple[str, ...]


def get_sdk_principal(x_tokenwatch_key: str = Header(alias="X-TokenWatch-Key")) -> SdkPrincipal:
    if not x_tokenwatch_key.startswith("tw_live_"):
        raise HTTPException(status_code=401, detail="Invalid SDK key")
    rows = get_db().table("api_keys").select("id,organization_id,permissions,is_active,expires_at,revoked_at").eq(
        "key_hash", hash_secret(x_tokenwatch_key)
    ).eq("key_type", "ingestion").eq("is_active", True).is_("revoked_at", "null").is_("deleted_at", "null").limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid or revoked SDK key")
    row = rows[0]
    if row.get("expires_at") and row["expires_at"] <= datetime.now(timezone.utc).isoformat():
        raise HTTPException(status_code=401, detail="Expired SDK key")
    get_db().table("api_keys").update({"last_used_at": datetime.now(timezone.utc).isoformat()}).eq("id", row["id"]).execute()
    return SdkPrincipal(str(row["id"]), str(row["organization_id"]), tuple(row.get("permissions") or []))


def require_sdk_permission(principal: SdkPrincipal, permission: str) -> None:
    if permission not in principal.permissions:
        raise HTTPException(status_code=403, detail=f"SDK key lacks {permission} permission")
