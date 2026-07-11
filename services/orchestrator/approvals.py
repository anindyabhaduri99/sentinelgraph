"""
approvals.py
============
HITL approval queue functions. Write actions produced by the graph are
stored here as pending, never executed automatically. A human reviewer
(admin/ops) approves or rejects; only approval triggers real execution.
"""

from db import SessionLocal
from models import PendingApproval
from repository import update_portfolio_allocation


def create_pending_approval(user_id: str, role: str, original_request: str, draft_response: str, action_type: str) -> dict:
    session = SessionLocal()
    try:
        approval = PendingApproval(
            user_id=user_id,
            role=role,
            original_request=original_request,
            draft_response=draft_response,
            action_type=action_type,
            status="pending",
        )
        session.add(approval)
        session.commit()
        return {"approval_id": approval.id, "status": "pending"}
    finally:
        session.close()


def list_pending_approvals() -> list[dict]:
    session = SessionLocal()
    try:
        rows = session.query(PendingApproval).filter(PendingApproval.status == "pending").all()
        result = []
        for row in rows:
            result.append({
                "id": row.id,
                "user_id": row.user_id,
                "role": row.role,
                "original_request": row.original_request,
                "draft_response": row.draft_response,
                "action_type": row.action_type,
                "status": row.status,
                "created_at": str(row.created_at),
            })
        return result
    finally:
        session.close()


def decide_approval(approval_id: int, decision: str, reviewer_id: str) -> dict:
    session = SessionLocal()
    try:
        approval = session.query(PendingApproval).filter(PendingApproval.id == approval_id).first()
        if approval is None:
            return {"error": f"approval {approval_id} not found"}
        if approval.status != "pending":
            return {"error": f"approval {approval_id} already {approval.status}"}

        if decision == "approve":
            approval.status = "approved"
        elif decision == "reject":
            approval.status = "rejected"
        else:
            return {"error": "decision must be 'approve' or 'reject'"}

        approval.reviewed_by = reviewer_id
        from datetime import datetime, timezone
        approval.reviewed_at = datetime.now(timezone.utc)
        session.commit()

        return {"approval_id": approval_id, "status": approval.status}
    finally:
        session.close()