from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from services.plans import Plan, plan_service
from utils.database import get_db


class EntitlementService:
    def plan(self, organization_id: str) -> Plan:
        return plan_service.for_organization(organization_id)

    def limit(self, organization_id: str, feature: str) -> int | bool:
        value = self.plan(organization_id).entitlements.get(feature, 0)
        return value if isinstance(value, (int, bool)) else 0

    def require_feature(self, organization_id: str, feature: str) -> None:
        if self.limit(organization_id, feature) is not True:
            raise HTTPException(status_code=403, detail={"code": "feature_not_in_plan", "feature": feature})

    def enforce_count(self, organization_id: str, feature: str, table: str, **filters: Any) -> None:
        limit = self.limit(organization_id, feature)
        if limit == -1:
            return
        query = get_db().table(table).select("id", count="exact").eq("organization_id", organization_id)
        for key, value in filters.items():
            query = query.eq(key, value)
        if table in {"api_keys", "alert_rules", "budget_policies", "organization_members"}:
            query = query.is_("deleted_at", "null")
        result = query.execute()
        count = result.count if result.count is not None else len(result.data or [])
        if count >= int(limit):
            raise HTTPException(status_code=409, detail={"code": "plan_limit_reached", "feature": feature, "limit": limit})

    def usage_snapshot(self, organization_id: str) -> dict[str, Any]:
        start = datetime.now(timezone.utc).date().replace(day=1).isoformat()
        rows = get_db().table("usage_counters").select("request_count,token_count,cost").eq(
            "organization_id", organization_id
        ).eq("period_type", "monthly").eq("period_start", start).is_("user_id", "null").is_("provider", "null").is_("model", "null").limit(1).execute().data or []
        usage = rows[0] if rows else {"request_count": 0, "token_count": 0, "cost": 0}
        plan = self.plan(organization_id)
        return {"plan": {"code": plan.code, "name": plan.name}, "usage": usage, "limits": plan.entitlements}

    def enforce_organization_creation(self, user_id: str) -> None:
        memberships = get_db().table("organization_members").select("organization_id").eq("user_id", user_id).eq("status", "active").is_("deleted_at", "null").execute().data or []
        if not memberships:
            return
        limits = [int(self.limit(str(row["organization_id"]), "organizations")) for row in memberships]
        if -1 in limits:
            return
        limit = max(limits or [1])
        if len({str(row["organization_id"]) for row in memberships}) >= limit:
            raise HTTPException(status_code=409, detail={"code": "plan_limit_reached", "feature": "organizations", "limit": limit})


entitlement_service = EntitlementService()
