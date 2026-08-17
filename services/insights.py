from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import datetime, timezone
from typing import Any


def build_cost_insights(
    logs: list[dict[str, Any]],
    policy_events: list[dict[str, Any]] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Turn trusted usage records into explainable financial insights.

    Recommendations are based only on the customer's observed unit costs. They
    are deliberately labelled as opportunities because model quality is not
    interchangeable and TokenWatch must not promise unverified savings.
    """
    current = now or datetime.now(timezone.utc)
    month_start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_logs = [row for row in logs if _timestamp(row) >= month_start]
    total_cost = sum(float(row.get("calculated_cost") or 0) for row in month_logs)
    days_elapsed = max(1, current.day)
    projection = total_cost / days_elapsed * _days_in_month(current)

    by_provider: dict[str, float] = defaultdict(float)
    by_model: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"cost": 0.0, "tokens": 0.0, "requests": 0.0}
    )
    daily: dict[str, float] = defaultdict(float)
    for row in month_logs:
        cost = float(row.get("calculated_cost") or 0)
        provider = str(row.get("provider") or "unknown")
        model = str(row.get("model") or "unknown")
        tokens = float(row.get("total_tokens") or 0)
        by_provider[provider] += cost
        bucket = by_model[(provider, model)]
        bucket["cost"] += cost
        bucket["tokens"] += tokens
        bucket["requests"] += 1
        daily[_timestamp(row).date().isoformat()] += cost

    recommendations: list[dict[str, Any]] = []
    potential_savings = 0.0
    for provider in sorted(by_provider):
        candidates = []
        for (candidate_provider, model), values in by_model.items():
            if candidate_provider == provider and values["tokens"] > 0:
                candidates.append((model, values, values["cost"] / values["tokens"]))
        if len(candidates) < 2:
            continue
        cheapest_model, _, cheapest_rate = min(candidates, key=lambda item: item[2])
        for model, values, rate in candidates:
            if model == cheapest_model or rate <= cheapest_rate * 1.2:
                continue
            opportunity = max(0.0, values["cost"] - values["tokens"] * cheapest_rate)
            if opportunity < 0.01:
                continue
            potential_savings += opportunity
            recommendations.append({
                "type": "model_cost_review",
                "provider": provider,
                "model": model,
                "alternative": cheapest_model,
                "estimated_monthly_opportunity": round(opportunity, 2),
                "message": f"Review {model} workloads against {cheapest_model}; quality must be validated before switching.",
            })

    policy_events = policy_events or []
    prevented = sum(float((event.get("metadata") or {}).get("estimated_cost") or 0) for event in policy_events)
    blocked = len(policy_events)
    latest_day = current.date().isoformat()
    previous_values = [value for day, value in daily.items() if day != latest_day]
    baseline = sum(previous_values) / len(previous_values) if previous_values else 0.0
    today_cost = daily.get(latest_day, 0.0)
    anomaly_ratio = today_cost / baseline if baseline > 0 else None
    risk = "high" if anomaly_ratio and anomaly_ratio >= 2 else "watch" if anomaly_ratio and anomaly_ratio >= 1.5 else "normal"
    top_provider = max(by_provider.items(), key=lambda item: item[1], default=(None, 0.0))

    return {
        "month": {
            "actual_cost": round(total_cost, 8),
            "projected_cost": round(projection, 8),
            "days_elapsed": days_elapsed,
        },
        "risk": {
            "level": risk,
            "today_cost": round(today_cost, 8),
            "daily_baseline": round(baseline, 8),
            "anomaly_ratio": round(anomaly_ratio, 2) if anomaly_ratio is not None else None,
            "top_provider": top_provider[0],
            "top_provider_share": round(top_provider[1] / total_cost * 100, 1) if total_cost else 0,
        },
        "value": {
            "blocked_requests": blocked,
            "estimated_spend_prevented": round(prevented, 8),
            "estimated_optimization_opportunity": round(potential_savings, 2),
        },
        "recommendations": sorted(
            recommendations, key=lambda item: item["estimated_monthly_opportunity"], reverse=True
        )[:5],
        "methodology": "Forecast uses current-month daily pace. Optimization opportunities compare observed cost per token within the same provider and require quality validation.",
    }


def _timestamp(row: dict[str, Any]) -> datetime:
    raw = str(row.get("request_timestamp") or row.get("created_at"))
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _days_in_month(value: datetime) -> int:
    return monthrange(value.year, value.month)[1]
