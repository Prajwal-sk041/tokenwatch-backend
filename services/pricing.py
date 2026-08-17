from datetime import date
from decimal import Decimal


# USD per million tokens. Unknown models are rejected so cost is never client-controlled.
MODEL_PRICING: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("openai", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("openai", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("anthropic", "claude-3-5-sonnet"): (Decimal("3.00"), Decimal("15.00")),
    ("anthropic", "claude-sonnet-5"): (Decimal("2.00"), Decimal("10.00")),
    ("gemini", "gemini-1.5-flash"): (Decimal("0.075"), Decimal("0.30")),
    ("gemini", "gemini-3.5-flash"): (Decimal("1.50"), Decimal("9.00")),
    ("groq", "llama-3.1-70b-versatile"): (Decimal("0.59"), Decimal("0.79")),
    ("groq", "llama-3.3-70b-versatile"): (Decimal("0.59"), Decimal("0.79")),
    ("openrouter", "openai/gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("azure_openai", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("aws_bedrock", "anthropic.claude-3-5-sonnet"): (Decimal("3.00"), Decimal("15.00")),
}

PRICING_EFFECTIVE_DATE = date(2026, 8, 18)
PRICING_CURRENCY = "USD"
PRICING_UNIT = "per_1m_tokens"
PRICING_SOURCES = {
    "openai": "https://developers.openai.com/api/docs/models/gpt-4o",
    "anthropic": "https://www.anthropic.com/claude/sonnet",
    "gemini": "https://ai.google.dev/gemini-api/docs/pricing",
    "groq": "https://groq.com/pricing",
}


def pricing_catalog() -> dict:
    """Return the exact server-side catalog used for usage and policy costs."""
    models = [
        {
            "provider": provider,
            "model": model,
            "input_per_1m_tokens": str(rates[0]),
            "output_per_1m_tokens": str(rates[1]),
            "source_url": PRICING_SOURCES.get(provider),
        }
        for (provider, model), rates in sorted(MODEL_PRICING.items())
    ]
    return {
        "currency": PRICING_CURRENCY,
        "unit": PRICING_UNIT,
        "effective_date": PRICING_EFFECTIVE_DATE.isoformat(),
        "models": models,
        "notice": "TokenWatch uses this versioned catalog for estimates. Provider invoices remain authoritative.",
    }


def calculate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    rates = MODEL_PRICING.get((provider, model))
    if not rates:
        raise ValueError("Unsupported provider/model pricing combination")
    return ((Decimal(prompt_tokens) * rates[0]) + (Decimal(completion_tokens) * rates[1])) / Decimal(1_000_000)
