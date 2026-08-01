import base64
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "audit-service-key-placeholder")
os.environ.setdefault("JWT_SECRET", "audit-jwt-secret-with-at-least-32-characters")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
os.environ.setdefault("ALERT_SCHEDULER_ENABLED", "false")
os.environ.setdefault("API_KEY_ENCRYPTION_KEY", base64.urlsafe_b64encode(b"0" * 32).decode())
