"""
auth.py
=======
JWT verification for the orchestrator. This service only ever verifies
tokens (never issues them) — issuance is the identity service's job
exclusively. Uses the same JWT_SECRET as the identity service, since
that's what makes a token signed by identity verifiable here.
"""

import os
import jwt
from fastapi import HTTPException, Header

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"


def verify_access_token(authorization: str = Header(None)) -> dict:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Access token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Provided token is not an access token")

    return payload