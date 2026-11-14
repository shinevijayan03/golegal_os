"""
GoLegal vNext Domain Entities (SQLAlchemy 2.0).
14 Mandatory Entities strictly partitioned by organisation_id.
"""
from __future__ import annotations
import uuid
import json
from datetime import datetime, timezone, date
from typing import Optional, Dict, Any

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, ForeignKey, Text, UniqueConstraint, event
)
from sqlalchemy.orm import relationship

from golegal.db.session import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def gen_uuid() -> str:
    return str(uuid.uuid4())


# ----------------------------------------------------------------------------
# 1. Organisation (Tenant Root)
# ----------------------------------------------------------------------------
class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    status = Column(String(32), default="active", nullable=False)

    memberships = relationship("Membership", back_populates="organisation", cascade="all, delete-orphan")
    contracts = relationship("Contract", back_populates="organisation")
    audit_events = relationship("AuditEvent", back_populates="organisation")
    ai_policy = relationship("AIProcessingPolicy", back_populates="organisation", uselist=False)


# ----------------------------------------------------------------------------
# 2. Membership (Tenant-scoped RBAC)
# ----------------------------------------------------------------------------
class Membership(Base):
    __tablename__ = "memberships"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    organisation_id = Column(String(36), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(64), nullable=False)
    user_email = Column(String(255), nullable=True)
    role = Column(String(32), nullable=False)  # owner, editor, approver, counterparty_signer, legal_admin, operator
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    organisation = relationship("Organisation", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint("organisation_id", "user_id", name="uq_org_user"),
    )


# ----------------------------------------------------------------------------
# 3. TemplateVersion (Immutable Published Catalogue)
# ----------------------------------------------------------------------------
class TemplateVersion(Base):
    __tablename__ = "template_versions"

    id = Column(String(64), primary_key=True)  # e.g., tpl_ka_rental_v1
    agreement_type = Column(String(64), nullable=False)
    jurisdiction_code = Column(String(16), nullable=False)
    version = Column(String(32), nullable=False)
    state = Column(String(32), default="draft", nullable=False)  # draft, legal_approved, retired
    schema_json_raw = Column("schema_json", Text, nullable=False, default="{}")
    object_key = Column(String(255), nullable=True)
    sha256 = Column(String(64), nullable=True)
    approved_by = Column(String(64), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    eligibility_rules = relationship("EligibilityRule", back_populates="template_version")

    @property
    def schema_json(self) -> Dict[str, Any]:
        return json.loads(self.schema_json_raw or "{}")

    @schema_json.setter
    def schema_json(self, value: Dict[str, Any]) -> None:
        self.schema_json_raw = json.dumps(value)


# ----------------------------------------------------------------------------
# 4. EligibilityRule (Statutory Execution & Stamping Gates)
# ----------------------------------------------------------------------------
class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    template_version_id = Column(String(64), ForeignKey("template_versions.id"), nullable=False)
    document_type = Column(String(64), nullable=False)
    jurisdiction_code = Column(String(16), nullable=False)
    execution_mode = Column(String(32), default="draft_only", nullable=False)  # draft_only, provider_allowed, blocked
    requires_stamping = Column(Boolean, default=True, nullable=False)
    requires_registration_review = Column(Boolean, default=True, nullable=False)
    rule_version = Column(String(32), default="1.0.0", nullable=False)
    legal_approver = Column(String(255), nullable=True)
    effective_from = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    template_version = relationship("TemplateVersion", back_populates="eligibility_rules")


# ----------------------------------------------------------------------------
# 5. Contract (Lifecycle Root with Optimistic Lock)
# ----------------------------------------------------------------------------
class Contract(Base):
    __tablename__ = "contracts"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    organisation_id = Column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    template_version_id = Column(String(64), ForeignKey("template_versions.id"), nullable=False, index=True)
    status = Column(String(32), default="DRAFT", nullable=False, index=True)
    # Statuses: DRAFT, IN_REVIEW, APPROVED, READY_FOR_EXECUTION, SIGN_PENDING, EXECUTED, MOCK_COMPLETED, ARCHIVED, CANCELLED
    title = Column(String(255), nullable=False)
    field_values_raw = Column("field_values", Text, nullable=False, default="{}")
    created_by = Column(String(64), nullable=False)
    current_revision_id = Column(String(36), nullable=True)
    etag_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organisation = relationship("Organisation", back_populates="contracts")
    revisions = relationship("DocumentRevision", back_populates="contract", foreign_keys="DocumentRevision.contract_id")
    review_decisions = relationship("ReviewDecision", back_populates="contract")
    execution_requests = relationship("ExecutionRequest", back_populates="contract")
    stamp_records = relationship("StampRecord", back_populates="contract")
    field_candidates = relationship("FieldCandidate", back_populates="contract")
    findings = relationship("Finding", back_populates="contract")
    reminders = relationship("Reminder", back_populates="contract")
    audit_events = relationship("AuditEvent", back_populates="contract")

    @property
    def field_values(self) -> Dict[str, Any]:
        return json.loads(self.field_values_raw or "{}")

    @field_values.setter
    def field_values(self, val: Dict[str, Any]) -> None:
        self.field_values_raw = json.dumps(val)


# ----------------------------------------------------------------------------
# 6. DocumentRevision (Frozen Immutable Artifact)
# ----------------------------------------------------------------------------
class DocumentRevision(Base):
    __tablename__ = "document_revisions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    revision_no = Column(Integer, nullable=False, default=1)
    object_key = Column(String(255), nullable=False)
    mime_type = Column(String(64), default="application/pdf", nullable=False)
    size_bytes = Column(Integer, default=0, nullable=False)
    sha256 = Column(String(64), nullable=False)
    render_status = Column(String(32), default="completed", nullable=False)
    frozen_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    contract = relationship("Contract", back_populates="revisions", foreign_keys=[contract_id])


# ----------------------------------------------------------------------------
# 7. ReviewDecision (Approver Sign-Off Trace)
# ----------------------------------------------------------------------------
class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    revision_id = Column(String(36), ForeignKey("document_revisions.id"), nullable=False)
    actor_user_id = Column(String(64), nullable=False)
    decision = Column(String(32), nullable=False)  # approve, reject
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    contract = relationship("Contract", back_populates="review_decisions")
    revision = relationship("DocumentRevision")


# ----------------------------------------------------------------------------
# 8. ExecutionRequest (Mock/Live Outbox & Idempotency)
# ----------------------------------------------------------------------------
class ExecutionRequest(Base):
    __tablename__ = "execution_requests"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    revision_id = Column(String(36), ForeignKey("document_revisions.id"), nullable=False)
    provider_key = Column(String(64), default="mock_esign", nullable=False)
    provider_request_id = Column(String(128), unique=True, nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    mode = Column(String(16), default="mock", nullable=False)  # mock, live
    status = Column(String(32), default="PENDING", nullable=False)  # PENDING, MOCK_COMPLETED, EXECUTED, FAILED
    signed_object_key = Column(String(255), nullable=True)
    signed_sha256 = Column(String(64), nullable=True)
    provider_receipt_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    contract = relationship("Contract", back_populates="execution_requests")
    revision = relationship("DocumentRevision")

    __table_args__ = (
        UniqueConstraint("contract_id", "idempotency_key", name="uq_contract_idemp"),
    )


# ----------------------------------------------------------------------------
# 9. StampRecord (Verified Stamping State)
# ----------------------------------------------------------------------------
class StampRecord(Base):
    __tablename__ = "stamp_records"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    status = Column(String(32), default="required_unverified", nullable=False)  # not_required, required_unverified, verified, failed
    amount_paise = Column(Integer, nullable=True)
    currency = Column(String(8), default="INR", nullable=False)
    jurisdiction_code = Column(String(16), default="KA", nullable=False)
    verified_by = Column(String(64), nullable=True)
    receipt_object_key = Column(String(255), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    contract = relationship("Contract", back_populates="stamp_records")


# ----------------------------------------------------------------------------
# 10. FieldCandidate (Extracted OCR Review Queue)
# ----------------------------------------------------------------------------
class FieldCandidate(Base):
    __tablename__ = "field_candidates"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    revision_id = Column(String(36), ForeignKey("document_revisions.id"), nullable=True)
    field_key = Column(String(128), nullable=False)
    candidate_value = Column(Text, nullable=False)
    source_page = Column(Integer, default=1, nullable=False)
    source_excerpt = Column(Text, nullable=True)
    parser_name = Column(String(64), default="gpu_ocr", nullable=False)
    review_status = Column(String(32), default="proposed", nullable=False)  # proposed, accepted, rejected
    reviewed_by = Column(String(64), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    contract = relationship("Contract", back_populates="field_candidates")
    revision = relationship("DocumentRevision")


# ----------------------------------------------------------------------------
# 11. Finding (Deterministic Lawyer-Authored Rule Checklist)
# ----------------------------------------------------------------------------
class Finding(Base):
    __tablename__ = "findings"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    revision_id = Column(String(36), ForeignKey("document_revisions.id"), nullable=True)
    rule_id = Column(String(64), nullable=False)
    severity = Column(String(16), default="info", nullable=False)  # info, review, critical
    message = Column(Text, nullable=False)
    source_excerpt = Column(Text, nullable=True)
    location = Column(String(128), nullable=True)
    status = Column(String(32), default="open", nullable=False)  # open, acknowledged, resolved, waived
    reviewer_id = Column(String(64), nullable=True)

    contract = relationship("Contract", back_populates="findings")
    revision = relationship("DocumentRevision")


# ----------------------------------------------------------------------------
# 12. AuditEvent (INSERT-ONLY Hash-Chained Log)
# ----------------------------------------------------------------------------
class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    organisation_id = Column(String(36), ForeignKey("organisations.id"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=True, index=True)
    actor_id = Column(String(64), nullable=True)
    event_type = Column(String(64), nullable=False)
    occurred_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    request_id = Column(String(64), nullable=False)
    object_hash = Column(String(64), nullable=True)
    payload_redacted_raw = Column("payload_redacted", Text, nullable=False, default="{}")
    previous_hash = Column(String(64), nullable=False)
    event_hash = Column(String(64), nullable=False)

    organisation = relationship("Organisation", back_populates="audit_events")
    contract = relationship("Contract", back_populates="audit_events")

    @property
    def payload_redacted(self) -> Dict[str, Any]:
        return json.loads(self.payload_redacted_raw or "{}")

    @payload_redacted.setter
    def payload_redacted(self, val: Dict[str, Any]) -> None:
        self.payload_redacted_raw = json.dumps(val)


# Immutability triggers on AuditEvent (AT-10)
@event.listens_for(AuditEvent, "before_update")
def _block_audit_update(mapper, connection, target):
    raise PermissionError("AUDIT_MUTATION_BLOCKED: AuditEvent records are append-only and strictly immutable.")


@event.listens_for(AuditEvent, "before_delete")
def _block_audit_delete(mapper, connection, target):
    raise PermissionError("AUDIT_DELETION_BLOCKED: AuditEvent records cannot be deleted.")


# ----------------------------------------------------------------------------
# 13. Reminder (Deduplicated Lifecycle Expiries)
# ----------------------------------------------------------------------------
class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False)
    kind = Column(String(64), nullable=False)  # renewal, notice_period, payment_due
    event_date = Column(Date, nullable=False)
    send_at_utc = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), default="scheduled", nullable=False)
    dedupe_key = Column(String(128), unique=True, nullable=False)
    source_field_confirmed = Column(Boolean, default=True, nullable=False)

    contract = relationship("Contract", back_populates="reminders")


# ----------------------------------------------------------------------------
# 14. AIProcessingPolicy (Tenant-Configured Privacy Controls)
# ----------------------------------------------------------------------------
class AIProcessingPolicy(Base):
    __tablename__ = "ai_processing_policies"

    organisation_id = Column(String(36), ForeignKey("organisations.id"), primary_key=True)
    third_party_ai_enabled = Column(Boolean, default=False, nullable=False)
    provider_allowlist_raw = Column("provider_allowlist", Text, default="[]", nullable=False)
    data_use_basis_record = Column(String(255), default="CONSENT_RECORD_DEFAULT_OFF", nullable=False)
    retention_policy_id = Column(String(64), default="RETENTION_27_DAYS", nullable=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    organisation = relationship("Organisation", back_populates="ai_policy")

    @property
    def provider_allowlist(self) -> list:
        return json.loads(self.provider_allowlist_raw or "[]")

    @provider_allowlist.setter
    def provider_allowlist(self, val: list) -> None:
        self.provider_allowlist_raw = json.dumps(val)
