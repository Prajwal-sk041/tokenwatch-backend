from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from utils.database import get_db
from utils.auth import hash_password, verify_password, create_access_token, decode_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

security = HTTPBearer()

# --- Schemas ---
class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

# --- Helper: Get current user from token ---
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials.strip().strip('"').strip("'")
        print(f"DEBUG TOKEN: {token[:50]}...")
        payload = decode_token(token)
        print(f"DEBUG PAYLOAD: {payload}")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token - no sub field")
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token error: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"}
        )

# --- Register ---
@router.post("/register")
def register(data: RegisterRequest):
    db = get_db()
    existing = db.table("users").select("id").eq("email", data.email).execute()
    if existing.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    hashed = hash_password(data.password)
    result = db.table("users").insert({
        "email": data.email,
        "hashed_password": hashed,
        "full_name": data.full_name
    }).execute()
    return {
        "message": "User registered successfully! 🎉",
        "user_id": result.data[0]["id"],
        "email": data.email
    }

# --- Login ---
@router.post("/login")
def login(data: LoginRequest):
    db = get_db()
    result = db.table("users").select("*").eq("email", data.email).execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    user = result.data[0]
    if not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    token = create_access_token({"sub": user["id"], "email": user["email"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"]
    }

# --- Get Current User (Protected) ---
@router.get("/me")
def get_me(user_id: str = Depends(get_current_user)):
    db = get_db()
    result = db.table("users").select(
        "id, email, full_name, plan, is_active, created_at"
    ).eq("id", user_id).single().execute()
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return result.data
