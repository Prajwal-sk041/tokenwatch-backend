from functools import lru_cache
import os
from typing import Mapping

from cryptography.fernet import Fernet
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    supabase_url: HttpUrl
    supabase_service_key: str = Field(min_length=16)
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_expire_days: int = Field(default=30, ge=1, le=365)
    auth_cookie_secure: bool = True
    auth_cookie_domain: str = ""
    app_base_url: HttpUrl = "http://localhost:3000"
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    smtp_host: str = ""
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    resend_api_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_environment: str = "test"
    stripe_tax_enabled: bool = False
    sentry_dsn: str = ""
    sentry_environment: str = "production"
    admin_emails: tuple[str, ...] = ()
    public_status_cache_seconds: int = Field(default=30, ge=5, le=300)
    email_preview_enabled: bool = False
    alert_scheduler_enabled: bool = False
    api_key_encryption_key: str

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        return value

    @field_validator("api_key_encryption_key")
    @classmethod
    def validate_encryption_key(cls, value: str) -> str:
        try:
            Fernet(value.encode("ascii"))
        except Exception as exc:
            raise ValueError("API_KEY_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def validate_origins(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if not values or any(value == "*" for value in values):
            raise ValueError("CORS_ALLOWED_ORIGINS must contain explicit origins")
        return values

    @field_validator("stripe_environment")
    @classmethod
    def validate_stripe_environment(cls, value: str) -> str:
        if value not in {"test", "live"}:
            raise ValueError("STRIPE_ENVIRONMENT must be test or live")
        return value


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = environ or os.environ
    origins = tuple(
        origin.strip().rstrip("/")
        for origin in env.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    )
    return Settings(
        supabase_url=env.get("SUPABASE_URL", ""),
        supabase_service_key=env.get("SUPABASE_SERVICE_KEY", ""),
        jwt_secret=env.get("JWT_SECRET", ""),
        jwt_algorithm=env.get("JWT_ALGORITHM", "HS256"),
        access_token_expire_minutes=env.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"),
        refresh_token_expire_days=env.get("REFRESH_TOKEN_EXPIRE_DAYS", "30"),
        auth_cookie_secure=env.get("AUTH_COOKIE_SECURE", "true").lower() in {"1", "true", "yes", "on"},
        auth_cookie_domain=env.get("AUTH_COOKIE_DOMAIN", ""),
        app_base_url=env.get("APP_BASE_URL", "http://localhost:3000"),
        cors_allowed_origins=origins,
        smtp_host=env.get("SMTP_HOST", ""),
        smtp_port=env.get("SMTP_PORT") or "465",
        smtp_username=env.get("SMTP_USERNAME", ""),
        smtp_password=env.get("SMTP_PASSWORD", ""),
        smtp_from_email=env.get("SMTP_FROM_EMAIL", ""),
        resend_api_key=env.get("RESEND_API_KEY", ""),
        stripe_secret_key=env.get("STRIPE_SECRET_KEY", ""),
        stripe_webhook_secret=env.get("STRIPE_WEBHOOK_SECRET", ""),
        stripe_environment=env.get("STRIPE_ENVIRONMENT", "test"),
        stripe_tax_enabled=env.get("STRIPE_TAX_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
        sentry_dsn=env.get("SENTRY_DSN", ""),
        sentry_environment=env.get("SENTRY_ENVIRONMENT", "production"),
        admin_emails=tuple(x.strip().lower() for x in env.get("ADMIN_EMAILS", "").split(",") if x.strip()),
        public_status_cache_seconds=env.get("PUBLIC_STATUS_CACHE_SECONDS", "30"),
        email_preview_enabled=env.get("EMAIL_PREVIEW_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
        alert_scheduler_enabled=env.get("ALERT_SCHEDULER_ENABLED", "false").lower()
        in {"1", "true", "yes", "on"},
        api_key_encryption_key=env.get("API_KEY_ENCRYPTION_KEY", ""),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
