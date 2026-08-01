from pathlib import Path

import pytest
from pydantic import ValidationError

from main import app
from schemas.requests import AlertCreate, BudgetPolicyCreate, OnboardingUpdate


def test_phase3_routes_are_discoverable():
    paths = {route.path for route in app.routes}
    assert {"/onboarding/{organization_id}", "/onboarding/{organization_id}/test-event", "/usage/events", "/usage/aggregate"} <= paths


def test_onboarding_progress_validation():
    value = OnboardingUpdate(current_step=4, completed_steps=[3, 1, 3], integration_type="python", provider="openai")
    assert value.completed_steps == [1, 3]
    with pytest.raises(ValidationError):
        OnboardingUpdate(current_step=12, completed_steps=[])


def test_budget_scope_and_threshold_validation():
    with pytest.raises(ValidationError):
        BudgetPolicyCreate(scope_type="provider", period_type="monthly", amount=10)
    with pytest.raises(ValidationError):
        BudgetPolicyCreate(scope_type="organization", period_type="monthly", amount=10, warning_threshold_percent=101)


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
