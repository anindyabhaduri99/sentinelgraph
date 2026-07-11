"""
main.py
=======
FastAPI entrypoint for the orchestrator service. Exposes POST /chat, which
runs the compiled LangGraph (planner -> retriever -> analyst -> evaluator
-> optionally optimizer/retry -> finalize) and returns the final response.
The compiled_graph object is built once at import time (see graph.py) and
reused across every request.
"""

from fastapi import FastAPI, Depends, Header, HTTPException, Depends
from pydantic import BaseModel
from graph import compiled_graph
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from typing import Optional

from auth import verify_access_token
from dal.entitlements import enforce_entitlement, AccessDeniedError
from registry import register_tool, list_tools
from approvals import list_pending_approvals, decide_approval

app = FastAPI(title="SentinelGraph Orchestrator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

class ChatRequest(BaseModel):
    user_message: str

class ChatResponse(BaseModel):
    final_response: str
    confidence_score: Optional[float] = None
    retry_count: int
    escalated_to_human: bool

class RegisterToolRequest(BaseModel):
    tool_name: str
    description: str
    input_schema: dict
    resource: str
    owning_domain: str

class DecisionRequest(BaseModel):
    decision: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, authorization: str = Header(None), token_payload: dict = Depends(verify_access_token)):

    raw_token = authorization.removeprefix("Bearer ").strip()
    
    initial_state = {
        "user_message": req.user_message,
        "access_token": raw_token,
        "role": token_payload["role"],
        "plan": None,
        "retrieved_context": None,
        "access_denied": False,
        "draft_response": None,
        "confidence_score": None,
        "retry_count": 0,
        "final_response": None,
        "escalated_to_human": False,
        "available_tools": [],
    }

    result = await compiled_graph.ainvoke(initial_state)

    print(f"DEBUG final result from graph: {result}", flush=True)

    return ChatResponse(
        final_response=result["final_response"],
        confidence_score=result["confidence_score"],
        retry_count=result["retry_count"],
        escalated_to_human=result["escalated_to_human"],
    )
    

@app.post("/tools/register")
async def register_tool_endpoint(req: RegisterToolRequest, token_payload: dict = Depends(verify_access_token)):
    try:
        enforce_entitlement(token_payload["role"], resource="tool_registry", action="write")
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return register_tool(
        tool_name=req.tool_name,
        description=req.description,
        input_schema=req.input_schema,
        resource=req.resource,
        owning_domain=req.owning_domain,
    )

@app.get("/tools")
async def get_tools_endpoint():
    return list_tools()

from approvals import list_pending_approvals, decide_approval

class DecisionRequest(BaseModel):
    decision: str

@app.get("/approvals")
async def get_approvals(token_payload: dict = Depends(verify_access_token)):
    try:
        enforce_entitlement(token_payload["role"], resource="approval_queue", action="read")
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return list_pending_approvals()

@app.post("/approvals/{approval_id}/decide")
async def decide_approval_endpoint(approval_id: int, req: DecisionRequest, token_payload: dict = Depends(verify_access_token)):
    try:
        enforce_entitlement(token_payload["role"], resource="approval_queue", action="write")
    except AccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return decide_approval(approval_id, req.decision, token_payload["sub"])

@app.get("/health")
async def health():
    return {"status": "ok"}