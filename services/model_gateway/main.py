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

class InvokeRequest(BaseModel):
    role: str            # which agent role is calling: "planner", "analyst", "evaluator", etc.
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

@app.post("/invoke", response_model=InvokeResponse)
def invoke(req: InvokeRequest):
    # Step 1: look up which provider/model this role maps to.
    # This is the "Bedrock-style" central routing decision — defined in
    # router.py, not hardcoded here, so changing the mapping is a one-line
    # edit in one file, not a hunt through every agent's code.

    try:
        config=resolve_model(req.role)
    except ValueError as e:
        # Unknown role name was passed in -> return a clean 400 error
        # instead of crashing.
        raise HTTPException(status_code=400, detail=str(e))

    # Step 2: get the actual LangChain client for that provider/model.
    # get_anthropic_client / get_openai_client (in providers.py) are the
    # ONLY two functions in this whole codebase that read the API keys.

    if config["provider"]=="anthropic":
        client=get_anthropic_client(config["model"])
    elif config["provider"] == "openai":
        client = get_openai_client(config["model"])
    else:
        # Defensive check — should never happen if router.py is correct,
        # but fail loudly if it does.
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {config['provider']}")
 
    # Step 3: build the message list in the format LangChain chat models
    # expect — a list of (role, content) tuples.

    messages=[
        ("system", req.system_prompt),
        ("human", req.user_message),
    ]

    # Step 4: actually call the model. This is the one real network call
    # to Anthropic/OpenAI in the entire system.

    result=client.invoke(messages)

    # Step 5: return a structured response so callers (and later, our
    # audit-trail logger) know exactly which provider/model produced
    # this output — important for debugging and for the audit trail
    # we'll build in a later phase.

    return InvokeResponse(
        role=req.role,
        provider=config["provider"],
        model=config["model"],
        content=result.content,
    )
