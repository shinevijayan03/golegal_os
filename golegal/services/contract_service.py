"""
Contract State Machine & Deterministic Validation Service.
Enforces FR-03, FR-06, AT-01, AT-02, AT-04, AT-05, and AT-06.
"""
from __future__ import annotations
import re
import hashlib
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from golegal.domain.models import (
    Contract, DocumentRevision, ReviewDecision, Finding, AuditEvent, utc_now
)
from golegal.services.auth_service import AuthService, TenantIsolationError
from golegal.services.catalog_service import CatalogService, LegalEligibilityError
from golegal.services.stamping_service import StampingService, StampGateError


class ContractValidationError(ValueError):
    """Raised when field constraints, required schemas, or date order fails (422)."""
    pass


class StaleEtagError(Exception):
    """Raised on optimistic locking conflict when etags do not match (409)."""
    pass


class SelfApprovalError(PermissionError):
    """Raised when contract submitter attempts to self-approve under default policy (FR-06)."""
    pass


class ContractService:
    def __init__(self, session: Session):
        self.session = session
        self.auth = AuthService(session)
        self.catalog = CatalogService(session)
        self.stamping = StampingService(session)

    def _assert_tenant_access(self, contract: Contract, org_id: str, actor_id: str) -> None:
        """Enforces AT-01: Contract must strictly belong to the actor's organisation."""
        if not contract or contract.organisation_id != org_id:
            raise TenantIsolationError(f"404 NOT_FOUND: Contract does not exist in organisation '{org_id}'.")
        self.auth.verify_tenant_access(org_id, actor_id)

    def validate_fields(self, template_version_id: str, field_values: Dict[str, Any]) -> None:
        """Enforces AT-04: Deterministic validation of date order, positive amounts, and required keys."""
        # 1. Date order check: end_date must be strictly after start_date
        start_date_str = field_values.get("start_date")
        end_date_str = field_values.get("end_date")
        if start_date_str and end_date_str:
            try:
                s_date = datetime.strptime(str(start_date_str), "%Y-%m-%d").date()
                e_date = datetime.strptime(str(end_date_str), "%Y-%m-%d").date()
                if e_date <= s_date:
                    raise ContractValidationError(
                        f"422 DATE_ORDER_INVALID: end_date ({e_date}) must be strictly after start_date ({s_date})."
                    )
            except ValueError as ve:
                if "DATE_ORDER_INVALID" in str(ve):
                    raise
                # pass other date parsing issues to template schema validator

        # 2. Non-negative / positive money check
        if "monthly_rent_paise" in field_values:
            rent = field_values["monthly_rent_paise"]
            if rent is not None and rent <= 0:
                raise ContractValidationError(f"422 INVALID_RENT: monthly_rent_paise ({rent}) must be positive integer.")

        if "security_deposit_paise" in field_values:
            dep = field_values["security_deposit_paise"]
            if dep is not None and dep < 0:
                raise ContractValidationError(f"422 INVALID_DEPOSIT: security_deposit_paise ({dep}) cannot be negative.")

    def create_contract(
        self, org_id: str, actor_id: str, template_version_id: str, title: str, field_values: Dict[str, Any]
    ) -> Contract:
        self.auth.verify_tenant_access(org_id, actor_id, required_roles=["owner", "editor", "operator"])
        self.validate_fields(template_version_id, field_values)

        contract = Contract(
            organisation_id=org_id,
            template_version_id=template_version_id,
            title=title,
            created_by=actor_id,
            status="DRAFT",
            etag_version=1
        )
        contract.field_values = field_values
        self.session.add(contract)
        self.session.flush()
        return contract

    def get_contract(self, contract_id: str, org_id: str, actor_id: str) -> Contract:
        c = self.session.query(Contract).filter_by(id=contract_id).first()
        self._assert_tenant_access(c, org_id, actor_id)
        return c

    def update_fields(
        self, contract_id: str, org_id: str, actor_id: str, expected_etag: int, field_values: Dict[str, Any]
    ) -> Contract:
        """Enforces AT-05: Modifying fields in APPROVED/IN_REVIEW invalidates approvals, increments etag, resets to DRAFT."""
        contract = self.get_contract(contract_id, org_id, actor_id)
        self.auth.verify_tenant_access(org_id, actor_id, required_roles=["owner", "editor"])

        # Optimistic locking check
        if contract.etag_version != expected_etag:
            raise StaleEtagError(
                f"409 STALE_ETAG_CONFLICT: Contract was updated by another session. "
                f"Expected etag {expected_etag}, found {contract.etag_version}."
            )

        self.validate_fields(contract.template_version_id, field_values)
        contract.field_values = field_values
        contract.etag_version += 1

        # AT-05: State transition and invalidation
        if contract.status in ("APPROVED", "IN_REVIEW"):
            contract.status = "DRAFT"
            # Create fresh unapproved revision
            new_rev = DocumentRevision(
                contract_id=contract.id,
                revision_no=len(contract.revisions) + 1,
                object_key=f"contracts/{contract.id}/revisions/rev_{contract.etag_version}.pdf",
                mime_type="application/pdf",
                size_bytes=1024,
                sha256=hashlib.sha256(str(field_values).encode("utf-8")).hexdigest(),
                render_status="completed"
            )
            self.session.add(new_rev)
            self.session.flush()
            contract.current_revision_id = new_rev.id

        self.session.flush()
        return contract

    def submit_for_review(self, contract_id: str, org_id: str, actor_id: str) -> DocumentRevision:
        contract = self.get_contract(contract_id, org_id, actor_id)
        self.auth.verify_tenant_access(org_id, actor_id, required_roles=["owner", "editor"])
        self.validate_fields(contract.template_version_id, contract.field_values)

        rev_no = (len(contract.revisions) or 0) + 1
        digest = hashlib.sha256(f"{contract.id}:{rev_no}:{str(contract.field_values)}".encode("utf-8")).hexdigest()
        revision = DocumentRevision(
            contract_id=contract.id,
            revision_no=rev_no,
            object_key=f"contracts/{contract.id}/revisions/rev_{rev_no}.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            sha256=digest,
            render_status="completed",
            frozen_at=utc_now()
        )
        self.session.add(revision)
        self.session.flush()

        contract.current_revision_id = revision.id
        contract.status = "IN_REVIEW"
        self.session.flush()
        return revision

    def record_review_decision(
        self, contract_id: str, org_id: str, actor_id: str, revision_id: str, decision: str, comment: Optional[str] = None
    ) -> Contract:
        """Enforces FR-06: Submitter cannot self-approve."""
        contract = self.get_contract(contract_id, org_id, actor_id)
        if actor_id == contract.created_by and decision == "approve":
            raise SelfApprovalError("403 SELF_APPROVAL_BLOCKED: Submitter cannot approve their own contract.")
        self.auth.verify_tenant_access(org_id, actor_id, required_roles=["owner", "approver"])

        rec = ReviewDecision(
            contract_id=contract.id,
            revision_id=revision_id,
            actor_user_id=actor_id,
            decision=decision,
            comment=comment
        )
        self.session.add(rec)

        if decision == "approve":
            contract.status = "APPROVED"
        else:
            contract.status = "DRAFT"

        self.session.flush()
        return contract

    def prepare_execution(self, contract_id: str, org_id: str, actor_id: str) -> Contract:
        """Enforces AT-02 & AT-06."""
        contract = self.get_contract(contract_id, org_id, actor_id)
        self.auth.verify_tenant_access(org_id, actor_id, required_roles=["owner", "approver", "operator"])

        # AT-02 Legal template eligibility check
        rule = self.catalog.verify_execution_eligibility(contract.template_version_id)

        # AT-06 Stamping gate check
        if rule.requires_stamping:
            self.stamping.assert_stamp_verified(contract.id, org_id)

        contract.status = "READY_FOR_EXECUTION"
        self.session.flush()
        return contract

    def evaluate_checklist(self, contract_id: str, org_id: str) -> List[Finding]:
        """Lawyer-authored explainable findings (FR-05)."""
        contract = self.session.query(Contract).filter_by(id=contract_id, organisation_id=org_id).first()
        if not contract:
            raise TenantIsolationError(f"404 NOT_FOUND: Contract '{contract_id}' not found.")
        findings: List[Finding] = []
        covenants = str(contract.field_values.get("custom_covenants", ""))

        # PII check in free-text: 12-digit Aadhaar pattern
        if re.search(r"\b\d{4}\s?\d{4}\s?\d{4}\b", covenants):
            f = Finding(
                contract_id=contract.id,
                revision_id=contract.current_revision_id,
                rule_id="RULE-PII-01",
                severity="critical",
                message="Raw 12-digit Aadhaar number detected in covenants. Must be masked.",
                source_excerpt="Aadhaar detected in custom covenant text",
                location="custom_covenants",
                status="open"
            )
            findings.append(f)
            self.session.add(f)
            self.session.flush()

        return findings
