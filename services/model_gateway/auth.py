"""
auth.py
=======
JWT verification for the Model Gateway. Same JWT_SECRET as identity and
orchestrator - this is what lets a token issued by identity, and already
verified once by the orchestrator, be independently re-verified here too.
This is the concrete implementation of "a downstream service must not
blindly trust an upstream caller's claimed identity."
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