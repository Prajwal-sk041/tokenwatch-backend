from datetime import date, datetime, timezone
from pathlib import Path
import pytest
from pydantic import ValidationError
from config import load_settings
from services.reporting import local_day, report_range
from types import SimpleNamespace
from fastapi import HTTPException
from services.billing import StripeProvider
from utils.email import send_alert_email
import sys

def test_atomic_ingestion_migration_is_transactional_and_idempotent():
    sql=Path("migrations/202608010007_phase56_atomic_usage.sql").read_text(encoding="utf-8")
    assert "function public.ingest_usage_atomic" in sql
    assert "on conflict (organization_id,user_id,provider,model,period_type,period_start)" in sql
    assert "exception when unique_violation" in sql
    assert "grant execute on function public.ingest_usage_atomic(jsonb) to service_role" in sql
    assert "reconcile_usage_counters" in sql and "p_repair boolean default false" in sql

def test_ist_midnight_uses_iana_boundary():
    selected=report_range("Asia/Kolkata","today",now=datetime(2026,8,1,12,tzinfo=timezone.utc))
    assert selected.start_utc.isoformat()=="2026-07-31T18:30:00+00:00"
    assert selected.end_utc.isoformat()=="2026-08-01T18:30:00+00:00"

def test_pacific_dst_day_is_23_hours():
    selected=report_range("America/Los_Angeles","custom",date(2026,3,8),date(2026,3,8))
    assert (selected.end_utc-selected.start_utc).total_seconds()==23*3600

def test_custom_range_is_half_open_and_late_event_groups_locally():
    selected=report_range("UTC","custom",date(2026,7,1),date(2026,7,31))
    assert selected.start_utc.isoformat()=="2026-07-01T00:00:00+00:00"
    assert selected.end_utc.isoformat()=="2026-08-01T00:00:00+00:00"
    assert local_day("2026-07-31T19:00:00+00:00","Asia/Kolkata")=="2026-08-01"

def test_invalid_timezone_is_rejected():
    with pytest.raises(Exception) as error: report_range("PST","today")
    assert getattr(error.value,"status_code",None)==422

def test_production_email_preview_is_forbidden():
    with pytest.raises(ValidationError):
        load_settings({"SUPABASE_URL":"https://example.supabase.co","SUPABASE_SERVICE_KEY":"x"*20,"JWT_SECRET":"x"*40,
          "API_KEY_ENCRYPTION_KEY":"MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=","CORS_ALLOWED_ORIGINS":"https://example.com",
          "EMAIL_PREVIEW_ENABLED":"true","SENTRY_ENVIRONMENT":"production"})

def test_alert_job_and_billing_are_server_authoritative():
    operations=Path("routers/operations.py").read_text(encoding="utf-8")
    alerts=Path("services/alerts.py").read_text(encoding="utf-8")
    billing=Path("services/billing.py").read_text(encoding="utf-8")
    assert "compare_digest" in operations and "cron_secret" in operations
    assert "deduplication_key" in alerts and "next_retry_at" in alerts
    assert "Webhook.construct_event" in billing and "checkout.session.completed" in billing

def test_stripe_fixture_rejects_environment_mismatch(monkeypatch):
    provider=StripeProvider.__new__(StripeProvider)
    provider.settings=SimpleNamespace(stripe_webhook_secret="whsec_test",stripe_environment="test")
    monkeypatch.setattr("services.billing.stripe.Webhook.construct_event",lambda *_args,**_kwargs:{"id":"evt_1","livemode":True})
    with pytest.raises(HTTPException) as error: provider.verify_webhook(b"{}","signature")
    assert error.value.status_code==400

def test_stripe_fixture_accepts_matching_signed_event(monkeypatch):
    provider=StripeProvider.__new__(StripeProvider)
    provider.settings=SimpleNamespace(stripe_webhook_secret="whsec_test",stripe_environment="test")
    event={"id":"evt_1","type":"invoice.paid","livemode":False,"data":{"object":{}}}
    monkeypatch.setattr("services.billing.stripe.Webhook.construct_event",lambda *_args,**_kwargs:event)
    assert provider.verify_webhook(b"{}","signature")["id"]=="evt_1"

def test_resend_provider_is_used_without_exposing_recipient(monkeypatch):
    sent=[]
    fake=SimpleNamespace(api_key=None,Emails=SimpleNamespace(send=lambda payload: sent.append(payload) or {"id":"email_1"}))
    monkeypatch.setitem(sys.modules,"resend",fake)
    monkeypatch.setattr("utils.email.get_settings",lambda:SimpleNamespace(resend_api_key="re_test",smtp_from_email="TokenWatch <test@example.com>",smtp_host="",smtp_username="",smtp_password="",smtp_port=465))
    assert send_alert_email("Subject","<p>Safe</p>","receiver@example.com") is True
    assert sent[0]["to"]==["receiver@example.com"]
