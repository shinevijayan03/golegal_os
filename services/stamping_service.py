"""
GoLegal StockHolding Corporation of India (SHCIL) e-Stamp Service
Handles e-Stamp procurement, prepaid balance ledger debits, and low-balance alerts.
"""
import uuid
from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session
from domain.models import EStamp, SysConfig, SysConfigJn, AuditLog

LOW_BALANCE_THRESHOLD = 10000.0


class InsufficientStampingBalanceError(Exception):
    pass


class StampingService:
    def __init__(self, session: Session):
        self.session = session

    def get_prepaid_balance(self) -> float:
        config = self.session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        if not config:
            return 50000.0
        return float(config.stockholding_prepaid_balance)

    def is_low_balance(self) -> bool:
        return self.get_prepaid_balance() < LOW_BALANCE_THRESHOLD

    def top_up_balance(self, amount: float, admin_user: str = "ADMIN") -> float:
        """Top up the StockHolding corporate prepaid deposit."""
        if amount <= 0:
            raise ValueError("Top up amount must be greater than zero")

        config = self.session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        if not config:
            config = SysConfig(id="GLOBAL_CONFIG", stockholding_prepaid_balance=50000.0)
            self.session.add(config)

        prev = config.stockholding_prepaid_balance
        config.stockholding_prepaid_balance += amount
        config.updated_at = datetime.now(timezone.utc)

        # Append to audit journal
        jn = SysConfigJn(
            operation="UPDATE",
            updated_by_user=admin_user,
            previous_value=json.dumps({"stockholding_prepaid_balance": prev}),
            new_value=json.dumps({"stockholding_prepaid_balance": config.stockholding_prepaid_balance, "top_up": amount})
        )
        self.session.add(jn)
        self.session.commit()
        return config.stockholding_prepaid_balance

    def procure_estamp(
        self,
        agreement_id: str,
        state_code: str,
        stamp_amount: float,
        purchased_by: str,
        vendor: str = "StockHolding"
    ) -> EStamp:
        """
        Procure verified e-Stamp certificate and debit prepaid balance.
        """
        # Check existing e-stamp for idempotency before debiting balance
        existing = self.session.query(EStamp).filter_by(agreement_id=agreement_id).first()
        if existing:
            return existing

        config = self.session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        if not config:
            config = SysConfig(id="GLOBAL_CONFIG", stockholding_prepaid_balance=50000.0)
            self.session.add(config)

        if config.stockholding_prepaid_balance < stamp_amount:
            raise InsufficientStampingBalanceError(
                f"SHCIL prepaid balance (₹{config.stockholding_prepaid_balance:.2f}) is insufficient for duty ₹{stamp_amount:.2f}"
            )

        # Debit balance
        prev_balance = config.stockholding_prepaid_balance
        config.stockholding_prepaid_balance -= stamp_amount
        config.updated_at = datetime.now(timezone.utc)

        cert_num = f"IN-{state_code.upper()}{int(stamp_amount):04d}{uuid.uuid4().hex[:10].upper()}"
        estamp = EStamp(
            agreement_id=agreement_id,
            certificate_number=cert_num,
            state_code=state_code.upper(),
            stamp_amount=stamp_amount,
            purchased_by=purchased_by,
            vendor=vendor,
            certificate_url=f"/artifacts/estamps/{cert_num}.pdf"
        )
        self.session.add(estamp)

        # Journal entry for debit
        jn = SysConfigJn(
            operation="UPDATE",
            updated_by_user="SYSTEM_STAMPING_WORKER",
            previous_value=json.dumps({"stockholding_prepaid_balance": prev_balance}),
            new_value=json.dumps({
                "stockholding_prepaid_balance": config.stockholding_prepaid_balance,
                "debited": stamp_amount,
                "certificate_number": cert_num
            })
        )
        self.session.add(jn)

        # Audit log for agreement
        audit = AuditLog(
            agreement_id=agreement_id,
            event_type="ESTAMP_PROCURED",
            triggered_by="SHCIL_GATEWAY",
            event_data=json.dumps({
                "certificate_number": cert_num,
                "stamp_amount": stamp_amount,
                "state": state_code,
                "remaining_balance": config.stockholding_prepaid_balance,
                "low_balance_alert": config.stockholding_prepaid_balance < LOW_BALANCE_THRESHOLD
            })
        )
        self.session.add(audit)
        self.session.commit()
        return estamp
