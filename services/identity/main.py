"""
main.py
=======
FastAPI entrypoint for the Identity service. Exposes /register, /login,
and /refresh. This is the only service that ever sees a plain-text
password - every other service only ever sees JWTs.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import jwt

from db import SessionLocal
from models import User
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

app = FastAPI(title="SentinelGraph Identity Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_ROLES = {"admin", "portfolio_manager", "ops", "external_client", "risk_analyst"}


class RegisterRequest(BaseModel):
    user_id: str
    email: EmailStr
    password: str
    confirm_password: str
    role: str


class LoginRequest(BaseModel):
    user_id: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    role: str


@app.post("/register", status_code=201)
def register(req: RegisterRequest):
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if req.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {VALID_ROLES}")

    session = SessionLocal()
    try:
        existing = session.query(User).filter(
            (User.user_id == req.user_id) | (User.email == req.email)
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail="User ID or email already exists")

        new_user = User(
            user_id=req.user_id,
            email=req.email,
            password_hash=hash_password(req.password),
            role=req.role,
        )
        session.add(new_user)
        session.commit()
        return {"message": "User registered successfully", "user_id": req.user_id}
    finally:
        session.close()


@app.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.user_id == req.user_id).first()
        if user is None or not verify_password(req.password, user.password_hash):
            # Deliberately identical error for "no such user" and "wrong
            # password" - revealing which one it was would let an
            # attacker enumerate valid user IDs.
            raise HTTPException(status_code=401, detail="Invalid user ID or password")

        access_token = create_access_token(user.user_id, user.role)
        refresh_token = create_refresh_token(user.user_id)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token, role=user.role)
    finally:
        session.close()


@app.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest):
    try:
        payload = decode_token(req.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Provided token is not a refresh token")

    user_id = payload["sub"]

    session = SessionLocal()
    try:
        user = session.query(User).filter(User.user_id == user_id).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User no longer exists")

        # Role is looked up fresh here, not trusted from any prior token -
        # this is what makes a role change take effect on next refresh.
        new_access_token = create_access_token(user.user_id, user.role)
        new_refresh_token = create_refresh_token(user.user_id)
        return TokenResponse(access_token=new_access_token, refresh_token=new_refresh_token, role=user.role)
    finally:
        session.close()


@app.get("/health")
def health():
    return {"status": "ok"}