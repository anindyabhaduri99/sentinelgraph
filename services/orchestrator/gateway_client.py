"""
gateway_client.py
=================
Async HTTP client for calling the model-gateway service. Every node that
needs an LLM call awaits this function instead of blocking synchronously —
lets the orchestrator handle multiple concurrent user requests without
one slow LLM call stalling every other in-flight request.
"""

import os
import httpx

MODEL_GATEWAY_URL = os.environ.get("MODEL_GATEWAY_URL", "http://model-gateway:8080")

async def call_model(role: str, system_prompt: str, user_message: str) -> str:
    """
    Async POST to the model gateway's /invoke endpoint. Returns just the
    text content. Raises on non-2xx response so the calling node can
    decide how to handle failure (retry, escalate, etc.).
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{MODEL_GATEWAY_URL}/invoke",
            json={
                "role" : role,
                "system_prompt" : system_prompt,
                "user_message" : user_message,
            },
        )

        response.raise_for_status()
        return response.json()["content"]