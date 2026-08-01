from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import HTTPException
import stripe

from config import get_settings
from services.audit import record_audit
from services.plans import plan_service
from utils.database import get_db
from utils.email import send_template_email

logger = logging.getLogger(__name__)


class BillingProvider(ABC):
    @abstractmethod
    def create_checkout(self, **kwargs: Any) -> str: ...
    @abstractmethod
    def create_portal(self, **kwargs: Any) -> str: ...
    @abstractmethod
    def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]: ...
    @abstractmethod
    def provision_plan(self, plan: dict[str, Any]) -> dict[str, str]: ...
    @abstractmethod
    def resume_subscription(self, subscription_id: str) -> None: ...


class StripeProvider(BillingProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.stripe_secret_key:
            raise HTTPException(status_code=503, detail="Billing is not configured")
        expected_prefix = "sk_live_" if settings.stripe_environment == "live" else "sk_test_"
        if not settings.stripe_secret_key.startswith(expected_prefix):
            raise HTTPException(status_code=503, detail="Billing environment configuration is inconsistent")
        stripe.api_key = settings.stripe_secret_key
        self.settings = settings

    def create_checkout(self, *, customer_id: str | None, customer_email: str, organization_id: str, plan: dict, interval: str, coupon_code: str | None = None) -> str:
        prefix = f"stripe_{self.settings.stripe_environment}_"
        price_id = plan.get(prefix + ("annual_price_id" if interval == "year" else "monthly_price_id"))
        if not price_id:
            raise HTTPException(status_code=503, detail="Selected plan price is not configured")
        params: dict[str, Any] = {
            "mode": "subscription", "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": f"{str(self.settings.app_base_url).rstrip('/')}/dashboard/billing?checkout=success",
            "cancel_url": f"{str(self.settings.app_base_url).rstrip('/')}/dashboard/billing?checkout=canceled",
            "client_reference_id": organization_id,
            "metadata": {"organization_id": organization_id, "plan_code": plan["code"]},
            "subscription_data": {"trial_period_days": 14, "metadata": {"organization_id": organization_id, "plan_code": plan["code"]}},
            "automatic_tax": {"enabled": self.settings.stripe_tax_enabled},
            "allow_promotion_codes": coupon_code is None,
        }
        params["customer"] = customer_id if customer_id else None
        if not customer_id:
            params.pop("customer")
            params["customer_email"] = customer_email
        if coupon_code:
            promotions = stripe.PromotionCode.list(code=coupon_code, active=True, limit=1)
            if not promotions.data:
                raise HTTPException(status_code=422, detail="Coupon is invalid or expired")
            params["discounts"] = [{"promotion_code": promotions.data[0].id}]
        session = stripe.checkout.Session.create(**params)
        if not session.url:
            raise HTTPException(status_code=502, detail="Billing provider returned no checkout URL")
        return session.url

    def create_portal(self, *, customer_id: str, return_url: str) -> str:
        session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
        return session.url

    def verify_webhook(self, payload: bytes, signature: str) -> dict[str, Any]:
        if not self.settings.stripe_webhook_secret:
            raise HTTPException(status_code=503, detail="Billing webhook is not configured")
        try:
            event = stripe.Webhook.construct_event(payload, signature, self.settings.stripe_webhook_secret, tolerance=300)
            if bool(event.get("livemode")) != (self.settings.stripe_environment == "live"):
                raise HTTPException(status_code=400, detail="Webhook environment mismatch")
            return event
        except (ValueError, stripe.error.SignatureVerificationError) as exc:
            raise HTTPException(status_code=400, detail="Invalid webhook signature") from exc

    def provision_plan(self, plan: dict[str, Any]) -> dict[str, str]:
        prefix = f"stripe_{self.settings.stripe_environment}_"
        product_id = plan.get(prefix + "product_id")
        if not product_id:
            product = stripe.Product.create(name=f"TokenWatch {plan['name']}", description=plan.get("description"), metadata={"plan_code": plan["code"]})
            product_id = product.id
        monthly_id = plan.get(prefix + "monthly_price_id")
        if not monthly_id:
            monthly_id = stripe.Price.create(product=product_id, currency="usd", unit_amount=int(float(plan["monthly_price"]) * 100), recurring={"interval": "month"}, metadata={"plan_code": plan["code"]}).id
        annual_id = plan.get(prefix + "annual_price_id")
        if not annual_id:
            annual_id = stripe.Price.create(product=product_id, currency="usd", unit_amount=int(float(plan["annual_price"]) * 100), recurring={"interval": "year"}, metadata={"plan_code": plan["code"]}).id
        return {"product_id": product_id, "monthly_price_id": monthly_id, "annual_price_id": annual_id}

    def resume_subscription(self, subscription_id: str) -> None:
        stripe.Subscription.modify(subscription_id, cancel_at_period_end=False)


class BillingService:
    handled_events = {
        "checkout.session.completed", "customer.subscription.created", "customer.subscription.updated",
        "customer.subscription.deleted", "invoice.paid", "invoice.payment_failed",
        "customer.subscription.trial_will_end",
    }

    def provider(self) -> BillingProvider:
        return StripeProvider()

    def checkout(self, organization_id: str, user_email: str, plan_code: str, interval: str, coupon_code: str | None = None) -> str:
        plan = plan_service.by_code(plan_code)
        rows = get_db().table("subscriptions").select("provider_customer_id,status").eq("organization_id", organization_id).is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute().data or []
        if rows and rows[0].get("status") in {"trialing", "active", "past_due", "unpaid", "paused"}:
            raise HTTPException(status_code=409, detail="Manage the existing subscription in the billing portal")
        customer_id = rows[0].get("provider_customer_id") if rows else None
        return self.provider().create_checkout(customer_id=customer_id, customer_email=user_email, organization_id=organization_id, plan=plan, interval=interval, coupon_code=coupon_code)

    def portal(self, organization_id: str, return_path: str) -> str:
        rows = get_db().table("subscriptions").select("provider_customer_id").eq("organization_id", organization_id).is_("deleted_at", "null").limit(1).execute().data or []
        if not rows or not rows[0].get("provider_customer_id"):
            raise HTTPException(status_code=409, detail="No billing customer exists for this organization")
        return self.provider().create_portal(customer_id=rows[0]["provider_customer_id"], return_url=f"{str(get_settings().app_base_url).rstrip('/')}{return_path}")

    def provision_catalog(self) -> list[dict[str, str]]:
        configured = []
        for code in ("starter", "pro", "team"):
            plan = plan_service.by_code(code)
            ids = self.provider().provision_plan(plan)
            prefix = f"stripe_{get_settings().stripe_environment}_"
            get_db().table("plans").update({prefix+"product_id": ids["product_id"], prefix+"monthly_price_id": ids["monthly_price_id"], prefix+"annual_price_id": ids["annual_price_id"]}).eq("id", plan["id"]).execute()
            configured.append({"plan": code, **ids})
        return configured

    def resume(self, organization_id: str) -> None:
        rows = get_db().table("subscriptions").select("provider_subscription_id,status").eq("organization_id", organization_id).eq("provider", "stripe").is_("deleted_at", "null").order("created_at", desc=True).limit(1).execute().data or []
        if not rows or not rows[0].get("provider_subscription_id"):
            raise HTTPException(status_code=404, detail="Subscription not found")
        if rows[0].get("status") not in {"active", "trialing", "paused", "past_due"}:
            raise HTTPException(status_code=409, detail="Subscription cannot be resumed")
        self.provider().resume_subscription(rows[0]["provider_subscription_id"])

    def process_webhook(self, event: dict[str, Any]) -> str:
        event_id, event_type = event["id"], event["type"]
        existing = get_db().table("billing_events").select("status,attempts").eq("provider", "stripe").eq("provider_event_id", event_id).limit(1).execute().data or []
        if existing and existing[0]["status"] == "processed":
            return "duplicate"
        obj = event["data"]["object"]
        organization_id = (obj.get("metadata") or {}).get("organization_id") or obj.get("client_reference_id")
        if not existing:
            payload = event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else dict(event)
            try:
                get_db().table("billing_events").insert({"provider": "stripe", "provider_event_id": event_id, "event_type": event_type, "organization_id": organization_id, "payload": payload, "livemode": bool(event.get("livemode")), "request_id": (event.get("request") or {}).get("id") if isinstance(event.get("request"), dict) else event.get("request")}).execute()
            except Exception:
                raced = get_db().table("billing_events").select("status").eq("provider", "stripe").eq("provider_event_id", event_id).limit(1).execute().data or []
                if raced:
                    return "duplicate"
                raise
        elif existing:
            get_db().table("billing_events").update({"attempts": int(existing[0].get("attempts") or 1) + 1}).eq("provider_event_id", event_id).eq("provider", "stripe").execute()
        try:
            if event_type not in self.handled_events:
                status = "ignored"
            else:
                self._dispatch(event_type, obj, organization_id, event_id)
                status = "processed"
            get_db().table("billing_events").update({"status": status, "processed_at": datetime.now(timezone.utc).isoformat()}).eq("provider_event_id", event_id).eq("provider", "stripe").execute()
            return status
        except Exception as exc:
            logger.exception("billing_webhook_failed", extra={"event_id": event_id, "event_type": event_type})
            get_db().table("billing_events").update({"status": "failed", "error_message": str(exc)[:1000]}).eq("provider_event_id", event_id).eq("provider", "stripe").execute()
            raise

    def _dispatch(self, event_type: str, obj: dict[str, Any], organization_id: str | None, event_id: str) -> None:
        if event_type == "checkout.session.completed":
            if not organization_id:
                raise ValueError("Checkout is missing organization metadata")
            return
        if event_type == "customer.subscription.trial_will_end":
            self._sync_subscription(obj, organization_id, event_id)
            resolved_org = organization_id or (obj.get("metadata") or {}).get("organization_id")
            if resolved_org: send_template_email("trial_ending", resolved_org, context={"idempotency_key": f"stripe:{event_id}:trial_ending"})
        elif event_type.startswith("customer.subscription."):
            self._sync_subscription(obj, organization_id, event_id)
            if event_type == "customer.subscription.deleted":
                resolved_org = organization_id or (obj.get("metadata") or {}).get("organization_id")
                if resolved_org: send_template_email("subscription_cancelled", resolved_org, context={"idempotency_key": f"stripe:{event_id}:subscription_cancelled"})
        elif event_type.startswith("invoice."):
            self._sync_invoice(obj, event_type, event_id)

    def _sync_subscription(self, obj: dict[str, Any], organization_id: str | None, event_id: str) -> None:
        metadata = obj.get("metadata") or {}
        organization_id = organization_id or metadata.get("organization_id")
        if not organization_id:
            raise ValueError("Subscription is missing organization metadata")
        price_id = ((obj.get("items") or {}).get("data") or [{}])[0].get("price", {}).get("id")
        plan = plan_service.by_provider_price(price_id) or plan_service.by_code(metadata.get("plan_code", "free"))
        now = datetime.now(timezone.utc).isoformat()
        values = {"organization_id": organization_id, "plan_id": plan["id"], "provider": "stripe", "provider_customer_id": obj.get("customer"),
            "provider_subscription_id": obj["id"], "provider_price_id": price_id,
            "status": obj.get("status", "incomplete"), "current_period_start": _timestamp(obj.get("current_period_start")),
            "current_period_end": _timestamp(obj.get("current_period_end")), "trial_start": _timestamp(obj.get("trial_start")), "trial_end": _timestamp(obj.get("trial_end")),
            "cancel_at_period_end": bool(obj.get("cancel_at_period_end")), "canceled_at": _timestamp(obj.get("canceled_at")),
            "conversion_at": now if obj.get("status") == "active" else None, "metadata": metadata, "updated_at": now}
        rows = get_db().table("subscriptions").select("id,status").eq("provider", "stripe").eq("provider_subscription_id", obj["id"]).limit(1).execute().data or []
        if rows:
            get_db().table("subscriptions").update(values).eq("id", rows[0]["id"]).execute()
        else:
            get_db().table("subscriptions").insert(values).execute()
        record_audit("subscription.synced", organization_id=organization_id, target_type="subscription", metadata={"status": values["status"], "plan": plan["code"]})
        if values["status"] == "active":
            send_template_email("subscription_active", organization_id, context={"idempotency_key": f"stripe:{event_id}:subscription_active"})

    def _sync_invoice(self, obj: dict[str, Any], event_type: str, event_id: str) -> None:
        subscription_id = obj.get("subscription")
        subs = get_db().table("subscriptions").select("id,organization_id").eq("provider_subscription_id", subscription_id).limit(1).execute().data or []
        if not subs:
            raise ValueError("Invoice subscription is unknown")
        sub = subs[0]
        values = {"organization_id": sub["organization_id"], "subscription_id": sub["id"], "provider": "stripe", "provider_invoice_id": obj["id"],
            "number": obj.get("number"), "status": obj.get("status", "open"), "currency": str(obj.get("currency", "usd")).upper(),
            "subtotal": _money(obj.get("subtotal")), "tax": _money((obj.get("total_tax_amounts") or [{}])[0].get("amount")), "total": _money(obj.get("total")),
            "amount_paid": _money(obj.get("amount_paid")), "hosted_invoice_url": obj.get("hosted_invoice_url"), "invoice_pdf": obj.get("invoice_pdf"),
            "due_at": _timestamp(obj.get("due_date")), "paid_at": _timestamp((obj.get("status_transitions") or {}).get("paid_at"))}
        existing = get_db().table("invoices").select("id").eq("provider_invoice_id", obj["id"]).eq("provider", "stripe").limit(1).execute().data or []
        if existing: get_db().table("invoices").update(values).eq("id", existing[0]["id"]).execute()
        else: get_db().table("invoices").insert(values).execute()
        get_db().table("subscriptions").update({"latest_invoice_id": obj["id"], "payment_failure_at": datetime.now(timezone.utc).isoformat() if event_type == "invoice.payment_failed" else None}).eq("id", sub["id"]).execute()
        if event_type == "invoice.payment_failed":
            send_template_email("payment_failed", sub["organization_id"], context={"invoice_url": obj.get("hosted_invoice_url"), "idempotency_key": f"stripe:{event_id}:payment_failed"})
        elif event_type == "invoice.paid":
            send_template_email("invoice_paid", sub["organization_id"], context={"invoice_url": obj.get("hosted_invoice_url"), "idempotency_key": f"stripe:{event_id}:invoice_paid"})


def _timestamp(value: int | None) -> str | None:
    return datetime.fromtimestamp(value, timezone.utc).isoformat() if value else None


def _money(value: int | None) -> float:
    return round((value or 0) / 100, 2)


billing_service = BillingService()
