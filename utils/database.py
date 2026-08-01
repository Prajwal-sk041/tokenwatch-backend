import threading

from supabase import Client, create_client

from config import get_settings


_thread_clients = threading.local()


def get_db() -> Client:
    client = getattr(_thread_clients, "client", None)
    if client is None:
        settings = get_settings()
        client = create_client(str(settings.supabase_url).rstrip("/"), settings.supabase_service_key)
        _thread_clients.client = client
    return client


def check_database_connection() -> bool:
    try:
        get_db().table("users").select("id", count="exact").limit(1).execute()
        return True
    except Exception:
        return False
