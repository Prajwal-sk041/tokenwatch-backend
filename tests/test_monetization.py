from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.billing import _money, _timestamp
from services.entitlements import EntitlementService


class CountQuery:
    def __init__(self, count): self.count = count
    def table(self, _): return self
    def select(self, *_args, **_kwargs): return self
    def eq(self, *_args): return self
    def is_(self, *_args): return self
    def execute(self): return SimpleNamespace(data=[], count=self.count)


def test_money_conversion_never_trusts_browser_amounts():
    assert _money(4999) == 49.99
    assert _money(None) == 0


def test_stripe_timestamp_is_utc():
    assert _timestamp(0) is None
    assert _timestamp(1_700_000_000).endswith("+00:00")


def test_entitlement_count_blocks_at_limit(monkeypatch):
    service = EntitlementService()
    monkeypatch.setattr(service, "limit", lambda _org, _feature: 5)
    monkeypatch.setattr("services.entitlements.get_db", lambda: CountQuery(5))
    with pytest.raises(HTTPException) as error:
        service.enforce_count("org", "provider_keys", "api_keys", key_type="provider")
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "plan_limit_reached"


def test_unlimited_entitlement_skips_database(monkeypatch):
    service = EntitlementService()
    monkeypatch.setattr(service, "limit", lambda _org, _feature: -1)
    service.enforce_count("org", "alerts", "alert_rules")


def test_phase4_migration_has_idempotent_events_and_rls():
    sql = open("migrations/202608010004_phase4_monetization.sql", encoding="utf-8").read()
    assert "unique(provider, provider_event_id)" in sql
    assert "alter table public.%I enable row level security" in sql
    assert "billing_events_status_idx" in sql
