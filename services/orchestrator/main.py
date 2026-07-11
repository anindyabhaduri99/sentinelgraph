"""
main.py
=======
FastAPI entrypoint for the orchestrator service. Exposes POST /chat, which
runs the compiled LangGraph (planner -> retriever -> analyst -> evaluator
-> optionally optimizer/retry -> finalize) and returns the final response.
The compiled_graph object is built once at import time (see graph.py) and
reused across every request.
"""

from fastapi import FastAPI, Depends, Header
from pydantic import BaseModel
from graph import compiled_graph
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from fastapi import Depends
from auth import verify_access_token

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
    confidence_score: float
    retry_count: int
    escalated_to_human: bool

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, authorization: str = Header(None), token_payload: dict = Depends(verify_access_token)):
    
    raw_token = authorization.removeprefix("Bearer ").strip()
    
    initial_state = {
        "user_message": req.user_message,
        "access_token": raw_token,
        "plan": None,
        "retrieved_context": None,
        "draft_response": None,
        "confidence_score": None,
        "retry_count": 0,
        "final_response": None,
        "escalated_to_human": False,
    }

    result = await compiled_graph.ainvoke(initial_state)

    return ChatResponse(
        final_response=result["final_response"],
        confidence_score=result["confidence_score"],
        retry_count=result["retry_count"],
        escalated_to_human=result["escalated_to_human"],
    )

@app.get("/health")
async def health():
    return {"status": "ok"}