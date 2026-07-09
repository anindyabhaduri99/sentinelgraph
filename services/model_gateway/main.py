"""
SentinelGraph Model Gateway
============================
This is the ONLY service in the whole system allowed to call Anthropic or
OpenAI directly. Every other service (orchestrator, retriever, evaluator, etc.)
sends an HTTP request to this gateway instead of importing an LLM SDK itself.

Why this exists (mimics AWS Bedrock):
- Centralizes both API keys in one place (today: .env, later: AWS Secrets Manager)
- Centralizes the "which model handles this role" decision (router.py)
- Lets us swap providers/models/versions without touching any other service's code
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from providers import get_anthropic_client, get_openai_client
from router import resolve_model

# -----------------------------------------------------------------------
# FastAPI app instance. This is what uvicorn runs (see Dockerfile CMD).
# -----------------------------------------------------------------------

app = FastAPI(title="SentinelGraph Model Gateway")

# -----------------------------------------------------------------------
# Request/Response schemas (Pydantic models).
# FastAPI uses these to auto-validate incoming JSON and auto-generate
# the /docs Swagger page. If a caller sends a malformed request (e.g.
# missing "role"), FastAPI rejects it before our code even runs.
# -----------------------------------------------------------------------

class InvoleRequest(BaseModel):
    rrole: str            # which agent role is calling: "planner", "analyst", "evaluator", etc.
    system_prompt: str   # the system prompt for that role (caller supplies it)
    user_message: str    # the actual content to send to the model

class InvokeResponse(BaseModel):
    role: str
    provider: str        # "anthropic" or "openai" — so callers/logs know what actually ran
    model: str            # exact model name used — useful for debugging/audit trail later
    content: str          # the model's text response

# -----------------------------------------------------------------------
# The single unified endpoint. Every agent node in the orchestrator will
# call: POST http://model-gateway:8080/invoke  with a JSON body matching
# InvokeRequest. Nobody outside this file ever touches ChatAnthropic or
# ChatOpenAI directly.
# -----------------------------------------------------------------------

