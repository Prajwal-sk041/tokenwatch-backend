from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from utils.database import get_db
from utils.auth import decode_token

router = APIRouter(prefix="/keys", tags=["API Keys"])
security = HTTPBearer()

# --- Schemas ---
class AddKeyRequest(BaseModel):
    name: str
    key_value: str          # ✅ matches frontend field name
    provider: str
    monthly_budget: Optional[float] = None

# --- Helper ---
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials.strip().strip('"').strip("'")
        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token error: {str(e)}")

# --- Add Key ---
@router.post("/add")
def add_key(data: AddKeyRequest, user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        insert_data = {
            "user_id": user_id,
            "key_name": data.name,
            "encrypted_key": data.key_value,   # ✅ use key_value
            "provider": data.provider,
            "is_active": True
        }
        if data.monthly_budget is not None:
            insert_data["monthly_budget"] = data.monthly_budget

        result = db.table("api_keys").insert(insert_data).execute()
        return {
            "message": "API key added successfully! 🎉",
            "key_id": result.data[0]["id"],
            "name": data.name,
            "provider": data.provider
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- List Keys ---
@router.get("/list")
def list_keys(user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        result = db.table("api_keys").select(
            "id, key_name, provider, monthly_budget, is_active, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()

        keys = []
        for row in result.data:
            keys.append({
                "id": row["id"],
                "name": row["key_name"],
                "provider": row["provider"],
                "monthly_budget": row.get("monthly_budget"),
                "is_active": row.get("is_active", True),
                "created_at": row["created_at"]
            })

        return keys
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# --- Delete Key ---
@router.delete("/delete/{key_id}")
def delete_key(key_id: str, user_id: str = Depends(get_current_user)):
    try:
        db = get_db()
        existing = db.table("api_keys").select("id").eq("id", key_id).eq("user_id", user_id).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Key not found or unauthorized")
        db.table("api_keys").delete().eq("id", key_id).execute()
        return {
            "message": "API key deleted successfully! 🗑️",
            "key_id": key_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
