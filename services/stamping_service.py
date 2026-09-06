"""
GoLegal StockHolding Corporation of India (SHCIL) e-Stamp Service
Handles e-Stamp procurement, prepaid balance ledger debits, and low-balance alerts.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy.orm import Session

from config import settings
from domain.models import AuditLog, EStamp, SysConfig, SysConfigJn, utc_now

LOW_BALANCE_THRESHOLD = settings.low_balance_threshold


class InsufficientStampingBalanceError(Exception):
    pass


class StampingService:
    def __init__(self, session: Session):
        self.session = session

    def _config(self, create: bool = False) -> SysConfig | None:
        config = self.session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        if not config and create:
            config = SysConfig(id="GLOBAL_CONFIG", stockholding_prepaid_balance=settings.initial_prepaid_balance)
            self.session.add(config)
        return config

    def get_prepaid_balance(self) -> float:
        config = self._config()
        if not config:
            return settings.initial_prepaid_balance
        return float(config.stockholding_prepaid_balance)

    def get_threshold(self) -> float:
        config = self._config()
        return float(config.low_balance_threshold) if config else LOW_BALANCE_THRESHOLD

    def is_low_balance(self) -> bool:
        return self.get_prepaid_balance() < self.get_threshold()

    def top_up_balance(self, amount: float, admin_user: str = "ADMIN") -> float:
        """Top up the StockHolding corporate prepaid deposit."""
        if amount <= 0:
            raise ValueError("Top up amount must be greater than zero")

        config = self._config(create=True)
        prev = config.stockholding_prepaid_balance
        config.stockholding_prepaid_balance += amount
        config.updated_at = utc_now()

        self.session.add(SysConfigJn(
            operation="UPDATE",
            updated_by_user=admin_user,
            previous_value=json.dumps({"stockholding_prepaid_balance": prev}),
            new_value=json.dumps({"stockholding_prepaid_balance": config.stockholding_prepaid_balance, "top_up": amount}),
        ))
        self.session.commit()
        return config.stockholding_prepaid_balance

    def procure_estamp(
        self,
        agreement_id: str,
        state_code: str,
        stamp_amount: float,
        purchased_by: str,
        vendor: str = "StockHolding",
    ) -> EStamp:
        """
        Procure verified e-Stamp certificate and debit prepaid balance.
        Idempotent per agreement: a second call returns the existing certificate without a second debit.
        """
        existing = self.session.query(EStamp).filter_by(agreement_id=agreement_id).first()
        if existing:
            return existing

        config = self._config(create=True)
        if config.stockholding_prepaid_balance < stamp_amount:
            raise InsufficientStampingBalanceError(
                f"SHCIL prepaid balance (₹{config.stockholding_prepaid_balance:.2f}) is insufficient for duty ₹{stamp_amount:.2f}"
            )

        prev_balance = config.stockholding_prepaid_balance
        config.stockholding_prepaid_balance -= stamp_amount
        config.updated_at = utc_now()

        cert_num = f"IN-{state_code.upper()}{int(stamp_amount):04d}{uuid.uuid4().hex[:10].upper()}"
        estamp = EStamp(
            agreement_id=agreement_id,
            certificate_number=cert_num,
            state_code=state_code.upper(),
            stamp_amount=stamp_amount,
            purchased_by=purchased_by,
            vendor=vendor,
            issued_at=utc_now(),
            certificate_url=f"/artifacts/estamps/{cert_num}.pdf",
        )
        self.session.add(estamp)

        self.session.add(SysConfigJn(
            operation="UPDATE",
            updated_by_user="SYSTEM_STAMPING_WORKER",
            previous_value=json.dumps({"stockholding_prepaid_balance": prev_balance}),
            new_value=json.dumps({
                "stockholding_prepaid_balance": config.stockholding_prepaid_balance,
                "debited": stamp_amount,
                "certificate_number": cert_num,
                "agreement_id": agreement_id,
            }),
        ))

        low = config.stockholding_prepaid_balance < float(config.low_balance_threshold or LOW_BALANCE_THRESHOLD)
        self.session.add(AuditLog(
            agreement_id=agreement_id,
            event_type="ESTAMP_PROCURED",
            triggered_by="SHCIL_GATEWAY",
            event_data=json.dumps({
                "certificate_number": cert_num,
                "stamp_amount": stamp_amount,
                "state": state_code,
                "remaining_balance": config.stockholding_prepaid_balance,
                "low_balance_alert": low,
            }),
        ))
        self.session.commit()
        return estamp

    def ledger(self, limit: int = 25) -> list[SysConfigJn]:
        return self.session.query(SysConfigJn).order_by(SysConfigJn.timestamp.desc()).limit(limit).all()
