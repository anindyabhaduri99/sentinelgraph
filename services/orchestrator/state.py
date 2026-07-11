from typing import TypedDict, Optional

class AgentState(TypedDict):
    user_message: str
    access_token: str
    plan: Optional[str]
    retrieved_context: Optional[str]
    draft_response: Optional[str]
    confidence_score: Optional[float]
    retry_count: int
    final_response: Optional[str]
    escalated_to_human: bool