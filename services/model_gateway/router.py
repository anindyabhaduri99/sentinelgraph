"""
router.py
=========
This is the central "which model handles this role" decision table —
the part that mimics Bedrock's model-routing behavior.

Why this matters: if we later want the evaluator to use a different model
(cost change, incident response, new model release), we change ONE line
here. No agent code anywhere else needs to know or care which model it's
actually talking to — it just says "role: evaluator" and the gateway
figures out the rest.
"""

# Each role maps to a specific provider + model.
# provider must be either "anthropic" or "openai" (matches providers.py).
ROLE_CONFIG = {
    "planner": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",   # lightweight — just breaks user query into a structured plan
    },
    "retriever": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",   # lightweight — decides which tools/data to call, not reasoning-heavy
    },
    "analyst": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",  # reasoning-heavy — synthesizes the final grounded answer
    },
    "evaluator": {
        "provider": "openai",           # deliberately a DIFFERENT family than analyst
        "model": "gpt-4o",              # -> decorrelated judge, catches shared blind spots
    },
    "optimizer": {
        "provider": "openai",
        "model": "gpt-4o-mini",         # lightweight — only rewrites a prompt on a failed retry
    },
}


def resolve_model(role: str) -> dict:
    """
    Looks up the provider/model config for a given role.
    Raises ValueError if the role isn't recognized — main.py catches this
    and turns it into a clean HTTP 400 instead of a crash.
    """
    if role not in ROLE_CONFIG:
        raise ValueError(f"Unknown role: '{role}'. Valid roles: {list(ROLE_CONFIG.keys())}")
    return ROLE_CONFIG[role]