from decimal import Decimal


# USD per million tokens. Unknown models are rejected so cost is never client-controlled.
MODEL_PRICING: dict[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("openai", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("openai", "gpt-4o"): (Decimal("2.50"), Decimal("10.00")),
    ("anthropic", "claude-3-5-sonnet"): (Decimal("3.00"), Decimal("15.00")),
    ("gemini", "gemini-1.5-flash"): (Decimal("0.075"), Decimal("0.30")),
    ("groq", "llama-3.1-70b-versatile"): (Decimal("0.59"), Decimal("0.79")),
    ("openrouter", "openai/gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("azure_openai", "gpt-4o-mini"): (Decimal("0.15"), Decimal("0.60")),
    ("aws_bedrock", "anthropic.claude-3-5-sonnet"): (Decimal("3.00"), Decimal("15.00")),
}


def calculate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    rates = MODEL_PRICING.get((provider, model))
    if not rates:
        raise ValueError("Unsupported provider/model pricing combination")
    return ((Decimal(prompt_tokens) * rates[0]) + (Decimal(completion_tokens) * rates[1])) / Decimal(1_000_000)
