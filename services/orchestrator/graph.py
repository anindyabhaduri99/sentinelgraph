"""
graph.py
========
Defines the LangGraph StateGraph: registers each node function, wires the
edges between them, and defines the conditional edge that decides whether
to retry (via the optimizer) or move to finalize. Uses the same
CONFIDENCE_THRESHOLD and MAX_RETRIES from config.py that finalize_node
uses, so there is a single source of truth for both values.
"""

from langgraph.graph import StateGraph, END
from state import AgentState
from config import CONFIDENCE_THRESHOLD, MAX_RETRIES
from nodes import (
    intent_classifier_node,
    filter_tools_node,
    planner_node,
    retriever_node,
    analyst_node,
    evaluator_node,
    optimizer_node,
    finalize_node,
)

def should_retry_or_finalize(state: AgentState) -> str:
    if state['confidence_score'] >= CONFIDENCE_THRESHOLD:
        return "finalize"
    if state['retry_count'] >= MAX_RETRIES:
        return "finalize"
    return "retry"

def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("intent_classifier", intent_classifier_node)
    graph.add_node("filter_tools", filter_tools_node)
    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("evaluator", evaluator_node)
    graph.add_node("optimizer", optimizer_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("filter_tools")
    graph.add_edge("filter_tools", "intent_classifier")
    def should_continue_after_intent(state: AgentState) -> str:
        if state["intent"] == "out_of_scope":
            return "finalize"
        return "planner"

    graph.add_conditional_edges(
        "intent_classifier",
        should_continue_after_intent,
        {
            "planner": "planner",
            "finalize": "finalize",
        },
    )
    graph.add_edge("planner", "retriever")

    def should_continue_after_retrieval(state: AgentState) -> str:
        if state["access_denied"]:
            return "finalize"
        return "analyst"

    graph.add_conditional_edges(
        "retriever",
        should_continue_after_retrieval,
        {
            "analyst": "analyst",
            "finalize": "finalize",
        },
    )
    graph.add_edge("analyst", "evaluator")

    graph.add_conditional_edges(
        "evaluator",
        should_retry_or_finalize,
        {
            "retry": "optimizer",
            "finalize": "finalize",
        },
    )
    graph.add_edge("optimizer", "analyst")
    graph.add_edge("finalize", END)

    return graph.compile()

compiled_graph = build_graph()