"""
Configurable Stamping Verification Gate & Treasury Service.
Enforces FR-08 & AT-06: Unverified stamp duty blocks execution with 422.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session

from golegal.domain.models import StampRecord, Contract, utc_now


class StampGateError(ValueError):
    """Raised when mandatory stamp duty is unverified or missing (422)."""
    pass


class StampingService:
    def __init__(self, session: Session):
        self.session = session

    def get_stamp_record(self, contract_id: str) -> Optional[StampRecord]:
        return self.session.query(StampRecord).filter_by(contract_id=contract_id).first()

    def record_verified_stamp(
        self, contract_id: str, amount_paise: int, cert_num: str, verified_by: str, jurisdiction: str = "KA"
    ) -> StampRecord:
        rec = self.get_stamp_record(contract_id)
        if not rec:
            rec = StampRecord(contract_id=contract_id, jurisdiction_code=jurisdiction)
            self.session.add(rec)

        rec.status = "verified"
        rec.amount_paise = amount_paise
        rec.receipt_object_key = f"stamps/{jurisdiction}/{cert_num}.pdf"
        rec.verified_by = verified_by
        rec.verified_at = utc_now()
        self.session.flush()
        return rec

    def assert_stamp_verified(self, contract_id: str, org_id: str) -> None:
        """Enforces AT-06: Pre-execution gate fails closed if stamp is unverified."""
        rec = self.get_stamp_record(contract_id)
        if not rec or rec.status != "verified":
            raise StampGateError(
                f"422 STAMP_UNVERIFIED: Contract '{contract_id}' requires mandatory state stamp duty. "
                f"Current stamp status is '{rec.status if rec else 'none'}'. "
                "System does not infer statutory amounts without verified administrator or provider receipt."
            )
