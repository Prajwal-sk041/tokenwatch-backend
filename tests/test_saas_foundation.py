from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from dependencies import require_sdk_permission, SdkPrincipal
from services import audit
from services.budget import evaluate_budget
from services.pricing import calculate_cost
from services.security import hash_secret
from services.tenant import ROLE_RANK, require_membership


class MembershipQuery:
    def __init__(self, rows): self.rows = rows
    def table(self, _name): return self
    def select(self, *_args): return self
    def eq(self, *_args): return self
    def is_(self, *_args): return self
    def limit(self, *_args): return self
    def execute(self): return SimpleNamespace(data=self.rows)


def test_tenant_isolation_rejects_non_member(monkeypatch):
    monkeypatch.setattr("services.tenant.get_db", lambda: MembershipQuery([]))
    with pytest.raises(HTTPException) as error:
        require_membership("user-a", "org-b")
    assert error.value.status_code == 403


def test_organization_permissions_are_ordered():
    assert ROLE_RANK["owner"] > ROLE_RANK["admin"] > ROLE_RANK["member"] > ROLE_RANK["viewer"]


def test_viewer_cannot_satisfy_admin_permission(monkeypatch):
    monkeypatch.setattr("services.tenant.get_db", lambda: MembershipQuery([{"role": "viewer", "status": "active"}]))
    with pytest.raises(HTTPException):
        require_membership("user-a", "org-a", "admin")


def test_budget_engine_allows_warns_and_blocks():
    assert evaluate_budget(Decimal("10"), Decimal("5"), Decimal("100")).action == "allow"
    assert evaluate_budget(Decimal("79"), Decimal("2"), Decimal("100")).action == "warn"
    decision = evaluate_budget(Decimal("99"), Decimal("2"), Decimal("100"))
    assert decision.blocked and not decision.allowed


def test_sdk_authentication_hash_is_deterministic_and_permission_scoped():
    assert hash_secret("tw_live_secret") == hash_secret("tw_live_secret")
    assert hash_secret("tw_live_secret") != "tw_live_secret"
    principal = SdkPrincipal("key-1", "org-1", ("usage:write",))
    require_sdk_permission(principal, "usage:write")
    with pytest.raises(HTTPException):
        require_sdk_permission(principal, "policy:check")


def test_cost_is_calculated_server_side():
    assert calculate_cost("openai", "gpt-4o-mini", 1_000_000, 0) == Decimal("0.15")
    with pytest.raises(ValueError):
        calculate_cost("openai", "unpriced-model", 1, 1)


def test_audit_log_records_required_action(monkeypatch):
    captured = {}
    class FakeRepository:
        def __init__(self, table): assert table == "audit_logs"
        def insert(self, values): captured.update(values)
    monkeypatch.setattr(audit, "Repository", FakeRepository)
    audit.record_audit("organization.invite_created", organization_id="org-1", actor_user_id="user-1")
    assert captured["action"] == "organization.invite_created"
    assert captured["organization_id"] == "org-1"
