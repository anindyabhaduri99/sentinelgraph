"""
main.py
=======
FastAPI entrypoint for the orchestrator service. Exposes POST /chat, which
runs the compiled LangGraph (planner -> retriever -> analyst -> evaluator
-> optionally optimizer/retry -> finalize) and returns the final response.
The compiled_graph object is built once at import time (see graph.py) and
reused across every request.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from graph import compiled_graph

app = FastAPI(title="SentinelGraph Orchestrator")

class ChatRequest(BaseModel):
    user_message: str

class CharResponse(BaseModel):
    final_response: str
    confidence_score: float
    retry_count: int
    escalated_to_human: bool

@app.post("/chat", response_model=CharResponse)
async def chat(req: ChatRequest):
    initial_state = {
        "user_message": req.user_message,
        "plan" : None,
        "retrieved_context" : None,
        "draft_response" : None,
        "confidence_score" : None,
        "retry_count" : 0,
        "final_response" : None,
        "escalated_to_human" : False,
    }

    result = await compiled_graph.ainvoke(initial_state)

@app.get("/health")
async def gealth():
    return {"status" : "ok"}    
