"""
GoLegal Agreement Workflow & Asynchronous Signing State Machine
"""
import uuid
from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session
from domain.models import Agreement, Party, Signature, AuditLog


class InvalidStateTransitionError(Exception):
    pass


class WorkflowService:
    VALID_TRANSITIONS = {
        "Draft": ["Paid", "Cancelled"],
        "Paid": ["Pending_Signatures", "Cancelled"],
        "Pending_Signatures": ["Completed", "Expired", "Cancelled"],
        "Completed": [],
        "Cancelled": [],
        "Expired": []
    }

    def __init__(self, session: Session):
        self.session = session

    def transition_state(self, agreement: Agreement, new_state: str, triggered_by: str = "SYSTEM"):
        """Enforce strict lifecycle transitions."""
        current = agreement.status
        allowed = self.VALID_TRANSITIONS.get(current, [])
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition agreement from '{current}' to '{new_state}'. Permitted: {allowed}"
            )

        agreement.status = new_state
        if new_state == "Completed":
            agreement.executed_at = datetime.now(timezone.utc)

        audit = AuditLog(
            agreement_id=agreement.id,
            event_type="STATE_TRANSITION",
            triggered_by=triggered_by,
            event_data=json.dumps({
                "from_state": current,
                "to_state": new_state,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        )
        self.session.add(audit)
        self.session.commit()

    def check_and_complete_signing(self, agreement_id: str) -> bool:
        """
        Evaluate non-atomic multi-party signing progress.
        If all designated owners, tenants, and witnesses have signed,
        atomically transition agreement to 'Completed'.
        """
        agreement = self.session.query(Agreement).filter_by(id=agreement_id).first()
        if not agreement:
            raise ValueError("Agreement not found")

        if agreement.status != "Pending_Signatures":
            return agreement.status == "Completed"

        parties = self.session.query(Party).filter_by(agreement_id=agreement_id).all()
        if not parties:
            return False

        all_signed = all(p.signing_status == "Signed" for p in parties)
        if all_signed:
            self.transition_state(agreement, "Completed", triggered_by="SIGNING_COMPLETION_ENGINE")
            return True
        return False

    def get_signing_progress(self, agreement_id: str) -> dict:
        """Return real-time signatory completion matrix."""
        parties = self.session.query(Party).filter_by(agreement_id=agreement_id).all()
        total = len(parties)
        signed_count = sum(1 for p in parties if p.signing_status == "Signed")
        return {
            "agreement_id": agreement_id,
            "total_parties": total,
            "signed_count": signed_count,
            "all_signed": total > 0 and signed_count == total,
            "parties": [
                {
                    "party_id": p.id,
                    "name": p.full_name,
                    "type": p.party_type,
                    "email": p.email,
                    "status": p.signing_status
                }
                for p in parties
            ]
        }
