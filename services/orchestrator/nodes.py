"""
nodes.py
========
Each function here is one "node" in the LangGraph. A node receives the
current AgentState, does its job, and returns a dict of fields to merge
into the state. All LLM calls go through call_model() (async, HTTP call
to the model-gateway). System prompts are loaded from shared/prompts/*.yml
via load_prompt() — never hardcoded here. Any content originating from the
user, retrieval, or a prior agent step is wrapped in <untrusted_input>
tags before being interpolated into a prompt, per the injection defense
convention defined in _injection_defense_block.yml.
"""

from itertools import combinations_with_replacement
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "shared", "prompts"))

from state import AgentState
from gateway_client import call_model
from repository import get_ticket, get_portfolio
from loader import load_prompt

def _wrap(content) -> str:
    """Wraps any interpolated content in the untrusted_input tag boundary."""
    return f"<untrusted_input>{content}</untrusted_input>"

# -----------------------------------------------------------------------
# PLANNER NODE
# -----------------------------------------------------------------------

async def planner_node(state: AgentState) -> dict:
    system_prompt = load_prompt("planner")
    plan = await call_model(
        role="planner",
        system_prompt=system_prompt,
        user_message=_wrap(state["user_message"]),
    )

    return {"plan": plan}

# -----------------------------------------------------------------------
# RETRIEVER NODE
# Still hardcoded to a fixed ticket_id/client_id — plan is not yet parsed
# or acted on. See memory: real fix is Phase 6a/6b (registry + filtering
# node) plus structured-output planning.
# -----------------------------------------------------------------------
async def retriever_node(state: AgentState) -> dict:
    ticket = get_ticket("TCK-1001")
    portfolio = get_portfolio("CLIENT-88213")

    retrieved_context = (
        f"Ticket data: {ticket}\n"
        f"Portfolio data: {portfolio}"
    )

    return {"retrieved_context" : retrieved_context}

# -----------------------------------------------------------------------
# ANALYST NODE
# -----------------------------------------------------------------------
async def analyst_node(state: AgentState) -> dict:
    system_prompt = load_prompt("analyst")
    combined_input = (
        f"Original question: {_wrap(state['user_message'])}\n\n"
        f"Plan: {_wrap(state['plan'])}\n\n"
        f"Retrieved context: \n{_wrap(state['retrieved_context'])}"
    )

    draft = await call_model(
        role="analyst",
        system_prompt=system_prompt,
        user_message=combined_input,
    )

    return {"draft_response": draft}

# -----------------------------------------------------------------------
# EVALUATOR NODE
# -----------------------------------------------------------------------
async def evaluator_node(state: AgentState) -> dict:
    system_prompt = load_prompt("evaluator")
    combined_input = (
        f"Question: {_wrap(state['user_message'])}\n"
        f"Context: {_wrap(state['retrieved_context'])}"
        f"Draft Response : {_wrap(state['draft_response'])}"
    )
    raw_score = await call_model(
        role="evaluator",
        system_prompt=system_prompt,
        user_message=combined_input,
    )

    try:
        score = float(raw_score.strip())
    except ValueError:
        score = 0.0
    return {"confidence_score" : score}


# -----------------------------------------------------------------------
# OPTIMIZER NODE
# -----------------------------------------------------------------------
async def optimizer_node(state: AgentState) -> dict:
    system_prompt = load_prompt("optimizer")
    combined_input = (
        f"Question: {_wrap(state['user_message'])}\n"
        f"Context: {_wrap(state['retrieved_context'])}\n"
        f"Low-scoring draft: {_wrap(state['confidence_score'])}\n"
        f"Confidence score was: {state['confidence_score']}"
    )

    improved_instructions = await call_model(
        role="optimizer",
        system_prompt=system_prompt,
        user_message=combined_input,
    )
    return {
        "plan" : improved_instructions,
        "retry_count" : state['retry_count'] + 1,
    }

# -----------------------------------------------------------------------
# FINALIZE NODE
# Explicitly checks BOTH signals: did we pass on confidence, or did we
# exhaust retries without passing? No LLM call, stays sync.
# -----------------------------------------------------------------------
def finalize_node(state: AgentState) -> dict:
    from config import CONFIDENCE_THRESHOLD, MAX_RETRIES

    passed_on_confidence = state["confidence_score"] >= CONFIDENCE_THRESHOLD
    retries_exhausted = state["retry_count"] >= MAX_RETRIES

    if passed_on_confidence:
        return {
            "final_response": state["draft_response"],
            "escalated_to_human": False,
        }

    if retries_exhausted:
        return {
            "final_response": (
                "This request requires human review before a response can "
                "be provided. It has been escalated to the human-in-the-loop queue."
            ),
            "escalated_to_human": True,
        }

    # Defensive fallback — should not normally be reached, since the
    # conditional edge in graph.py only routes here when one of the two
    # conditions above is already true. Escalate rather than silently
    # returning an unvalidated draft.
    return {
        "final_response": (
            "This request could not be confidently resolved and has been "
            "escalated to the human-in-the-loop queue."
        ),
        "escalated_to_human": True,
    }