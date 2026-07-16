"""
main.py
=======
Simulates a genuinely EXTERNAL third-party system — a vendor CRM holding
client contact and escalation-tier information. This is intentionally a
separate service/container, reached over real HTTP, to make the
service-to-service authentication pattern concrete rather than commented-out.

Authentication here is a static API key, checked via a header — this
external vendor has no knowledge of our internal JWTs, our users, or our
roles. It only knows "is this caller presenting our agreed API key."
"""

from fastapi import FastAPI, Header, HTTPException
import os

app = FastAPI(title="Mock External CRM API")

EXPECTED_API_KEY = os.environ.get("EXTERNAL_CRM_API_KEY")

MOCK_CRM_DATA = {
    "CLIENT-88213": {
        "client_id": "CLIENT-88213",
        "primary_contact": "Sarah Chen",
        "contact_email": "s.chen@example-client.com",
        "escalation_tier": "Tier 2",
        "account_manager": "James Whitfield",
    }
}


def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@app.get("/client-contact/{client_id}")
def get_client_contact(client_id: str, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    contact = MOCK_CRM_DATA.get(client_id)
    if contact is None:
        raise HTTPException(status_code=404, detail=f"No contact record for {client_id}")
    return contact

@app.get("/health")
def health():
    return {"status": "ok"}