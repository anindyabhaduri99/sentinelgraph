"""
external_apis_client.py
========================
Calls the external CRM service. This is the concrete answer to "how is
the user's access token handled for a service-to-service call to an
external API" - it is NOT handled at all here, because it shouldn't be.

The user's role is checked against our OWN entitlements (via the DAL)
BEFORE this function is ever invoked - that's where authorization happens.
This function then authenticates itself to the external system using our
own service-level API key, never the calling user's JWT. The external CRM
has no way to verify our internal JWT anyway - it isn't part of our trust
domain, and was never designed to accept our tokens.
"""

import os
import httpx
from dal.entitlements import enforce_entitlement

EXTERNAL_CRM_URL = os.environ.get("EXTERNAL_CRM_URL", "http://external-crm:8200")
EXTERNAL_CRM_API_KEY = os.environ.get("EXTERNAL_CRM_API_KEY")


def get_client_contact(client_id: str, role: str) -> dict:
    """
    DAL check happens here first, using the caller's role — this is our
    side of the trust boundary. Only after this passes do we make the
    real external call, authenticated with OUR service-level API key,
    not the user's token.
    """
    enforce_entitlement(role, resource="client_contact", action="read")

    response = httpx.get(
        f"{EXTERNAL_CRM_URL}/client-contact/{client_id}",
        headers={"X-API-Key": EXTERNAL_CRM_API_KEY},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()