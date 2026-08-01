from datetime import datetime, timedelta, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class AlertProvider(StrEnum):
    ALL = "all"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class AlertType(StrEnum):
    COST = "cost"
    TOKENS = "tokens"
    REQUESTS = "requests"


class AlertPeriod(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RegisterRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(default="", max_length=100)


class LoginRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AddKeyRequest(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    key_value: str = Field(min_length=8, max_length=4096)
    provider: Provider
    monthly_budget: float | None = Field(default=None, gt=0, le=1_000_000)


class UsageLog(StrictModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._:/-]+$")
    prompt_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    completion_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    total_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    cost: float = Field(default=0.0, ge=0, le=1_000_000)
    project: str = Field(default="default", min_length=1, max_length=100)
    agent: str = Field(default="default", min_length=1, max_length=100)
    environment: str = Field(default="development", min_length=1, max_length=50)
    latency_ms: int = Field(default=0, ge=0, le=86_400_000)
    timestamp: datetime | None = None

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("timestamp cannot be more than five minutes in the future")
        return value

    @model_validator(mode="after")
    def validate_total(self):
        component_total = self.prompt_tokens + self.completion_tokens
        if self.total_tokens and component_total and self.total_tokens != component_total:
            raise ValueError("total_tokens must equal prompt_tokens plus completion_tokens")
        return self


class AlertCreate(StrictModel):
    alert_type: AlertType
    threshold: float = Field(gt=0, le=1_000_000_000)
    provider: AlertProvider = AlertProvider.ALL
    period: AlertPeriod = AlertPeriod.DAILY
    notify_email: EmailStr | None = None

