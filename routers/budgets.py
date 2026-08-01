from fastapi import APIRouter, Depends

from dependencies import Principal, get_principal
from datetime import datetime, timezone
from fastapi import HTTPException
from schemas.requests import BudgetPolicyCreate, BudgetPolicyUpdate
from services.audit import record_audit
from services.tenant import require_membership
from services.entitlements import entitlement_service
from utils.database import get_db


router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.post("/{organization_id}", status_code=201)
def create_budget(organization_id: str, payload: BudgetPolicyCreate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    entitlement_service.enforce_count(organization_id, "budgets", "budget_policies", is_active=True)
    row = get_db().table("budget_policies").insert({"organization_id": organization_id, **payload.model_dump()}).execute().data[0]
    record_audit("budget.updated", organization_id=organization_id, actor_user_id=principal.user_id, target_type="budget_policy", target_id=str(row["id"]), metadata={"scope_type": payload.scope_type, "period_type": payload.period_type})
    return row


@router.get("/{organization_id}")
def list_budgets(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    return get_db().table("budget_policies").select("*").eq("organization_id", organization_id).is_("deleted_at", "null").execute().data or []


@router.patch("/{organization_id}/{budget_id}")
def update_budget(organization_id: str, budget_id: str, payload: BudgetPolicyUpdate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    values = payload.model_dump(exclude_none=True)
    rows = get_db().table("budget_policies").update(values).eq("id", budget_id).eq("organization_id", organization_id).is_("deleted_at", "null").execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Budget not found")
    record_audit("budget.updated", organization_id=organization_id, actor_user_id=principal.user_id, target_type="budget_policy", target_id=budget_id)
    return rows[0]


@router.delete("/{organization_id}/{budget_id}", status_code=204)
def delete_budget(organization_id: str, budget_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    now = datetime.now(timezone.utc).isoformat()
    rows = get_db().table("budget_policies").update({"is_active": False, "deleted_at": now}).eq("id", budget_id).eq("organization_id", organization_id).is_("deleted_at", "null").execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Budget not found")
    record_audit("budget.deleted", organization_id=organization_id, actor_user_id=principal.user_id, target_type="budget_policy", target_id=budget_id)
