"""
llama_tools.py
==============
Wraps our existing tool functions (get_ticket, get_portfolio,
get_client_contact) as LlamaIndex FunctionTool objects.

WHY: previously, retriever_node looked up tools in a plain Python
dictionary (TOOL_DISPATCH in config.py) and called them directly. This
worked, but it was fully custom, hand-rolled dispatch logic. FunctionTool
is a standard, named abstraction from a real RAG/tool-calling framework
(LlamaIndex) for "a function, wrapped as a formally callable tool" - using
it here means our tool-invocation layer is built on a recognized
framework pattern rather than bespoke code, while everything underneath
(the DAL entitlement checks, the real Postgres/API calls) stays exactly
the same.

NOTE: none of our DAL logic, entitlement checks, or the actual
implementations of get_ticket/get_portfolio/get_client_contact change at
all here - only how the retriever finds and invokes them changes.
"""

from llama_index.core.tools import FunctionTool
from repository import get_ticket, get_portfolio
from external_apis_client import get_client_contact
from rag_search import search_documents

# Each FunctionTool wraps one of our existing functions. The "fn" is the
# real Python function LlamaIndex will actually call when this tool is
# invoked - this is still OUR code, with OUR DAL checks inside it. The
# "name" here must exactly match the tool_name our planner selects and
# the tool_name stored in identity.tool_registry, since that's how we'll
# look up the right FunctionTool object when the retriever needs to call it.

get_ticket_tool = FunctionTool.from_defaults(
    fn=get_ticket,
    name="get_ticket",
    description="Retrieves a client service ticket by its ticket ID.",
)

get_portfolio_tool = FunctionTool.from_defaults(
    fn=get_portfolio,
    name="get_portfolio",
    description="Retrieves a client portfolio by client ID.",
)

get_client_contact_tool = FunctionTool.from_defaults(
    fn=get_client_contact,
    name="get_client_contact",
    description="Retrieves a client's primary contact and escalation tier from the external CRM.",
)

search_documents_tool = FunctionTool.from_defaults(
    fn=search_documents,
    name="search_documents",
    description="Searches internal compliance policies and client FAQ documents for relevant information.",
)

LLAMA_TOOL_REGISTRY = {
    "get_ticket": get_ticket_tool,
    "get_portfolio": get_portfolio_tool,
    "get_client_contact": get_client_contact_tool,
    "search_documents": search_documents_tool,
}