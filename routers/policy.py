from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from dependencies import SdkPrincipal, get_sdk_principal, require_sdk_permission
from services.budget import BudgetDecision, evaluate_budget
from services.pricing import calculate_cost
from services.audit import record_audit
from utils.database import get_db


router = APIRouter(prefix="/policy", tags=["Policy Engine"])


@router.get("/check")
def check_policy(
    provider: str = Query(), model: str = Query(), estimated_prompt_tokens: int = Query(default=0, ge=0),
    estimated_completion_tokens: int = Query(default=0, ge=0), user_id: str | None = Query(default=None),
    sdk: SdkPrincipal = Depends(get_sdk_principal),
):
    require_sdk_permission(sdk, "policy:check")
    try:
        estimated = calculate_cost(provider, model, estimated_prompt_tokens, estimated_completion_tokens)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    today = datetime.now(timezone.utc).date()
    policies = get_db().table("budget_policies").select("*").eq("organization_id", sdk.organization_id).eq("is_active", True).is_("deleted_at", "null").execute().data or []
    decisions: list[BudgetDecision] = []
    for policy in policies:
        scope = policy["scope_type"]
        value = policy.get("scope_value")
        if scope == "provider" and value != provider or scope == "model" and value != model or scope == "user" and value != user_id:
            continue
        period_start = today.replace(day=1) if policy["period_type"] == "monthly" else today
        query = get_db().table("usage_counters").select("cost").eq("organization_id", sdk.organization_id).eq("period_type", policy["period_type"]).eq("period_start", period_start.isoformat())
        if scope == "provider": query = query.eq("provider", provider)
        if scope == "model": query = query.eq("model", model)
        if scope == "user": query = query.eq("user_id", user_id)
        current = sum(Decimal(str(row["cost"])) for row in (query.execute().data or []))
        decisions.append(evaluate_budget(current, estimated, Decimal(str(policy["amount"])), Decimal(str(policy["warning_threshold_percent"])), Decimal(str(policy["hard_stop_threshold_percent"])), policy["action"]))
    decision = next((item for item in decisions if item.blocked), next((item for item in decisions if item.action == "warn"), BudgetDecision(True, False, "allow", "No blocking policy", None, Decimal(0))))
    if decision.blocked:
        record_audit(
            "policy.request_blocked",
            organization_id=sdk.organization_id,
            target_type="provider_model",
            target_id=f"{provider}:{model}",
            metadata={
                "provider": provider,
                "model": model,
                "estimated_cost": str(estimated),
                "reason": decision.reason,
            },
        )
    return {"allowed": decision.allowed, "blocked": decision.blocked, "reason": decision.reason, "remaining_budget": str(decision.remaining_budget) if decision.remaining_budget is not None else None, "current_usage": str(decision.current_usage), "action": decision.action}
