"""
Deduplicated Lifecycle Reminder & Expiry Notification Service.
Enforces FR-10, AT-12, and AT-17.
"""
from __future__ import annotations
from datetime import datetime, date, timezone, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session

from golegal.domain.models import Reminder, utc_now


class ReminderService:
    def __init__(self, session: Session):
        self.session = session

    def schedule_reminder(
        self, contract_id: str, kind: str, event_date: date, source_confirmed: bool = True
    ) -> Optional[Reminder]:
        """Enforces AT-12: Reminders are scheduled ONLY from confirmed native fields or human-accepted candidates."""
        if not source_confirmed:
            return None  # Unconfirmed candidates cannot trigger legal reminder scheduling

        dedupe_key = f"{contract_id}:{kind}:{event_date.isoformat()}"
        existing = self.session.query(Reminder).filter_by(dedupe_key=dedupe_key).first()
        if existing:
            return existing

        # Schedule reminder 30 days before event date
        send_at = datetime.combine(event_date, datetime.min.time(), tzinfo=timezone.utc) - timedelta(days=30)
        reminder = Reminder(
            contract_id=contract_id,
            kind=kind,
            event_date=event_date,
            send_at_utc=send_at,
            status="scheduled",
            dedupe_key=dedupe_key,
            source_field_confirmed=source_confirmed
        )
        self.session.add(reminder)
        self.session.flush()
        return reminder

    def list_reminders_for_contract(self, contract_id: str) -> List[Reminder]:
        return self.session.query(Reminder).filter_by(contract_id=contract_id).all()
