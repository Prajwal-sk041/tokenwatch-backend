from datetime import datetime, timedelta, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Provider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"


class AlertProvider(StrEnum):
    ALL = "all"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    AZURE_OPENAI = "azure_openai"
    AWS_BEDROCK = "aws_bedrock"


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


class PasswordResetRequest(StrictModel):
    email: EmailStr


class PasswordResetConfirm(StrictModel):
    token: str = Field(min_length=32, max_length=512)
    new_password: str = Field(min_length=12, max_length=128)


class TokenActionRequest(StrictModel):
    token: str = Field(min_length=32, max_length=512)


class OrganizationCreate(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class OrganizationInvite(StrictModel):
    email: EmailStr
    role: str = Field(pattern=r"^(admin|member|viewer)$")


class IngestionKeyCreate(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    permissions: list[str] = Field(default_factory=lambda: ["usage:write", "policy:check"], max_length=10)
    expires_at: datetime | None = None


class BudgetPolicyCreate(StrictModel):
    scope_type: str = Field(pattern=r"^(organization|user|provider|model)$")
    scope_value: str | None = Field(default=None, max_length=160)
    period_type: str = Field(pattern=r"^(daily|monthly)$")
    amount: float = Field(ge=0, le=1_000_000_000)
    warning_threshold_percent: float = Field(default=80, ge=0, le=100)
    hard_stop_threshold_percent: float = Field(default=100, ge=0, le=100)
    action: str = Field(default="block", pattern=r"^(allow|warn|block|log)$")

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "organization" and self.scope_value is not None:
            raise ValueError("organization scope must not include scope_value")
        if self.scope_type != "organization" and not self.scope_value:
            raise ValueError("scope_value is required for this scope")
        return self


class PolicyCheckRequest(StrictModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=160)
    estimated_prompt_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    estimated_completion_tokens: int = Field(default=0, ge=0, le=2_000_000_000)
    user_id: str | None = None


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
    idempotency_key: str = Field(min_length=8, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    provider_request_id: str | None = Field(default=None, max_length=200)
    attributed_user_id: str | None = None
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
        now = datetime.now(timezone.utc)
        if value > now + timedelta(minutes=5) or value < now - timedelta(minutes=15):
            raise ValueError("timestamp must be within the accepted replay window")
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
    channel: str = Field(default="email", pattern=r"^(email|webhook|slack|teams)$")
    destination: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_destination(self):
        if self.channel == "webhook" and (not self.destination or not self.destination.startswith("https://")):
            raise ValueError("webhook destination must use HTTPS")
        return self


class SubscriptionChange(StrictModel):
    plan_code: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")


class CheckoutCreate(StrictModel):
    plan_code: str = Field(pattern=r"^(starter|pro|team)$")
    billing_interval: str = Field(default="month", pattern=r"^(month|year)$")
    coupon_code: str | None = Field(default=None, min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class PortalCreate(StrictModel):
    return_path: str = Field(default="/dashboard/billing", pattern=r"^/[A-Za-z0-9/_-]*$")


class SupportTicketCreate(StrictModel):
    category: str = Field(pattern=r"^(support|billing|bug|feedback|security)$")
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=10000)
    page_url: str | None = Field(default=None, max_length=2048)
    email: EmailStr | None = None


class OnboardingUpdate(StrictModel):
    current_step: int = Field(ge=1, le=11)
    completed_steps: list[int] = Field(default_factory=list, max_length=11)
    integration_type: str | None = Field(default=None, pattern=r"^(python|node|rest)$")
    provider: Provider | None = None
    completed: bool = False
    skipped: bool = False

    @field_validator("completed_steps")
    @classmethod
    def valid_steps(cls, value: list[int]) -> list[int]:
        if any(step < 1 or step > 11 for step in value):
            raise ValueError("completed_steps must contain values from 1 through 11")
        return sorted(set(value))


class OnboardingTestEvent(StrictModel):
    sdk_key: str = Field(min_length=24, max_length=512)
    provider: Provider
    model: str = Field(min_length=1, max_length=120)


class BudgetPolicyUpdate(StrictModel):
    amount: float | None = Field(default=None, ge=0, le=1_000_000_000)
    warning_threshold_percent: float | None = Field(default=None, ge=0, le=100)
    hard_stop_threshold_percent: float | None = Field(default=None, ge=0, le=100)
    action: str | None = Field(default=None, pattern=r"^(allow|warn|block|log)$")
    is_active: bool | None = None


class MemberRoleUpdate(StrictModel):
    role: str = Field(pattern=r"^(admin|member|viewer)$")


class AlertUpdate(StrictModel):
    threshold: float | None = Field(default=None, gt=0, le=1_000_000_000)
    is_active: bool | None = None
    destination: str | None = Field(default=None, max_length=2048)

