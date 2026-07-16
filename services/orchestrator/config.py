"""
config.py
=========
Centralizes tunable thresholds so they're not hardcoded inline in graph.py
or nodes.py. Both can be overridden via environment variables without a
code change — e.g., raising CONFIDENCE_THRESHOLD in a stricter compliance
environment, or increasing MAX_RETRIES if false-negative evaluations are
common for a particular query type.
"""

import os
from repository import get_ticket, get_portfolio
from external_apis_client import get_client_contact

TOOL_DISPATCH = {
    "get_ticket": get_ticket,
    "get_portfolio": get_portfolio,
    "get_client_contact": get_client_contact,
}

CONFIDENCE_THRESHOLD = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.9"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))