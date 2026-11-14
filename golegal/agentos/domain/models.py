"""
GoLegal AgentOS v1.0 Relational Data Domain (SQLAlchemy ORM).
Implements all entities and invariants specified in Section 6 of GoLegal_AgentOS_v1_Spec_Driven_PRD.md.
"""
from __future__ import annotations
import uuid
import json
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship

from golegal.domain.models import Base, utc_now


def generate_uuid() -> str:
    return str(uuid.uuid4())


class AgentPack(Base):
    """
    Code-owned and published skill pack catalog (PRD §6).
    Not editable by tenants.
    """
    __tablename__ = "agentos_agent_packs"

    key = Column(String(64), primary_key=True)  # e.g., 'contract_intelligence_v1'
    pack_version = Column(String(32), primary_key=True)  # e.g., '1.0.0'
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    skills_schema_json = Column(Text, nullable=False)  # JSON Schema for allowed configuration
    capabilities = Column(Text, nullable=False)  # JSON Array of allowed skills: search, extract, classify, compare, verify, draft
    system_policy_version = Column(String(32), default="2026-11-v1", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AgentDefinition(Base):
    """
    Agent Definition version row (PRD §6).
    Immutable once published; drafts can be modified with optimistic locking.
    """
    __tablename__ = "agentos_agent_definitions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    family_id = Column(String(64), nullable=False, index=True)  # Stable across versions
    tenant_id = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False)
    pack_key = Column(String(64), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, APPROVED, RETIRED
    goal_template = Column(Text, nullable=False)
    config_json = Column(Text, nullable=False)  # JSON configuration adhering to pack skills_schema
    created_by = Column(String(64), nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "family_id", "version", name="uq_agent_def_version"),
    )


class AgentRuntimePolicy(Base):
    """
    Tenant-level Agent Runtime limits and governance policy (PRD §4 & §6).
    """
    __tablename__ = "agentos_runtime_policies"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    name = Column(String(64), default="default_policy", nullable=False)
    version = Column(Integer, default=1, nullable=False)
    token_limit = Column(Integer, default=200000, nullable=False)
    budget_limit_minor = Column(Integer, default=50000, nullable=False)  # INR paise (default ₹500.00)
    max_tool_calls = Column(Integer, default=200, nullable=False)
    max_steps = Column(Integer, default=30, nullable=False)
    max_document_count = Column(Integer, default=50, nullable=False)
    max_document_size_mb = Column(Integer, default=10, nullable=False)
    max_aggregate_pages = Column(Integer, default=1000, nullable=False)
    max_run_age_days = Column(Integer, default=30, nullable=False)
    allowed_providers = Column(Text, default='["local_fixture", "local_gpu_rtx3060"]', nullable=False)
    data_residency = Column(String(32), default="IN", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AgentDeployment(Base):
    """
    Admin-approved immutable agent deployment bound to tenant, playbook, and data scopes (PRD §6).
    """
    __tablename__ = "agentos_agent_deployments"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    definition_id = Column(String(64), ForeignKey("agentos_agent_definitions.id"), nullable=False)
    definition_version = Column(Integer, nullable=False)
    playbook_version_id = Column(String(64), nullable=False)  # e.g., 'playbook_nda_2026_11'
    allowed_collection_ids = Column(Text, default="[]", nullable=False)  # JSON array of authorized collection IDs
    tool_grant_set_id = Column(String(64), nullable=False)
    runtime_policy_id = Column(String(64), ForeignKey("agentos_runtime_policies.id"), nullable=False)
    approved_by = Column(String(64), nullable=False)  # Must be TENANT_ADMIN
    approved_at = Column(DateTime, default=utc_now, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    state = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, SUSPENDED

    definition = relationship("AgentDefinition")
    policy = relationship("AgentRuntimePolicy")


class ToolGrant(Base):
    """
    Explicit tool privilege granted to a deployment (PRD §6).
    Cannot override platform hard denylist.
    """
    __tablename__ = "agentos_tool_grants"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    deployment_id = Column(String(64), ForeignKey("agentos_agent_deployments.id"), nullable=False, index=True)
    tool_name = Column(String(64), nullable=False)
    allowed_scopes = Column(Text, default="[]", nullable=False)  # JSON array
    side_effect_class = Column(String(32), default="READ", nullable=False)  # READ, CREATE_DRAFT, EXTERNAL
    enabled = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("deployment_id", "tool_name", name="uq_deployment_tool"),
    )


class DocumentSource(Base):
    """
    Local tenant-scoped upload intake artifact (PRD §2 & §6).
    Separate from GoLegal official legal contracts.
    """
    __tablename__ = "agentos_document_sources"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    collection_id = Column(String(64), default="col_default", nullable=False, index=True)
    name = Column(String(255), nullable=False)
    created_by = Column(String(64), nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, QUARANTINED, REJECTED
    created_at = Column(DateTime, default=utc_now, nullable=False)


class SourceRevision(Base):
    """
    Immutable source snapshot revision with byte-level hash (PRD §6).
    """
    __tablename__ = "agentos_source_revisions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    document_source_id = Column(String(64), ForeignKey("agentos_document_sources.id"), nullable=False, index=True)
    revision_no = Column(Integer, default=1, nullable=False)
    object_key = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    mime_type = Column(String(64), default="application/pdf", nullable=False)
    bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, default=1, nullable=False)
    text_extraction_status = Column(String(32), default="SUCCESS", nullable=False)  # SUCCESS, INCOMPLETE_TEXT, FAILED
    warnings_json = Column(Text, default="[]", nullable=False)
    extracted_text = Column(Text, nullable=True)  # Normalized text stored with parser version
    created_at = Column(DateTime, default=utc_now, nullable=False)

    source = relationship("DocumentSource", backref="revisions")
    __table_args__ = (
        UniqueConstraint("document_source_id", "revision_no", name="uq_source_revision_no"),
    )


class Mission(Base):
    """
    Long-running durable mission instance (PRD §6 & §7).
    """
    __tablename__ = "agentos_missions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    deployment_id = Column(String(64), ForeignKey("agentos_agent_deployments.id"), nullable=False)
    definition_version = Column(Integer, nullable=False)
    goal = Column(Text, nullable=False)
    requested_by = Column(String(64), nullable=False)
    status = Column(String(32), default="CREATED", nullable=False)
    # State machine: CREATED, PLANNING, AWAITING_SCOPE_APPROVAL, RUNNING, AWAITING_REVIEW, PAUSED, DELIVERED, COMPLETED, CANCELLED, FAILED
    workflow_id = Column(String(128), unique=True, nullable=False)
    input_manifest_sha256 = Column(String(64), nullable=False)
    budget_limit_minor = Column(Integer, nullable=False)  # INR paise ceiling
    idempotency_key = Column(String(128), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    closed_at = Column(DateTime, nullable=True)

    deployment = relationship("AgentDeployment")
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_mission_tenant_idemp"),
    )


class MissionInput(Base):
    """
    Snapshot of input source revision pinned to a mission (PRD §6).
    """
    __tablename__ = "agentos_mission_inputs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    source_id = Column(String(64), nullable=False)
    source_revision_id = Column(String(64), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    source_kind = Column(String(32), default="PDF_UPLOAD", nullable=False)  # PDF_UPLOAD, GOLEGAL_CONTRACT
    source_access_snapshot = Column(Text, default="{}", nullable=False)  # JSON

    mission = relationship("Mission", backref="inputs")
    __table_args__ = (
        UniqueConstraint("mission_id", "source_revision_id", name="uq_mission_input_rev"),
    )


class MissionPlan(Base):
    """
    Bounded explicit plan proposed by planner and decided by supervisor (PRD §6 & §7).
    """
    __tablename__ = "agentos_mission_plans"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    plan_json = Column(Text, nullable=False)  # Array of PlanV1 tasks
    plan_sha256 = Column(String(64), nullable=False)
    status = Column(String(32), default="PROPOSED", nullable=False)  # PROPOSED, APPROVED, REJECTED
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="plans")


class MissionTask(Base):
    """
    Durable scheduled activity task within a plan (PRD §6).
    """
    __tablename__ = "agentos_mission_tasks"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    plan_version = Column(Integer, default=1, nullable=False)
    task_key = Column(String(64), nullable=False)  # e.g., 'task_extract_01'
    skill_name = Column(String(64), nullable=False)
    deps_json = Column(Text, default="[]", nullable=False)  # Task keys this task depends on
    state = Column(String(32), default="PENDING", nullable=False)  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    attempt_count = Column(Integer, default=0, nullable=False)
    output_object_key = Column(String(255), nullable=True)
    idempotency_key = Column(String(128), unique=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="tasks")


class Approval(Base):
    """
    Human supervisor approval gate (PRD §6 & §7).
    """
    __tablename__ = "agentos_approvals"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    task_id = Column(String(64), nullable=True)
    kind = Column(String(32), default="SCOPE", nullable=False)  # SCOPE, FINDING, REPORT
    subject_sha256 = Column(String(64), nullable=False)
    requested_role = Column(String(64), default="MISSION_OPERATOR", nullable=False)
    expires_at = Column(DateTime, nullable=False)
    state = Column(String(32), default="PENDING", nullable=False)  # PENDING, APPROVED, REJECTED, EXPIRED
    actor_id = Column(String(64), nullable=True)
    reason = Column(Text, nullable=True)
    decision_version = Column(Integer, default=1, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="approvals")


class SourceSpan(Base):
    """
    Exact character slice & page coordinate evidence anchor (PRD §6 & §9).
    """
    __tablename__ = "agentos_source_spans"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    source_revision_id = Column(String(64), nullable=False, index=True)
    source_sha256 = Column(String(64), nullable=False)
    page_index_0 = Column(Integer, nullable=False)
    char_start = Column(Integer, nullable=False)
    char_end = Column(Integer, nullable=False)
    verbatim_excerpt = Column(Text, nullable=False)
    excerpt_sha256 = Column(String(64), nullable=False)
    extraction_method = Column(String(32), default="PYMUPDF_EXACT", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)


class AgentFinding(Base):
    """
    Contract intelligence candidate deviation / finding (PRD §6 & §9).
    """
    __tablename__ = "agentos_findings"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    source_span_id = Column(String(64), ForeignKey("agentos_source_spans.id"), nullable=False)
    playbook_rule_id = Column(String(64), nullable=False)  # e.g., 'NDA-TERM-04'
    playbook_version = Column(String(32), default="2026-11-v1", nullable=False)
    category = Column(String(64), nullable=False)  # e.g., 'confidentiality_duration', 'governing_law'
    severity = Column(String(32), default="REVIEW", nullable=False)  # INFO, REVIEW, HIGH
    statement = Column(Text, nullable=False)
    verification_state = Column(String(32), default="CANDIDATE", nullable=False)  # CANDIDATE, VERIFIED, UNSUPPORTED, STALE
    review_state = Column(String(32), default="OPEN", nullable=False)  # OPEN, ACCEPTED, REJECTED
    reviewed_by = Column(String(64), nullable=True)  # LEGAL_REVIEWER actor ID
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="findings")
    span = relationship("SourceSpan")


# Alias for backward compatibility within AgentOS module
Finding = AgentFinding


class ToolInvocation(Base):
    """
    Execution trace for every tool dispatched by policy gateway (PRD §6).
    """
    __tablename__ = "agentos_tool_invocations"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    task_id = Column(String(64), nullable=True)
    tool_name = Column(String(64), nullable=False)
    grant_version = Column(Integer, default=1, nullable=False)
    input_sha256 = Column(String(64), nullable=False)
    outcome = Column(String(32), default="SUCCESS", nullable=False)  # SUCCESS, DENIED, FAILED
    duration_ms = Column(Integer, default=0, nullable=False)
    usage_json = Column(Text, default="{}", nullable=False)
    external_request_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="tool_invocations")


class BudgetLedgerEntry(Base):
    """
    Atomic INR paise cost reservation and settlement ledger (PRD §6).
    """
    __tablename__ = "agentos_budget_ledger"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    reservation_id = Column(String(64), unique=True, nullable=False)
    provider = Column(String(64), default="local_gpu_rtx3060", nullable=False)
    model = Column(String(64), default="qwen_contract_extractor", nullable=False)
    tokens_in = Column(Integer, default=0, nullable=False)
    tokens_out = Column(Integer, default=0, nullable=False)
    estimated_cost_minor = Column(Integer, default=0, nullable=False)  # Paise reserved
    actual_cost_minor = Column(Integer, nullable=True)  # Paise settled
    status = Column(String(32), default="RESERVED", nullable=False)  # RESERVED, SETTLED, RELEASED
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="ledger_entries")


class Artifact(Base):
    """
    Immutable mission output artifact (PRD §6).
    """
    __tablename__ = "agentos_artifacts"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)  # REPORT_MARKDOWN, REPORT_JSON, MANIFEST, EXTRACT
    object_key = Column(String(255), nullable=False)
    sha256 = Column(String(64), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    content = Column(Text, nullable=False)  # Stored text/JSON payload
    created_by = Column(String(64), nullable=False)
    review_status = Column(String(32), default="DRAFT", nullable=False)  # DRAFT, REVIEWED, REJECTED
    created_at = Column(DateTime, default=utc_now, nullable=False)

    mission = relationship("Mission", backref="artifacts")


class MissionEvent(Base):
    """
    Append-only cryptographically chained audit event (H_n = SHA256(H_{n-1} || payload)) (PRD §6).
    """
    __tablename__ = "agentos_mission_events"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    mission_id = Column(String(64), ForeignKey("agentos_missions.id"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    type = Column(String(64), nullable=False)
    actor_type = Column(String(32), default="HUMAN", nullable=False)  # HUMAN, SYSTEM, POLICY
    actor_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    redacted_payload_json = Column(Text, default="{}", nullable=False)
    prev_event_hash = Column(String(64), nullable=False)
    event_hash = Column(String(64), nullable=False)

    mission = relationship("Mission", backref="events")
    __table_args__ = (
        UniqueConstraint("mission_id", "seq", name="uq_mission_event_seq"),
    )


class WatchSubscription(Base):
    """
    P1 event watch subscription on contract revisions (PRD §6 & §7).
    """
    __tablename__ = "agentos_watch_subscriptions"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(64), nullable=False, index=True)
    deployment_id = Column(String(64), ForeignKey("agentos_agent_deployments.id"), nullable=False)
    collection_id = Column(String(64), nullable=False)
    event_type = Column(String(64), default="contract.revision.created", nullable=False)
    status = Column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, PAUSED
    last_processed_event_id = Column(String(64), nullable=True)
    created_by = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
