from datetime import datetime, timedelta, timezone
import logging
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

from config import get_settings
from dependencies import Principal, get_principal
from schemas.requests import LoginRequest, PasswordResetConfirm, PasswordResetRequest, RegisterRequest, TokenActionRequest
from services.audit import record_audit
from services.security import create_access_token, generate_opaque_token, hash_secret
from services.rate_limit import consume
from utils.auth import hash_password, verify_password
from utils.database import get_db
from utils.email import send_action_email, send_template_email


router = APIRouter(prefix="/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)


def _set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    settings = get_settings()
    common = {"httponly": True, "secure": settings.auth_cookie_secure, "samesite": "none" if settings.auth_cookie_secure else "lax", "domain": settings.auth_cookie_domain or None, "path": "/"}
    response.set_cookie("tw_access", access_token, max_age=settings.access_token_expire_minutes * 60, **common)
    response.set_cookie("tw_refresh", refresh_token, max_age=settings.refresh_token_expire_days * 86400, **common)


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    for name in ("tw_access", "tw_refresh"):
        response.delete_cookie(name, domain=settings.auth_cookie_domain or None, path="/", secure=settings.auth_cookie_secure, samesite="none" if settings.auth_cookie_secure else "lax")


def _default_organization(user_id: str) -> str | None:
    rows = get_db().table("organization_members").select("organization_id").eq("user_id", user_id).eq("status", "active").is_("deleted_at", "null").order("created_at").limit(1).execute().data or []
    return str(rows[0]["organization_id"]) if rows else None


def _issue_session(user: dict, request: Request, response: Response, family_id: str | None = None) -> dict:
    settings = get_settings()
    refresh = generate_opaque_token("twr_")
    session = get_db().table("auth_sessions").insert({
        "user_id": user["id"], "refresh_token_hash": hash_secret(refresh),
        "family_id": family_id or str(uuid.uuid4()),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)).isoformat(),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }).execute().data[0]
    access = create_access_token(user, str(session["id"]), _default_organization(str(user["id"])))
    _set_session_cookies(response, access, refresh)
    return {"access_token": access, "token_type": "bearer", "expires_in": settings.access_token_expire_minutes * 60}


@router.post("/register", status_code=201)
def register(data: RegisterRequest, request: Request):
    consume(request, "auth.register", 5, 3600)
    db = get_db()
    email = str(data.email).lower()
    if db.table("users").select("id").eq("email", email).is_("deleted_at", "null").execute().data:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = db.table("users").insert({"email": email, "hashed_password": hash_password(data.password), "full_name": data.full_name}).execute().data[0]
    slug = f"workspace-{str(user['id'])[:8]}"
    org = db.table("organizations").insert({"name": f"{data.full_name or email}'s workspace", "slug": slug, "owner_user_id": user["id"]}).execute().data[0]
    db.table("organization_members").insert({"organization_id": org["id"], "user_id": user["id"], "role": "owner", "status": "active", "joined_at": datetime.now(timezone.utc).isoformat()}).execute()
    token = generate_opaque_token("twv_")
    db.table("auth_action_tokens").insert({"user_id": user["id"], "token_hash": hash_secret(token), "purpose": "verify_email", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}).execute()
    record_audit("account.registered", organization_id=str(org["id"]), actor_user_id=str(user["id"]), target_type="user", target_id=str(user["id"]))
    email_sent = send_action_email("Verify your TokenWatch email", f"{str(get_settings().app_base_url).rstrip('/')}/verify-email?token={token}", email)
    message = ("Registration successful. Verify your email before signing in." if email_sent else
               "Registration successful, but the verification email could not be sent right now. Use \"Resend verification\" in a few minutes, or contact support if this continues.")
    return {"message": message, "user_id": user["id"], "email_delivery": email_sent}


@router.post("/verify-email")
def verify_email(data: TokenActionRequest):
    now = datetime.now(timezone.utc).isoformat()
    rows = get_db().table("auth_action_tokens").select("id,user_id").eq("token_hash", hash_secret(data.token)).eq("purpose", "verify_email").is_("consumed_at", "null").gt("expires_at", now).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    get_db().table("auth_action_tokens").update({"consumed_at": now}).eq("id", rows[0]["id"]).execute()
    get_db().table("users").update({"email_verified_at": now}).eq("id", rows[0]["user_id"]).execute()
    record_audit("account.email_verified", actor_user_id=str(rows[0]["user_id"]), target_type="user", target_id=str(rows[0]["user_id"]))
    orgs = get_db().table("organizations").select("id").eq("owner_user_id", rows[0]["user_id"]).limit(1).execute().data or []
    if orgs: send_template_email("welcome", str(orgs[0]["id"]))
    return {"message": "Email verified"}


@router.post("/verify-email/resend", status_code=202)
def resend_verification(data: PasswordResetRequest, request: Request):
    consume(request, "auth.verify_resend", 5, 3600)
    rows = get_db().table("users").select("id,email,email_verified_at").eq("email", str(data.email).lower()).eq("is_active", True).is_("deleted_at", "null").limit(1).execute().data or []
    if rows and not rows[0].get("email_verified_at"):
        token = generate_opaque_token("twv_")
        get_db().table("auth_action_tokens").insert({"user_id": rows[0]["id"], "token_hash": hash_secret(token), "purpose": "verify_email", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()}).execute()
        send_action_email("Verify your TokenWatch email", f"{str(get_settings().app_base_url).rstrip('/')}/verify-email?token={token}", rows[0]["email"])
    return {"message": "If verification is pending, a new message was requested"}


@router.post("/login")
def login(data: LoginRequest, request: Request, response: Response):
    consume(request, "auth.login", 10, 900)
    rows = get_db().table("users").select("*").eq("email", str(data.email).lower()).is_("deleted_at", "null").limit(1).execute().data or []
    if not rows or not verify_password(data.password, rows[0]["hashed_password"]):
        record_audit("auth.login_failed", metadata={"email_hash": hash_secret(str(data.email).lower())})
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user = rows[0]
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")
    if not user.get("email_verified_at"):
        raise HTTPException(status_code=403, detail="Email verification required")
    tokens = _issue_session(user, request, response)
    get_db().table("users").update({"last_login_at": datetime.now(timezone.utc).isoformat()}).eq("id", user["id"]).execute()
    record_audit("auth.login", actor_user_id=str(user["id"]), organization_id=_default_organization(str(user["id"])))
    return {**tokens, "user_id": user["id"], "email": user["email"], "full_name": user.get("full_name", "")}


@router.post("/refresh")
def refresh(request: Request, response: Response, tw_refresh: str | None = Cookie(default=None)):
    consume(request, "auth.refresh", 60, 900)
    if not tw_refresh:
        raise HTTPException(status_code=401, detail="Refresh token required")
    now = datetime.now(timezone.utc).isoformat()
    rows = get_db().table("auth_sessions").select("*").eq("refresh_token_hash", hash_secret(tw_refresh)).is_("revoked_at", "null").gt("expires_at", now).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    old = rows[0]
    users = get_db().table("users").select("*").eq("id", old["user_id"]).eq("is_active", True).limit(1).execute().data or []
    if not users:
        raise HTTPException(status_code=401, detail="Account unavailable")
    get_db().table("auth_sessions").update({"revoked_at": now, "last_used_at": now}).eq("id", old["id"]).execute()
    tokens = _issue_session(users[0], request, response, str(old["family_id"]))
    replacement = get_db().table("auth_sessions").select("id").eq("family_id", old["family_id"]).is_("revoked_at", "null").order("created_at", desc=True).limit(1).execute().data[0]
    get_db().table("auth_sessions").update({"replaced_by_session_id": replacement["id"]}).eq("id", old["id"]).execute()
    return tokens


@router.post("/logout", status_code=204)
def logout(response: Response, principal: Principal = Depends(get_principal)):
    get_db().table("auth_sessions").update({"revoked_at": datetime.now(timezone.utc).isoformat()}).eq("id", principal.session_id).execute()
    record_audit("auth.logout", actor_user_id=principal.user_id, organization_id=principal.organization_id)
    _clear_session_cookies(response)


@router.get("/sessions")
def list_sessions(principal: Principal = Depends(get_principal)):
    return get_db().table("auth_sessions").select("id,created_at,last_used_at,expires_at,revoked_at,ip_address,user_agent").eq("user_id", principal.user_id).order("created_at", desc=True).execute().data or []


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: str, principal: Principal = Depends(get_principal)):
    rows = get_db().table("auth_sessions").update({"revoked_at": datetime.now(timezone.utc).isoformat()}).eq("id", session_id).eq("user_id", principal.user_id).is_("revoked_at", "null").execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Active session not found")
    record_audit("auth.session_revoked", actor_user_id=principal.user_id, organization_id=principal.organization_id, target_type="auth_session", target_id=session_id)


@router.post("/password-reset/request", status_code=202)
def request_password_reset(data: PasswordResetRequest, request: Request):
    consume(request, "auth.password_reset", 5, 3600)
    rows = get_db().table("users").select("id").eq("email", str(data.email).lower()).eq("is_active", True).is_("deleted_at", "null").limit(1).execute().data or []
    if rows:
        token = generate_opaque_token("twp_")
        get_db().table("auth_action_tokens").insert({"user_id": rows[0]["id"], "token_hash": hash_secret(token), "purpose": "reset_password", "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}).execute()
        send_action_email("Reset your TokenWatch password", f"{str(get_settings().app_base_url).rstrip('/')}/reset-password?token={token}", str(data.email).lower())
    return {"message": "If the account exists, reset instructions were sent"}


@router.post("/password-reset/confirm")
def confirm_password_reset(data: PasswordResetConfirm):
    now = datetime.now(timezone.utc).isoformat()
    rows = get_db().table("auth_action_tokens").select("id,user_id").eq("token_hash", hash_secret(data.token)).eq("purpose", "reset_password").is_("consumed_at", "null").gt("expires_at", now).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user_id = str(rows[0]["user_id"])
    current_user = get_db().table("users").select("token_version").eq("id", user_id).limit(1).execute().data[0]
    get_db().table("users").update({"hashed_password": hash_password(data.new_password), "token_version": int(current_user["token_version"]) + 1}).eq("id", user_id).execute()
    get_db().table("auth_sessions").update({"revoked_at": now}).eq("user_id", user_id).is_("revoked_at", "null").execute()
    get_db().table("auth_action_tokens").update({"consumed_at": now}).eq("id", rows[0]["id"]).execute()
    record_audit("account.password_reset", actor_user_id=user_id, target_type="user", target_id=user_id)
    return {"message": "Password reset; all sessions revoked"}


@router.post("/disable", status_code=204)
def disable_account(response: Response, principal: Principal = Depends(get_principal)):
    now = datetime.now(timezone.utc).isoformat()
    current_user = get_db().table("users").select("token_version").eq("id", principal.user_id).limit(1).execute().data[0]
    get_db().table("users").update({"is_active": False, "disabled_at": now, "token_version": int(current_user["token_version"]) + 1}).eq("id", principal.user_id).execute()
    get_db().table("auth_sessions").update({"revoked_at": now}).eq("user_id", principal.user_id).is_("revoked_at", "null").execute()
    record_audit("account.disabled", actor_user_id=principal.user_id, organization_id=principal.organization_id)
    _clear_session_cookies(response)


@router.get("/me")
def get_me(principal: Principal = Depends(get_principal)):
    rows = get_db().table("users").select("id,email,full_name,email_verified_at,is_active,created_at").eq("id", principal.user_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")
    return {**rows[0], "organization_id": principal.organization_id}


def get_current_user(principal: Principal = Depends(get_principal)) -> str:
    return principal.user_id
