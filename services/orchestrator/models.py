"""
models.py
=========
SQLAlchemy ORM models mapping Python classes to the real Postgres tables
created in infra/local/init-schemas.sql. Using the ORM rather than raw SQL
strings gives us type safety and protects against SQL injection by default,
since SQLAlchemy parameterizes every query it generates.
"""

from sqlalchemy import Column, String, Boolean, Numeric, TIMESTAMP, JSON, func, Integer
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = {"schema" : "ticketing"}

    ticket_id = Column(String(20), primary_key=True)
    client_id = Column(String(20), nullable=False)
    subject = Column(String, nullable=False)
    status = Column(String(20), nullable=False, default="open")
    sla_breach = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now())

class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = {"schema" : "ticketing"}

    client_id = Column(String(20), primary_key=True)
    portfolio_value = Column(Numeric(15, 2), nullable=False)
    equities_pct = Column(Numeric(4, 3), nullable=False)
    bonds_pct = Column(Numeric(4, 3), nullable=False)
    cash_pct = Column(Numeric(4, 3), nullable=False)
    risk_profile = Column(String(20), nullable=False)

class ToolRegistry(Base):
    __tablename__ = "tool_registry"
    __table_args__ = {"schema": "identity"}

    tool_name = Column(String(50), primary_key=True)
    description = Column(String, nullable=False)
    input_schema = Column(JSON, nullable=False)
    resource = Column(String(50), nullable=False)
    owning_domain = Column(String(50), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

class PendingApproval(Base):
    __tablename__ = "pending_approvals"
    __table_args__ = {"schema": "identity"}

    id = Column(Integer, primary_key=True)
    user_id = Column(String(50), nullable=False)
    role = Column(String(30), nullable=False)
    original_request = Column(String, nullable=False)
    draft_response = Column(String, nullable=False)
    action_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())
    reviewed_by = Column(String(50))
    reviewed_at = Column(TIMESTAMP)