"""
auth.py
=======
Password hashing (bcrypt) and JWT creation/verification helpers. Kept
separate from main.py so the actual security-sensitive logic lives in
one small, easily-reviewed file rather than being scattered inline
inside endpoint functions.
"""

import os
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

def hash_password(plain_password: str) -> str:
    """
    Generates a bcrypt hash with an automatically-embedded random salt.
    Returned as a string (bcrypt returns bytes; we decode for storage as
    a VARCHAR column).
    """

    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> str:
    """
    Re-hashes the provided plain password using the salt embedded in the
    stored hash, and compares. Never decrypts anything - see prior
    discussion on why bcrypt is one-way by design.
    """
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))

def create_access_token(user_id: str, role: str) -> str:
    """
    Short-lived token (15 min) proving the caller's identity and role for
    a single session. Deliberately short-lived: if leaked, its window of
    misuse is small. Every subsequent hop (DAL, tool calls) will validate
    this token rather than trusting a caller's self-reported identity.
    """

    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    """
    Long-lived token (7 days) used only to obtain a new access token
    without re-entering a password. Deliberately carries no role claim -
    role is only asserted in freshly-issued access tokens, so a stale
    refresh token can't be used to smuggle an outdated role.
    """

    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> str:
    """
    Verifies signature and expiry, returns the decoded payload. Raises
    jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure - the
    caller (main.py) is responsible for turning these into proper HTTP
    error responses.
    """

    return jwt.decode(token, JWT_SECRET, algorithm=[JWT_ALGORITHM])

