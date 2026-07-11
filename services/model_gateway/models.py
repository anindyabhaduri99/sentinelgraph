"""
models.py
=========
SQLAlchemy ORM model mapping to observability.token_usage. Same purpose
as the orchestrator's models.py — a Python class representation of the
real Postgres table, so main.py can insert rows without hand-writing SQL.
"""

from sqlalchemy import Column, Integer, String, Numeric, TIMESTAMP, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class TokenUsage(Base):
    __tablename__ = "token_usage"
    __table_args__ = {"schema": "observability"}

    id = Column(Integer, primary_key=True)
    role = Column(String(30), nullable=False)
    provider = Column(String(20), nullable=False)
    model = Column(String(50), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost_usd = Column(Numeric(10, 6), nullable=False)
    created_at = Column(TIMESTAMP, server_default=func.now())

    