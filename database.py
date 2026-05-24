import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Bulletproof: load .env from the backend directory directly
load_dotenv(dotenv_path=r"C:\SaaS Product\TokenWatch\backend\.env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

print(f"DEBUG - URL loaded: {bool(SUPABASE_URL)}")
print(f"DEBUG - KEY loaded: {bool(SUPABASE_KEY)}")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ SUPABASE_URL or SUPABASE_SERVICE_KEY not found in .env!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
