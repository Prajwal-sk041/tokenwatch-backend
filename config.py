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
    cors_allowed_origins: tuple[str, ...] = ("http://localhost:3000",)
    smtp_host: str = ""
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
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
        cors_allowed_origins=origins,
        smtp_host=env.get("SMTP_HOST", ""),
        smtp_port=env.get("SMTP_PORT") or "465",
        smtp_username=env.get("SMTP_USERNAME", ""),
        smtp_password=env.get("SMTP_PASSWORD", ""),
        smtp_from_email=env.get("SMTP_FROM_EMAIL", ""),
        alert_scheduler_enabled=env.get("ALERT_SCHEDULER_ENABLED", "false").lower()
        in {"1", "true", "yes", "on"},
        api_key_encryption_key=env.get("API_KEY_ENCRYPTION_KEY", ""),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()
