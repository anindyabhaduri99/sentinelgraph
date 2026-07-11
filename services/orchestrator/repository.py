"""
repository.py
=============
Real database query functions. Each function opens a session, runs a real
parameterized SQLAlchemy query against Postgres, and returns a plain dict —
so the rest of the orchestrator (nodes.py) doesn't need to know about
SQLAlchemy ORM objects directly.
"""

from pydoc import cli
from db import SessionLocal
from models import Ticket, Portfolio
from dal.entitlements import enforce_entitlement

def get_ticket(ticket_id: str, role: str) -> dict:
    """
    Equivalent of: SELECT * FROM ticketing.tickets WHERE ticket_id = :ticket_id
    SQLAlchemy generates and parameterizes this automatically — no raw
    string concatenation, which is what prevents SQL injection here.
    """

    enforce_entitlement(role, resource="ticket", action="read")
    session = SessionLocal()

    try:
        ticket = session.query(Ticket).filter(Ticket.ticket_id == ticket_id).first()
        if ticket is None:
            return {"error": f"ticket {ticket_id} not found"}
        return {
            "ticket_id" : ticket.ticket_id,
            "client_id" : ticket.client_id,
            "subject" : ticket.subject,
            "status" : ticket.status,
            "sla_breach" : ticket.sla_breach,
        }
    finally:
        session.close()


def get_portfolio(client_id: str, role: str) -> dict:
    """
    Equivalent of: SELECT * FROM ticketing.portfolios WHERE client_id = :client_id
    """

    enforce_entitlement(role, resource="portfolio", action="read")
    session = SessionLocal()

    try:
        portfolio = session.query(Portfolio).filter(Portfolio.client_id == client_id).first()

        if portfolio is None:
            return {"error": f"client {client_id} not found"}
        return {
            "client_id": portfolio.client_id,
            "portfolio_value": float(portfolio.portfolio_value),
            "allocations": {
                "equities": float(portfolio.equities_pct),
                "bonds": float(portfolio.bonds_pct),
                "cash": float(portfolio.cash_pct),
            },
            "risk_profile": portfolio.risk_profile,
        }

    finally:
        session.close()

def update_portfolio_allocation(client_id: str, equities_pct: float, bonds_pct: float, cash_pct: float, role: str) -> dict:
    enforce_entitlement(role, resource="portfolio", action="write")

    session = SessionLocal()
    try:
        portfolio = session.query(Portfolio).filter(Portfolio.client_id == client_id).first()
        if portfolio is None:
            return {"error": f"client {client_id} not found"}

        portfolio.equities_pct = equities_pct
        portfolio.bonds_pct = bonds_pct
        portfolio.cash_pct = cash_pct
        session.commit()

        return {
            "client_id": client_id,
            "new_allocations": {"equities": equities_pct, "bonds": bonds_pct, "cash": cash_pct},
        }
    finally:
        session.close()