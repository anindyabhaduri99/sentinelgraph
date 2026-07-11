"""
cost.py
=======
Loads pricing.yml (versioned, manually-updated config) and computes the
USD cost of a single LLM call from real token counts. Provider APIs never
return a dollar figure directly — only token counts — so cost must always
be computed client-side against a maintained price table. This is the
same approach tools like LangSmith use internally.
"""

import os
import yaml

PRICING_PATH = os.path.join(os.path.dirname(__file__), "pricing.yml")


def _load_pricing() -> dict:
    with open(PRICING_PATH, "r") as f:
        return yaml.safe_load(f)


def compute_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Returns the USD cost of one call, given real token counts from the
    provider's response. Raises KeyError if the provider/model isn't in
    pricing.yml — deliberately loud, so a newly added model without a
    price entry is caught immediately rather than silently costed as $0.
    """
    pricing = _load_pricing()
    rates = pricing[provider][model]
    input_cost = (input_tokens / 1_000_000) * rates["input_per_million"]
    output_cost = (output_tokens / 1_000_000) * rates["output_per_million"]
    return round(input_cost + output_cost, 6)