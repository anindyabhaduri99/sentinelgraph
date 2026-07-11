"""
registry.py
===========
Registration and lookup functions for identity.tool_registry. This is
the mechanism a "domain team" uses to add their tool into the shared
catalog — mirrors the federated Plugin Registry pattern.
"""

from db import SessionLocal
from models import ToolRegistry


def register_tool(tool_name: str, description: str, input_schema: dict, resource: str, owning_domain: str) -> dict:
    session = SessionLocal()
    try:
        existing = session.query(ToolRegistry).filter(ToolRegistry.tool_name == tool_name).first()
        if existing:
            return {"error": f"Tool '{tool_name}' is already registered"}

        new_tool = ToolRegistry(
            tool_name=tool_name,
            description=description,
            input_schema=input_schema,
            resource=resource,
            owning_domain=owning_domain,
        )
        session.add(new_tool)
        session.commit()
        return {"message": f"Tool '{tool_name}' registered successfully"}
    finally:
        session.close()


def list_tools() -> list[dict]:
    session = SessionLocal()
    try:
        tools = session.query(ToolRegistry).filter(ToolRegistry.enabled == True).all()
        return [
            {
                "tool_name": t.tool_name,
                "description": t.description,
                "input_schema": t.input_schema,
                "resource": t.resource,
                "owning_domain": t.owning_domain,
            }
            for t in tools
        ]
    finally:
        session.close()