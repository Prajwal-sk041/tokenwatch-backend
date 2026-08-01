from fastapi import APIRouter, Depends, Header, HTTPException, Request

from dependencies import Principal, get_principal
from schemas.requests import CheckoutCreate, PortalCreate
from services.audit import record_audit
from services.billing import billing_service
from services.entitlements import entitlement_service
from services.plans import plan_service
from services.tenant import require_membership
from utils.database import get_db


router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/plans")
def plans():
    return plan_service.list_public()


@router.get("/{organization_id}/summary")
def summary(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id)
    subscriptions = get_db().table("subscriptions").select("*,plans(code,name,description,entitlements)").eq("organization_id", organization_id).is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute().data or []
    invoices = get_db().table("invoices").select("id,number,status,currency,total,amount_paid,hosted_invoice_url,invoice_pdf,due_at,paid_at,created_at").eq("organization_id", organization_id).is_("deleted_at", "null").order("created_at", desc=True).limit(24).execute().data or []
    return {"subscription": subscriptions[0] if subscriptions else None, "entitlements": entitlement_service.usage_snapshot(organization_id), "invoices": invoices}


@router.post("/{organization_id}/checkout", status_code=201)
def checkout(organization_id: str, payload: CheckoutCreate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "owner")
    users = get_db().table("users").select("email").eq("id", principal.user_id).limit(1).execute().data or []
    if not users: raise HTTPException(status_code=404, detail="User not found")
    url = billing_service.checkout(organization_id, users[0]["email"], payload.plan_code, payload.billing_interval, payload.coupon_code)
    record_audit("billing.checkout_created", organization_id=organization_id, actor_user_id=principal.user_id, metadata={"plan": payload.plan_code, "interval": payload.billing_interval})
    return {"url": url}


@router.post("/{organization_id}/portal", status_code=201)
def portal(organization_id: str, payload: PortalCreate, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "owner")
    return {"url": billing_service.portal(organization_id, payload.return_path)}


@router.post("/{organization_id}/resume", status_code=202)
def resume(organization_id: str, principal: Principal = Depends(get_principal)):
    require_membership(principal.user_id, organization_id, "owner")
    billing_service.resume(organization_id)
    record_audit("subscription.resume_requested", organization_id=organization_id, actor_user_id=principal.user_id)
    return {"status": "processing"}


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, stripe_signature: str = Header(alias="stripe-signature")):
    payload = await request.body()
    event = billing_service.provider().verify_webhook(payload, stripe_signature)
    return {"status": billing_service.process_webhook(event)}
