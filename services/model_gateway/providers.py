"""
providers.py
============
This file is the ONLY place in the entire codebase that reads the actual
API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY). Every other file — including
main.py — just calls these two functions and gets back a ready-to-use client.

Why isolate this in its own file:
- If we ever add a third provider (e.g., a local open-source model), we only
  touch this one file.
- Makes it obvious, during a code review or audit, exactly where secrets
  are consumed.
"""

import os
from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

def get_anthropic_client(model_name: str):
    """
    Builds an Anthropic chat client for the given model name.
    Reads ANTHROPIC_API_KEY from the environment — today that's populated
    from the .env file (via Docker Compose's env_file: .env). In the EKS
    phase, this same os.environ read will instead be populated by AWS
    Secrets Manager + External Secrets Operator, injected into the pod —
    this function itself won't need to change at all.
    """

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # Fail loudly and early rather than letting a request silently
        # hit Anthropic with no key and get a confusing 401 later.
        raise RuntimeError("ANTHROPIC_API_KEY is not set in the environment")

    return ChatAnthropic(
        model=model_name,
        api_key=api_key,
    )

def get_openai_client(model_name: str):
    """
    Same idea as get_anthropic_client, but for OpenAI models.
    Kept as a separate function (not one generic "get_client") so each
    provider's specific client class and any provider-specific config
    (timeouts, retries, etc.) stay easy to adjust independently later.
    """

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set in the environment")

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
    )