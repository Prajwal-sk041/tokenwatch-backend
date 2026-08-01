from functools import lru_cache

from supabase import Client, create_client

from config import get_settings


@lru_cache
def get_db() -> Client:
    settings = get_settings()
    return create_client(str(settings.supabase_url).rstrip("/"), settings.supabase_service_key)


def check_database_connection() -> bool:
    try:
        get_db().table("users").select("id", count="exact").limit(1).execute()
        return True
    except Exception:
        return False
