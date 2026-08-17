from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from main import app
from schemas.requests import AlertCreate, BudgetPolicyCreate, OnboardingUpdate, PasswordChangeRequest, PasswordResetConfirm, RegisterRequest


def test_phase3_routes_are_discoverable():
    paths = {route.path for route in app.routes}
    assert {"/onboarding/{organization_id}", "/onboarding/{organization_id}/test-event", "/usage/events", "/usage/aggregate"} <= paths


def test_onboarding_progress_validation():
    value = OnboardingUpdate(current_step=4, completed_steps=[3, 1, 3], integration_type="python", provider="openai")
    assert value.completed_steps == [1, 3]
    with pytest.raises(ValidationError):
        OnboardingUpdate(current_step=12, completed_steps=[])
    assert OnboardingUpdate(current_step=4, integration_type="powershell").integration_type == "powershell"


def test_budget_scope_and_threshold_validation():
    with pytest.raises(ValidationError):
        BudgetPolicyCreate(scope_type="provider", period_type="monthly", amount=10)
    with pytest.raises(ValidationError):
        BudgetPolicyCreate(scope_type="organization", period_type="monthly", amount=10, warning_threshold_percent=101)
    with pytest.raises(ValidationError):
        BudgetPolicyCreate(scope_type="organization", period_type="monthly", amount=10, warning_threshold_percent=90, hard_stop_threshold_percent=80)
    with pytest.raises(ValidationError):
        BudgetPolicyCreate(scope_type="organization", period_type="monthly", amount=0)


def test_alert_webhook_requires_https_and_stubs_validate():
    with pytest.raises(ValidationError):
        AlertCreate(alert_type="cost", threshold=5, channel="webhook", destination="http://unsafe.example")
    assert AlertCreate(alert_type="cost", threshold=5, channel="slack").channel == "slack"


def test_paid_plan_self_service_is_explicitly_blocked():
    source = Path("routers/subscriptions.py").read_text(encoding="utf-8")
    assert "trusted billing service" in source
    assert "status_code=403" in source


def test_migration_tracks_real_event_and_budget_references():
    source = Path("migrations/202608010003_phase3_product_experience.sql").read_text(encoding="utf-8")
    assert "test_usage_log_id uuid references public.usage_logs" in source
    assert "first_budget_id uuid references public.budget_policies" in source


def test_onboarding_cost_is_json_safe_and_database_clients_are_thread_scoped():
    onboarding = Path("routers/onboarding.py").read_text(encoding="utf-8")
    database = Path("utils/database.py").read_text(encoding="utf-8")
    assert "cost = calculate_cost(" in onboarding
    assert '"calculated_cost": str(cost)' in onboarding
    assert "threading.local()" in database
    assert "@lru_cache" not in database


@pytest.mark.parametrize("password", ["Ab1!x", "Longer9$password"])
def test_password_policy_accepts_requested_shape(password):
    assert RegisterRequest(email="user@example.com", password=password).password == password
    assert PasswordResetConfirm(token="x" * 32, new_password=password).new_password == password
    assert PasswordChangeRequest(current_password="old", new_password=password).new_password == password


@pytest.mark.parametrize("password", ["A1!", "abc1!", "Abcd!", "Abcd1"])
def test_password_policy_rejects_missing_requirement(password):
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password=password)


def test_account_management_routes_are_discoverable():
    paths = {route.path for route in app.routes}
    assert {"/auth/me", "/auth/change-password"} <= paths


def test_public_support_requires_contact_email(monkeypatch):
    from fastapi import HTTPException
    from routers import operations
    from schemas.requests import SupportTicketCreate

    monkeypatch.setattr(operations, "consume", lambda *_args, **_kwargs: None)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})
    payload = SupportTicketCreate(category="feedback", subject="Useful idea", message="A detailed feedback message")
    with pytest.raises(HTTPException) as error:
        operations.contact(payload, request, None)
    assert error.value.status_code == 422
