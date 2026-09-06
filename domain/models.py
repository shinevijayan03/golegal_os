"""
GoLegal Domain Models - 3NF Relational Schema & ORM Mapping

Every entity in the PRD Section 9 ER model is represented here, plus the
operational tables the agentic platform needs: documents (content-addressed
PDF store), OTP challenges, login events (suspicious-ingress detection),
notifications (dispatch ledger), feedback (NPS) and agent runs (AI audit).
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer,
    LargeBinary, String, Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

AGREEMENT_TYPES = ("Rental_Residential", "Rental_Commercial", "NDA", "Lease", "Custom")
AGREEMENT_STATUSES = ("Draft", "Paid", "Pending_Signatures", "Completed", "Cancelled", "Expired")
PARTY_TYPES = ("Owner", "Tenant", "Witness")
SIGNING_STATUSES = ("Pending", "Sent", "Signed", "Rejected")
USER_TYPES = ("Single_User", "Multi_User", "Hybrid_User", "Admin")


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Naive UTC timestamp (SQLite drops tzinfo; keep comparisons consistent)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sql_in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


class JsonMixin:
    """Helpers for Text columns that hold serialized JSON."""

    @staticmethod
    def _loads(raw, default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return default


class User(Base, JsonMixin):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_type = Column(String(20), nullable=False, default="Single_User")
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    phone = Column(String(20), nullable=False)
    address = Column(Text, nullable=True)
    state_code = Column(String(10), nullable=True)
    password_hash = Column(String(512), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    notification_prefs = Column(Text, nullable=False, default='{"sms": true, "email": true, "whatsapp": true}')
    last_login_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    agreements = relationship("Agreement", back_populates="initiator", cascade="all, delete-orphan")
    login_events = relationship("LoginEvent", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_users_phone", "phone"),
        CheckConstraint(f"user_type IN ({_sql_in(USER_TYPES)})", name="check_user_type"),
    )

    @property
    def is_admin(self) -> bool:
        return self.user_type == "Admin"

    def get_notification_prefs(self) -> dict:
        return self._loads(self.notification_prefs, {"sms": True, "email": True, "whatsapp": True})


class Agreement(Base, JsonMixin):
    __tablename__ = "agreements"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    initiator_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    agreement_type = Column(String(50), nullable=False, default="Rental_Residential")
    state_code = Column(String(10), nullable=False, default="KA")
    status = Column(String(30), nullable=False, default="Draft")
    property_details = Column(Text, nullable=False, default="{}")  # Serialized JSON
    commercial_terms = Column(Text, nullable=False, default="{}")  # Serialized JSON
    clause_toggles = Column(Text, nullable=False, default="{}")    # Serialized JSON
    custom_clauses = Column(Text, nullable=True)
    ai_risk_report = Column(Text, nullable=True)                   # Serialized JSON
    final_pdf_url = Column(Text, nullable=True)
    final_pdf_sha256 = Column(String(64), nullable=True)
    cloud_storage_consent = Column(Boolean, nullable=False, default=True)
    is_archived = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    executed_at = Column(DateTime, nullable=True)

    initiator = relationship("User", back_populates="agreements")
    parties = relationship("Party", back_populates="agreement", cascade="all, delete-orphan",
                           order_by="Party.created_at")
    estamp = relationship("EStamp", uselist=False, back_populates="agreement", cascade="all, delete-orphan")
    signatures = relationship("Signature", back_populates="agreement", cascade="all, delete-orphan")
    payment = relationship("Payment", uselist=False, back_populates="agreement", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="agreement", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="agreement", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="agreement", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_agreements_initiator", "initiator_id"),
        Index("idx_agreements_status", "status"),
        CheckConstraint(f"agreement_type IN ({_sql_in(AGREEMENT_TYPES)})", name="check_agreement_type"),
        CheckConstraint(f"status IN ({_sql_in(AGREEMENT_STATUSES)})", name="check_agreement_status"),
    )

    def get_property_details(self) -> dict:
        return self._loads(self.property_details, {})

    def set_property_details(self, data: dict):
        self.property_details = json.dumps(data)

    def get_commercial_terms(self) -> dict:
        return self._loads(self.commercial_terms, {})

    def set_commercial_terms(self, data: dict):
        self.commercial_terms = json.dumps(data)

    def get_clause_toggles(self) -> dict:
        return self._loads(self.clause_toggles, {})

    def set_clause_toggles(self, data: dict):
        self.clause_toggles = json.dumps(data)

    def get_ai_risk_report(self) -> dict | None:
        return self._loads(self.ai_risk_report, None)

    def set_ai_risk_report(self, data: dict):
        self.ai_risk_report = json.dumps(data)

    @property
    def display_title(self) -> str:
        if self.title:
            return self.title
        prop = self.get_property_details()
        return prop.get("premises_name") or self.agreement_type.replace("_", " ")

    def signed_count(self) -> int:
        return sum(1 for p in self.parties if p.signing_status == "Signed")


class Party(Base):
    __tablename__ = "parties"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False)
    party_type = Column(String(20), nullable=False)  # Owner, Tenant, Witness
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False)
    pan = Column(String(10), nullable=True)
    address = Column(Text, nullable=True)
    aadhaar_masked = Column(String(12), nullable=True)  # XXXXXXXX1234
    signing_status = Column(String(20), nullable=False, default="Pending")
    access_token = Column(String(1024), unique=True, nullable=True)
    access_token_expires_at = Column(DateTime, nullable=True)
    last_notified_at = Column(DateTime, nullable=True)
    reminder_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="parties")
    signatures = relationship("Signature", back_populates="party", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_parties_agreement", "agreement_id"),
        Index("idx_parties_token", "access_token"),
        CheckConstraint(f"party_type IN ({_sql_in(PARTY_TYPES)})", name="check_party_type"),
        CheckConstraint(f"signing_status IN ({_sql_in(SIGNING_STATUSES)})", name="check_signing_status"),
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
    invoice_number = Column(String(50), unique=True, nullable=True)
    total_amount = Column(Float, nullable=False)
    stamp_duty_amount = Column(Float, nullable=False)
    platform_fee = Column(Float, nullable=False)
    gst_amount = Column(Float, nullable=False, default=0.0)
    payment_gateway = Column(String(50), nullable=False, default="Razorpay")
    payment_mode = Column(String(30), nullable=False, default="UPI")
    gateway_payment_id = Column(String(255), unique=True, nullable=False)
    status = Column(String(20), nullable=False, default="Pending")
    invoice_pdf_url = Column(Text, nullable=True)
    paid_by_user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="payment")

    __table_args__ = (
        CheckConstraint(
            "status IN ('Pending', 'Success', 'Failed', 'Refunded')",
            name="check_payment_status"
        ),
    )


class AuditLog(Base, JsonMixin):
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
        return self._loads(self.event_data, {})

    def set_event_data(self, data: dict):
        self.event_data = json.dumps(data)


class Document(Base):
    """Content-addressed store for every PDF artifact (draft, final, invoice, 65B certificate)."""
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(String(30), nullable=False)  # DRAFT, FINAL, INVOICE, CERT_65B
    file_name = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False, default="application/pdf")
    content = Column(LargeBinary, nullable=False)
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="documents")

    __table_args__ = (
        Index("idx_documents_agreement_type", "agreement_id", "doc_type"),
        CheckConstraint("doc_type IN ('DRAFT', 'FINAL', 'INVOICE', 'CERT_65B')", name="check_doc_type"),
    )


class OtpChallenge(Base):
    """Persisted OTP challenge so rate limiting survives process/instance boundaries."""
    __tablename__ = "otp_challenges"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    subject = Column(String(255), nullable=False)  # phone (login) or party_id (eSign)
    purpose = Column(String(20), nullable=False)   # LOGIN, ESIGN
    otp_hash = Column(String(128), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    consumed = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        Index("idx_otp_subject_purpose", "subject", "purpose"),
        CheckConstraint("purpose IN ('LOGIN', 'ESIGN')", name="check_otp_purpose"),
    )


class LoginEvent(Base):
    """Security ingress journal that feeds the suspicious-login detector."""
    __tablename__ = "login_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    identifier = Column(String(255), nullable=False)  # phone/email attempted
    method = Column(String(30), nullable=False)       # OTP, PASSWORD
    ip_address = Column(String(45), nullable=False, default="127.0.0.1")
    user_agent = Column(Text, nullable=True)
    device_fingerprint = Column(String(128), nullable=True)
    geo_location = Column(String(255), nullable=True)
    success = Column(Boolean, nullable=False, default=False)
    suspicious = Column(Boolean, nullable=False, default=False)
    risk_reasons = Column(Text, nullable=False, default="[]")  # JSON list
    alert_dispatched = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=utc_now)

    user = relationship("User", back_populates="login_events")

    __table_args__ = (
        Index("idx_login_events_user", "user_id"),
    )

    def get_risk_reasons(self) -> list:
        try:
            return json.loads(self.risk_reasons or "[]")
        except ValueError:
            return []


class Notification(Base):
    """Dispatch ledger for every invitation, reminder and completion message."""
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="CASCADE"), nullable=False)
    party_id = Column(String(36), ForeignKey("parties.id", ondelete="CASCADE"), nullable=True)
    kind = Column(String(30), nullable=False)      # INVITE, REMINDER, COMPLETION, SECURITY
    channel = Column(String(30), nullable=False)   # SMS, WHATSAPP, EMAIL, ALL
    recipient = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    signing_url = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="SENT")
    triggered_by = Column(String(100), nullable=False, default="SYSTEM")
    created_at = Column(DateTime, default=utc_now)

    agreement = relationship("Agreement", back_populates="notifications")

    __table_args__ = (
        Index("idx_notifications_agreement", "agreement_id"),
    )


class Feedback(Base):
    """Net Promoter Score capture with detractor root-cause tagging."""
    __tablename__ = "feedback"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="SET NULL"), nullable=True)
    score = Column(Integer, nullable=False)
    category = Column(String(100), nullable=True)
    comment = Column(Text, nullable=True)
    sentiment = Column(String(20), nullable=False, default="Detractor")
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        CheckConstraint("score BETWEEN 0 AND 10", name="check_nps_score"),
    )


class AgentRun(Base, JsonMixin):
    """Immutable record of every AI agent invocation: goal, plan, tool calls, outcome."""
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    agent_type = Column(String(30), nullable=False)  # COPILOT, WORKFLOW, CLAUSE_RISK, INGEST
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    agreement_id = Column(String(36), ForeignKey("agreements.id", ondelete="SET NULL"), nullable=True)
    goal = Column(Text, nullable=False)
    model = Column(String(100), nullable=False, default="rule-based")
    status = Column(String(20), nullable=False, default="COMPLETED")  # COMPLETED, FAILED, NEEDS_HUMAN
    steps = Column(Text, nullable=False, default="[]")  # JSON list of {tool, input, output, ok}
    outcome = Column(Text, nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utc_now)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_agent_runs_agreement", "agreement_id"),
        CheckConstraint("status IN ('COMPLETED', 'FAILED', 'NEEDS_HUMAN', 'RUNNING')", name="check_agent_status"),
    )

    def get_steps(self) -> list:
        return self._loads(self.steps, [])

    def set_steps(self, steps: list):
        self.steps = json.dumps(steps, default=str)


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
