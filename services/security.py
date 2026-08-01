from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import uuid

from jose import jwt

from config import get_settings


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def generate_opaque_token(prefix: str = "") -> str:
    return prefix + secrets.token_urlsafe(48)


def create_access_token(user: dict, session_id: str, organization_id: str | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user["id"]),
        "email": user["email"],
        "sid": session_id,
        "ver": int(user.get("token_version", 1)),
        "org": organization_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "access" or not payload.get("sid"):
        raise ValueError("Invalid access token")
    return payload
