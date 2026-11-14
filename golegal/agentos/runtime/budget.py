"""
AgentOS Atomic INR Paise Budget Ledger & Pre-Dispatch Reservation Service.
Enforces AOS-13, AT-15, and PRD Section 6 budget semantics.
"""
from __future__ import annotations
import uuid
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func

from golegal.agentos.domain.models import BudgetLedgerEntry, Mission, generate_uuid


class BudgetExceededError(ValueError):
    """Raised when an operation would exceed the mission's authorized INR paise ceiling (AT-15)."""
    pass


class BudgetService:
    def __init__(self, session: Session):
        self.session = session

    def get_mission_spending_summary(self, mission_id: str) -> Dict[str, int]:
        """Calculates total reserved, settled, and remaining budget in paise."""
        mission = self.session.query(Mission).filter_by(id=mission_id).first()
        if not mission:
            raise ValueError(f"Mission '{mission_id}' not found.")

        entries = self.session.query(BudgetLedgerEntry).filter_by(mission_id=mission_id).all()
        settled_paise = sum(e.actual_cost_minor or 0 for e in entries if e.status == "SETTLED")
        reserved_paise = sum(e.estimated_cost_minor for e in entries if e.status == "RESERVED")
        total_committed = settled_paise + reserved_paise
        remaining_paise = max(0, mission.budget_limit_minor - total_committed)

        return {
            "budget_limit_paise": mission.budget_limit_minor,
            "settled_paise": settled_paise,
            "reserved_paise": reserved_paise,
            "total_committed_paise": total_committed,
            "remaining_paise": remaining_paise,
        }

    def reserve_budget(
        self,
        mission_id: str,
        estimated_cost_minor: int,
        provider: str = "local_gpu_rtx3060",
        model: str = "qwen_contract_extractor"
    ) -> BudgetLedgerEntry:
        """
        Enforces AOS-13 & AT-15: Atomic reserve-before-dispatch.
        Blocks invocation before dispatch if reservation exceeds limit.
        """
        summary = self.get_mission_spending_summary(mission_id)
        if summary["total_committed_paise"] + estimated_cost_minor > summary["budget_limit_paise"]:
            mission = self.session.query(Mission).filter_by(id=mission_id).first()
            if mission:
                mission.status = "BUDGET_EXCEEDED"
                self.session.commit()
            raise BudgetExceededError(
                f"422 BUDGET_EXCEEDED: Estimated cost {estimated_cost_minor} paise exceeds remaining budget "
                f"{summary['remaining_paise']} paise (Limit: {summary['budget_limit_paise']} paise)."
            )

        res_id = f"res-{generate_uuid()[:12]}"
        entry = BudgetLedgerEntry(
            mission_id=mission_id,
            reservation_id=res_id,
            provider=provider,
            model=model,
            tokens_in=0,
            tokens_out=0,
            estimated_cost_minor=estimated_cost_minor,
            actual_cost_minor=None,
            status="RESERVED"
        )
        self.session.add(entry)
        self.session.commit()
        return entry

    def settle_reservation(
        self,
        reservation_id: str,
        actual_cost_minor: int,
        tokens_in: int = 0,
        tokens_out: int = 0
    ) -> BudgetLedgerEntry:
        """Settles an existing reservation with actual incurred cost."""
        entry = self.session.query(BudgetLedgerEntry).filter_by(reservation_id=reservation_id).first()
        if not entry:
            raise ValueError(f"Reservation '{reservation_id}' not found.")

        entry.actual_cost_minor = actual_cost_minor
        entry.tokens_in = tokens_in
        entry.tokens_out = tokens_out
        entry.status = "SETTLED"
        self.session.commit()
        return entry

    def release_reservation(self, reservation_id: str) -> BudgetLedgerEntry:
        """Releases an unconsumed reservation back to available budget on failed task."""
        entry = self.session.query(BudgetLedgerEntry).filter_by(reservation_id=reservation_id).first()
        if not entry:
            raise ValueError(f"Reservation '{reservation_id}' not found.")

        entry.status = "RELEASED"
        entry.actual_cost_minor = 0
        self.session.commit()
        return entry


# Alias for backward compatibility
BudgetManager = BudgetService
