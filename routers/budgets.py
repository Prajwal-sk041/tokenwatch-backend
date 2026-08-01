from fastapi import APIRouter, Depends

from dependencies import Principal, get_principal
from schemas.requests import BudgetPolicyCreate
from services.audit import record_audit
from services.tenant import require_membership
from utils.database import get_db


router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.post("/{organization_id}", status_code=201)
def create_budget(organization_id: str, payload: BudgetPolicyCreate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "admin")
    row = get_db().table("budget_policies").insert({"organization_id": organization_id, **payload.model_dump()}).execute().data[0]
    record_audit("budget.updated", organization_id=organization_id, actor_user_id=principal.user_id, target_type="budget_policy", target_id=str(row["id"]), metadata={"scope_type": payload.scope_type, "period_type": payload.period_type})
    return row


@router.get("/{organization_id}")
def list_budgets(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    return get_db().table("budget_policies").select("*").eq("organization_id", organization_id).is_("deleted_at", "null").execute().data or []
