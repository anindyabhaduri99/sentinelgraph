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

import sys
import os
from itertools import combinations_with_replacement
from state import AgentState

sys.path.append(os.path.join(os.path.dirname(__file__), "shared", "prompts"))

from dal.entitlements import AccessDeniedError, check_entitlement
from registry import list_tools
from gateway_client import call_model
from repository import get_ticket, get_portfolio
from loader import load_prompt

def _wrap(content) -> str:
    """Wraps any interpolated content in the untrusted_input tag boundary."""
    return f"<untrusted_input>{content}</untrusted_input>"

async def intent_classifier_node(state: AgentState) -> dict:
    system_prompt = load_prompt("intent_classifier")

    raw_intent = await call_model(
        role="intent_classifier",
        system_prompt=system_prompt,
        user_message=_wrap(state["user_message"]),
        access_token=state["access_token"],
    )

    cleaned_intent = raw_intent.strip().lower()

    valid_intents = ["read_only", "write_action", "mixed"]
    if cleaned_intent not in valid_intents:
        cleaned_intent = "mixed"

    print(f"DEBUG intent_classifier_node: user_message={state['user_message']}, intent={cleaned_intent}", flush=True)
    return {"intent": cleaned_intent}

async def filter_tools_node(state: AgentState) -> dict:
    """
    Runs BEFORE the planner. Queries the full tool registry, keeps only
    tools whose resource this role is entitled to read, and stores that
    filtered list in state for the planner to eventually consume. Every
    call is a fresh check — no caching of entitlements across turns.
    """
    all_tools = list_tools()
    role = state["role"]

    filtered = []
    for tool in all_tools:
        if check_entitlement(role, resource=tool["resource"], action="read"):
            filtered.append(tool)

    return {"available_tools": filtered}

# -----------------------------------------------------------------------
# PLANNER NODE
# -----------------------------------------------------------------------

async def planner_node(state: AgentState) -> dict:
   
    system_prompt = load_prompt("planner")
    plan = await call_model(
        role="planner",
        system_prompt=system_prompt,
        user_message=_wrap(state["user_message"]),
        access_token=state["access_token"],
    )

    return {"plan": plan}

# -----------------------------------------------------------------------
# RETRIEVER NODE
# Still hardcoded to a fixed ticket_id/client_id — plan is not yet parsed
# or acted on. See memory: real fix is Phase 6a/6b (registry + filtering
# node) plus structured-output planning.
# -----------------------------------------------------------------------
async def retriever_node(state: AgentState) -> dict:
    try:
        ticket = get_ticket("TCK-1001", role=state["role"])
        portfolio = get_portfolio("CLIENT-88213", role=state["role"])
    except AccessDeniedError as e:
        return {"retrieved_context": f"Access denied: {e}",
        "access_denied": True,
        }

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
        access_token=state["access_token"],
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
        access_token=state["access_token"],
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
        access_token=state["access_token"],
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

    if state["access_denied"]:
        return {
            "final_response": (
                "Access denied: your role does not have permission to view this "
                "information. Please contact your administrator if you believe "
                "this is incorrect."
            ),
            "escalated_to_human": False,
        }

    if state["intent"] in ["write_action", "mixed"]:
        from approvals import create_pending_approval
        create_pending_approval(
            user_id=state["role"],
            role=state["role"],
            original_request=state["user_message"],
            draft_response=state["draft_response"] or "",
            action_type=state["intent"],
        )
        return {
            "final_response": (
                "A draft response has been prepared based on your request, but "
                "because this involves a write action, it requires human approval "
                "before anything is executed. It has been added to the approval queue."
            ),
            "escalated_to_human": True,
        }

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

    return {
        "final_response": (
            "This request could not be confidently resolved and has been "
            "escalated to the human-in-the-loop queue."
        ),
        "escalated_to_human": True,
    }