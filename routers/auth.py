import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from schemas.requests import LoginRequest, RegisterRequest
from utils.auth import create_access_token, decode_token, hash_password, verify_password
from utils.database import get_db


router = APIRouter(prefix="/auth", tags=["Authentication"])
security = HTTPBearer()
logger = logging.getLogger(__name__)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise JWTError("missing subject")
        return str(user_id)
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


@router.post("/register", status_code=201)
def register(data: RegisterRequest):
    try:
        db = get_db()
        email = str(data.email).lower()
        if db.table("users").select("id").eq("email", email).execute().data:
            raise HTTPException(status_code=409, detail="Email already registered")
        result = db.table("users").insert(
            {"email": email, "hashed_password": hash_password(data.password), "full_name": data.full_name}
        ).execute()
        return {"message": "User registered successfully", "user_id": result.data[0]["id"], "email": email}
    except HTTPException:
        raise
    except Exception:
        logger.exception("registration failed")
        raise HTTPException(status_code=500, detail="Unable to register user") from None


@router.post("/login")
def login(data: LoginRequest):
    try:
        email = str(data.email).lower()
        result = get_db().table("users").select("*").eq("email", email).execute()
        if not result.data or not verify_password(data.password, result.data[0]["hashed_password"]):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        user = result.data[0]
        if not user.get("is_active", True):
            raise HTTPException(status_code=403, detail="Account is inactive")
        return {
            "access_token": create_access_token({"sub": user["id"], "email": user["email"]}),
            "token_type": "bearer",
            "user_id": user["id"],
            "email": user["email"],
            "full_name": user.get("full_name", ""),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("login failed")
        raise HTTPException(status_code=500, detail="Unable to sign in") from None


@router.get("/me")
def get_me(user_id: str = Depends(get_current_user)):
    try:
        result = get_db().table("users").select(
            "id, email, full_name, plan, is_active, created_at"
        ).eq("id", user_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="User not found")
        return result.data
    except HTTPException:
        raise
    except Exception:
        logger.exception("user lookup failed")
        raise HTTPException(status_code=500, detail="Unable to load user") from None
