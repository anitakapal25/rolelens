"""USD prices per million tokens, used to log an estimated cost for every call.

Anthropic first-party API rates as of 2026-10; OpenAI embedding rate as published.
Update here when prices change; unknown models are logged with cost 0.
"""

from app.models import Usage

PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    # model: (input, output)
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-opus-5-5": (4.00, 20.00),
    "text-embedding-3-small": (0.02, 0.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


def make_usage(model: str, input_tokens: int, output_tokens: int) -> Usage:
    return Usage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=estimate_cost(model, input_tokens, output_tokens),
    )
