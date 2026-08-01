from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from utils.database import get_db
from config import get_settings


@dataclass(frozen=True)
class Plan:
    id: str
    code: str
    name: str
    entitlements: dict[str, Any]


class PlanService:
    def list_public(self) -> list[dict[str, Any]]:
        return get_db().table("plans").select(
            "id,code,name,description,monthly_price,annual_price,currency,monthly_event_limit,features,entitlements,sort_order"
        ).eq("is_active", True).order("sort_order").execute().data or []

    def by_code(self, code: str) -> dict[str, Any]:
        rows = get_db().table("plans").select("*").eq("code", code).eq("is_active", True).limit(1).execute().data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Plan not found")
        return rows[0]

    def by_provider_price(self, price_id: str | None) -> dict[str, Any] | None:
        if not price_id:
            return None
        rows = get_db().table("plans").select("*").eq("is_active", True).execute().data or []
        env = get_settings().stripe_environment
        for plan in rows:
            if plan.get(f"stripe_{env}_monthly_price_id") == price_id or plan.get(f"stripe_{env}_annual_price_id") == price_id:
                return plan
        return None

    def for_organization(self, organization_id: str) -> Plan:
        rows = get_db().table("subscriptions").select("plan_id,plans(id,code,name,entitlements)").eq(
            "organization_id", organization_id
        ).in_("status", ["trialing", "active", "past_due"]).is_("deleted_at", "null").limit(1).execute().data or []
        data = rows[0].get("plans") if rows else self.by_code("free")
        return Plan(str(data["id"]), data["code"], data["name"], data.get("entitlements") or {})


plan_service = PlanService()
