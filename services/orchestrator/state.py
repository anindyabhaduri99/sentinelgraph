from typing import TypedDict, Optional
from pydantic import BaseModel

class AgentState(TypedDict):
    user_message: str
    access_token: str
    role: str
    available_tools: list
    intent: str
    plan: Optional[str]
    retrieved_context: Optional[str]
    access_denied: bool
    draft_response: Optional[str]
    confidence_score: Optional[float]
    retry_count: int
    final_response: Optional[str]
    escalated_to_human: bool

class ToolCall(BaseModel):
    tool_name: str
    parameters: dict

class ToolPlan(BaseModel):
    tool_calls: list[ToolCall]



