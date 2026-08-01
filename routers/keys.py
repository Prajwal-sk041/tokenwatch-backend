import logging

from fastapi import APIRouter, Depends, HTTPException

from routers.auth import get_current_user
from schemas.requests import AddKeyRequest
from utils.database import get_db
from utils.encryption import decrypt_api_key, encrypt_api_key, mask_api_key


router = APIRouter(prefix="/keys", tags=["API Keys"])
logger = logging.getLogger(__name__)


@router.post("/add", status_code=201)
def add_key(data: AddKeyRequest, user_id: str = Depends(get_current_user)):
    try:
        record = {
            "user_id": user_id,
            "key_name": data.name,
            "encrypted_key": encrypt_api_key(data.key_value),
            "provider": data.provider.value,
            "is_active": True,
        }
        if data.monthly_budget is not None:
            record["monthly_budget"] = data.monthly_budget
        result = get_db().table("api_keys").insert(record).execute()
        return {
            "message": "API key added successfully",
            "key_id": result.data[0]["id"],
            "name": data.name,
            "provider": data.provider.value,
            "masked_key": mask_api_key(data.key_value),
        }
    except Exception:
        logger.exception("API key creation failed")
        raise HTTPException(status_code=500, detail="Unable to save API key") from None


@router.get("/list")
def list_keys(user_id: str = Depends(get_current_user)):
    try:
        result = get_db().table("api_keys").select(
            "id, key_name, provider, encrypted_key, monthly_budget, is_active, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).execute()
        return [
            {
                "id": row["id"],
                "name": row["key_name"],
                "provider": row["provider"],
                "masked_key": mask_api_key(decrypt_api_key(row["encrypted_key"])),
                "monthly_budget": row.get("monthly_budget"),
                "is_active": row.get("is_active", True),
                "created_at": row["created_at"],
            }
            for row in (result.data or [])
        ]
    except Exception:
        logger.exception("API key listing failed")
        raise HTTPException(status_code=500, detail="Unable to load API keys") from None


@router.delete("/delete/{key_id}")
def delete_key(key_id: str, user_id: str = Depends(get_current_user)):
    try:
        existing = get_db().table("api_keys").select("id").eq("id", key_id).eq(
            "user_id", user_id
        ).execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="API key not found")
        get_db().table("api_keys").delete().eq("id", key_id).eq("user_id", user_id).execute()
        return {"message": "API key deleted successfully", "key_id": key_id}
    except HTTPException:
        raise
    except Exception:
        logger.exception("API key deletion failed")
        raise HTTPException(status_code=500, detail="Unable to delete API key") from None
