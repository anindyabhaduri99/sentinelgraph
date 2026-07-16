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
import json
import asyncio
from itertools import combinations_with_replacement
from state import AgentState, ToolPlan
from pydantic import ValidationError

sys.path.append(os.path.join(os.path.dirname(__file__), "shared", "prompts"))

from dal.entitlements import AccessDeniedError, check_entitlement
from registry import list_tools
from gateway_client import call_model
from repository import get_ticket, get_portfolio
from loader import load_prompt
from config import TOOL_DISPATCH
from llama_tools import LLAMA_TOOL_REGISTRY

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

    valid_intents = ["read_only", "write_action", "mixed", "out_of_scope"]
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

    tools_description = ""
    for tool in state["available_tools"]:
        tools_description += f"- {tool['tool_name']}: {tool['description']} (schema: {tool['input_schema']})\n"

    combined_input = (
        f"Available tools:\n{tools_description}\n"
        f"User Question: {_wrap(state['user_message'])}"
    )

    raw_response = await call_model(
        role="planner",
        system_prompt=system_prompt,
        user_message=combined_input,
        access_token=state["access_token"],
    )

    cleaned_response = raw_response.strip()
    if cleaned_response.startswith("```"):
        cleaned_response = cleaned_response.split("```")[1]
        if cleaned_response.startswith("json"):
            cleaned_response = cleaned_response[4:]
        cleaned_response = cleaned_response.strip()

    try:
        parsed_json = json.loads(cleaned_response)
        tool_plan = ToolPlan(**parsed_json)
    except (json.JSONDecodeError, ValidationError) as e:
        return {"plan": {"tool_calls": [], "error": f"Planner returned invalid output: {e}"}}

    valid_tool_names = []
    for tool in state['available_tools']:
        valid_tool_names.append(tool["tool_name"])
    
    validated_calls = []
    for call in tool_plan.tool_calls:
        if call.tool_name in valid_tool_names:
            validated_calls.append({"tool_name": call.tool_name, "parameters": call.parameters})



    return {"plan": {"tool_calls": validated_calls, "error": None}}

# -----------------------------------------------------------------------
# RETRIEVER NODE
# Still hardcoded to a fixed ticket_id/client_id — plan is not yet parsed
# or acted on. See memory: real fix is Phase 6a/6b (registry + filtering
# node) plus structured-output planning.
# -----------------------------------------------------------------------
async def retriever_node(state: AgentState) -> dict:
    plan = state["plan"]

    if plan.get("error") or not plan.get("tool_calls"):
        return {"retrieved_context": f"Planning produced no valid tool calls: {plan.get('error')}", "access_denied": False}

    if not plan.get("tool_calls"):
        return {"retrieved_context": "No data retrieval was needed for this conversational message.", "access_denied": False}


    async def run_one_call(call):
        # Look up the LlamaIndex FunctionTool object (not a raw function)
        # matching this tool name.

        tool = LLAMA_TOOL_REGISTRY.get(call["tool_name"])
        if tool is None:
            return f"{call['tool_name']}: not yet implemented"

        try:
            # tool.call(...) is LlamaIndex's standard invocation method -
            # under the hood it calls the wrapped function (e.g. get_ticket)
            # with these exact keyword arguments, exactly as our own dict
            # lookup did before. The DAL's enforce_entitlement() check
            # still runs INSIDE that wrapped function, unchanged.
            result = await asyncio.to_thread(
                tool.call, role=state["role"], **call["parameters"]
            )
            return f"{call['tool_name']} result: {result}"
        except AccessDeniedError as e:
            return f"{call['tool_name']}: ACCESS_DENIED: {e}"

        # tool_function = TOOL_DISPATCH.get(call["tool_name"])
        # if tool_function is None:
        #     return f"{call['tool_name']}: not yet implemented"
        # try:
        #     result = await asyncio.to_thread(tool_function, role=state["role"], **call["parameters"])
        #     return f"{call['tool_name']} result: {result}"
        # except AccessDeniedError as e:
        #     return f"{call['tool_name']}: ACCESS_DENIED: {e}"

    tasks = []
    for call in plan["tool_calls"]:
        tasks.append(run_one_call(call))

    results = await asyncio.gather(*tasks)

    access_denied = False
    for r in results:
        if "ACCESS_DENIED" in r:
            access_denied = True

    combined_context = "\n".join(results)

    return {"retrieved_context": combined_context, "access_denied": access_denied}

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

    if state["intent"] == "out_of_scope":
        return {
            "final_response": (
                "Hello! I'm here to help with questions about your tickets, "
                "portfolio, or investment servicing account. What would you "
                "like to know?"
            ),
            "escalated_to_human": False,
        }

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