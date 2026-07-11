"""
models.py
=========
SQLAlchemy ORM model mapping to identity.users.
"""

from sqlalchemy import Column, String, TIMESTAMP, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    user_id = Column(String(50), primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now())