"""
entitlements.py
======
Data Access Layer. The single gatekeeper every data-fetching function
must pass through. Answers exactly one deterministic question: "is this
role allowed to do this action on this resource?" by checking the
identity.entitlements table. No LLM involvement at all - this is plain,
boring, auditable rule-checking, on purpose.
"""

from sqlalchemy import text
from db import SessionLocal

class AccessDeniedError(Exception):
    """Raised when a role lacks the required entitlement. Caught by the
    calling node and turned into a clear, safe response - never a raw
    stack trace or silent data leak."""

    pass
def check_entitlement(role: str, resource: str, action: str) -> bool:
    """
    Returns True if this exact (role, resource, action) combination
    exists in identity.entitlements, False otherwise. This is the
    ENTIRE access-control decision - one row lookup, nothing more.
    """

    session = SessionLocal()

    try:
        result = session.execute(
            text(
                "SELECT 1 FROM identity.entitlements "
                "WHERE role = :role AND resource = :resource AND action = :action"
            ),
            {"role": role, "resource": resource, "action": action}
        ).first()

        return result is not None
    finally:
        session.close()

def enforce_entitlement(role: str, resource: str, action: str):
    """
    Same check as above, but raises AccessDeniedError instead of
    returning a boolean - used right before any actual data access, so
    the calling code can't accidentally forget to check the result.
    """

    if not check_entitlement(role, resource, action):
        raise AccessDeniedError(
            f"role '{role}' is not entitled to '{action}' on '{resource}'"
        )
               
