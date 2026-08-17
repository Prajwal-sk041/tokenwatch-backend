from datetime import datetime, timezone

from services.insights import build_cost_insights
from pathlib import Path
import re


NOW = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)


def event(day: int, model: str, tokens: int, cost: float, provider: str = "openai"):
    return {
        "request_timestamp": f"2026-08-{day:02d}T10:00:00+00:00",
        "provider": provider,
        "model": model,
        "total_tokens": tokens,
        "calculated_cost": cost,
    }


def test_insights_forecast_uses_current_month_pace():
    result = build_cost_insights([event(1, "gpt-4o-mini", 1000, 1), event(10, "gpt-4o-mini", 1000, 1)], now=NOW)
    assert result["month"]["actual_cost"] == 2
    assert result["month"]["projected_cost"] == 6.2


def test_insights_proves_blocked_spend_without_claiming_realized_savings():
    result = build_cost_insights(
        [event(1, "gpt-4o-mini", 1000, 1)],
        [{"metadata": {"estimated_cost": "0.42"}}],
        now=NOW,
    )
    assert result["value"]["blocked_requests"] == 1
    assert result["value"]["estimated_spend_prevented"] == 0.42
    assert "require quality validation" in result["methodology"]


def test_insights_recommends_only_observed_same_provider_models():
    result = build_cost_insights(
        [event(1, "expensive", 1000, 10), event(2, "cheaper", 1000, 1)],
        now=NOW,
    )
    assert result["recommendations"][0]["model"] == "expensive"
    assert result["recommendations"][0]["alternative"] == "cheaper"
    assert result["value"]["estimated_optimization_opportunity"] == 9


def test_login_replaces_older_device_sessions():
    source = (Path(__file__).parents[1] / "routers" / "auth.py").read_text()
    login_section = source.split('def login(', 1)[1].split('@router.post("/refresh")', 1)[0]
    assert 'table("auth_sessions").update({"revoked_at": now})' in login_section
    assert re.search(r'\.eq\(\s*"user_id",\s*user\["id"\]\s*\)', login_section)
