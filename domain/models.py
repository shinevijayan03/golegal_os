"""
GoLegal Domain Models - 3NF Relational Schema & ORM Mapping
"""
from datetime import datetime, timezone
import uuid
import json
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime, ForeignKey, Index, CheckConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_type = Column(String(20), nullable=False, default="Single_User")
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=False)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    agreements = relationship("Agreement", back_populates="initiator", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "user_type IN ('Single_User', 'Multi_User', 'Hybrid_User', 'Admin')",
            name="check_user_type"
        ),
    )


class Agreement(Base):
    __tablename__ = "agreements"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    initiator_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agreement_type = Column(String(50), nullable=False, default="Rental_Residential")
    state_code = Column(String(10), nullable=False, default="KA")
    status = Column(String(30), nullable=False, default="Draft")
    property_details = Column(Text, nullable=False, default="{}")  # Serialized JSON
    commercial_terms = Column(Text, nullable=False, default="{}")  # Serialized JSON
    custom_clauses = Column(Text, nullable=True)
    final_pdf_url = Column(Text, nullable=True)
    cloud_storage_consent = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=utc_now)
    executed_at = Column(DateTime, nullable=True)

    initiator = relationship("User", back_populates="agreements")
    parties = relationship("Party", back_populates="agreement", cascade="all, delete-orphan")
    estamp = relationship("EStamp", uselist=False, back_populates="agreement", cascade="all, delete-orphan")
    signatures = relationship("Signature", back_populates="agreement", cascade="all, delete-orphan")
    payment = relationship("Payment", uselist=False, back_populates="agreement", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="agreement", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_agreements_initiator", "initiator_id"),
        Index("idx_agreements_status", "status"),
        CheckConstraint(
            "agreement_type IN ('Rental_Residential', 'Rental_Commercial', 'NDA', 'Lease', 'Custom')",
            name="check_agreement_type"
        ),
        CheckConstraint(
            "status IN ('Draft', 'Paid', 'Pending_Signatures', 'Completed', 'Cancelled', 'Expired')",
            name="check_agreement_status"
        ),
    )

    def get_property_details(self) -> dict:
        return json.loads(self.property_details) if self.property_details else {}

    def set_property_details(self, data: dict):
        self.property_details = json.dumps(data)

    def get_commercial_terms(self) -> dict:
        return json.loads(self.commercial_terms) if self.commercial_terms else {}

    def set_commercial_terms(self, data: dict):
        self.commercial_terms = json.dumps(data)


class Party(Base):
    __tablename__ = "parties"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False)
    party_type = Column(String(20), nullable=False)  # Owner, Tenant, Witness
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    aadhaar_masked = Column(String(12), nullable=True)  # XXXXXXXX1234
    signing_status = Column(String(20), nullable=False, default="Pending")
    access_token = Column(String(255), unique=True, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="parties")
    signatures = relationship("Signature", back_populates="party", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_parties_agreement", "agreement_id"),
        Index("idx_parties_token", "access_token"),
        CheckConstraint(
            "party_type IN ('Owner', 'Tenant', 'Witness')",
            name="check_party_type"
        ),
        CheckConstraint(
            "signing_status IN ('Pending', 'Sent', 'Signed', 'Rejected')",
            name="check_signing_status"
        ),
    )


class EStamp(Base):
    __tablename__ = "estamps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), unique=True, nullable=False)
    certificate_number = Column(String(100), unique=True, nullable=False)
    state_code = Column(String(10), nullable=False)
    stamp_amount = Column(Float, nullable=False)
    purchased_by = Column(String(255), nullable=False)
    vendor = Column(String(50), nullable=False, default="StockHolding")
    issued_at = Column(DateTime, default=utc_now)
    certificate_url = Column(Text, nullable=False)

    agreement = relationship("Agreement", back_populates="estamp")


class Signature(Base):
    __tablename__ = "signatures"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False)
    party_id = Column(String(36), ForeignKey("parties.id", ondelete="CASCADE"), nullable=False)
    auth_type = Column(String(30), nullable=False, default="Aadhaar_OTP")
    transaction_ref = Column(String(255), nullable=False)
    cert_issuer = Column(String(255), nullable=False, default="GoLegal CCA ESP")
    signature_hash = Column(String(255), nullable=False)
    signed_at = Column(DateTime, default=utc_now)
    ip_address = Column(String(45), nullable=False, default="127.0.0.1")
    user_agent = Column(Text, nullable=True)

    agreement = relationship("Agreement", back_populates="signatures")
    party = relationship("Party", back_populates="signatures")

    __table_args__ = (
        Index("idx_signatures_agreement", "agreement_id"),
        Index("idx_signatures_party", "party_id"),
        CheckConstraint(
            "auth_type IN ('Aadhaar_OTP', 'Biometric', 'DSC_Hardware', 'Internal_DSC')",
            name="check_auth_type"
        ),
    )


class Payment(Base):
    __tablename__ = "payments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), unique=True, nullable=False)
    total_amount = Column(Float, nullable=False)
    stamp_duty_amount = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    payment_gateway = Column(String(50), nullable=False, default="Razorpay")
    gateway_payment_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), nullable=False, default="Pending")
    invoice_pdf_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="payment")

    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending', 'Success', 'Failed', 'Refunded')",
            name="check_payment_status"
        ),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(100), nullable=False)
    triggered_by = Column(String(255), nullable=False)
    event_data = Column(Text, nullable=False, default="{}")  # JSON
    recorded_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="audit_logs")

    __table_args__ = (
        Index("idx_audit_logs_agreement", "agreement_id"),
    )

    def get_event_data(self) -> dict:
        return json.loads(self.event_data) if self.event_data else {}

    def set_event_data(self, data: dict):
        self.event_data = json.dumps(data)


class SysConfig(Base):
    __tablename__ = "sysconfigTlb"

    id = Column(String(50), primary_key=True, default="GLOBAL_CONFIG")
    lang = Column(String(10), nullable=False, default="en")
    dig_sign = Column(String(50), nullable=False, default="Aadhaar_eSign")
    estamp = Column(Boolean, nullable=False, default=True)
    estamp_vendor = Column(String(50), nullable=False, default="StockHolding")
    currency = Column(String(10), nullable=False, default="INR")
    system_commission = Column(Float, nullable=False, default=18.0)
    discount = Column(Float, nullable=False, default=0.0)
    country = Column(String(10), nullable=False, default="IND")
    data_pruning_days = Column(Integer, nullable=False, default=27)
    agreement_retain_days = Column(Integer, nullable=False, default=2920)
    stockholding_prepaid_balance = Column(Float, nullable=False, default=50000.0)
    low_balance_threshold = Column(Float, nullable=False, default=10000.0)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)


class SysConfigJn(Base):
    __tablename__ = "sysconfigTlb$jn"

    jn_id = Column(String(36), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime, default=utc_now)
    operation = Column(String(20), nullable=False)
    updated_by_user = Column(String(255), nullable=False)
    previous_value = Column(Text, nullable=True)  # JSON
    new_value = Column(Text, nullable=False)  # JSON

    __table_args__ = (
        CheckConstraint(
            "operation IN ('INSERT', 'UPDATE', 'DELETE')",
            name="check_jn_operation"
        ),
    )
