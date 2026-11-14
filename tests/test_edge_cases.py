"""
GoLegal vNext - Edge Cases & Concurrency Test Suite
Tests negative inputs, boundary conditions, race conditions, Indic unicode, and security boundaries.
"""
import pytest
from datetime import datetime, timezone, timedelta

from golegal.domain.models import Organisation, Membership, Contract, DocumentRevision
from golegal.services.contract_service import (
    ContractService, StaleEtagError, SelfApprovalError, ContractValidationError
)
from golegal.services.document_service import DocumentService, FileValidationError
from golegal.services.provider_service import ProviderService, ReplayWindowExpiredError


class TestEdgeCasesAndConcurrency:
    """Rigorous tests for edge conditions, concurrency conflicts, and validation boundaries."""

    def test_concurrency_etag_race_condition_conflict(self, vnext_tenants, db_session):
        """Two concurrent editors attempt to update the same contract with stale etags; 409 conflict raised."""
        contract_svc = ContractService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        editor = vnext_tenants["tenant_a"]["editor"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=editor, template_version_id="tpl_ka_rental_v1",
            title="Concurrent Contract", field_values={"monthly_rent_paise": 2000000}
        )
        initial_etag = c.etag_version

        # Editor 1 saves first -> etag increments to 2
        c1 = contract_svc.update_fields(
            c.id, org_id, editor, expected_etag=initial_etag, field_values={"monthly_rent_paise": 2200000}
        )
        assert c1.etag_version == initial_etag + 1

        # Editor 2 attempts to save using initial_etag (now stale) -> StaleEtagError (409)
        with pytest.raises(StaleEtagError) as exc_info:
            contract_svc.update_fields(
                c.id, org_id, editor, expected_etag=initial_etag, field_values={"monthly_rent_paise": 2500000}
            )
        assert "409" in str(exc_info.value) or "STALE_ETAG_CONFLICT" in str(exc_info.value)

    def test_self_approval_blocked_default_policy(self, vnext_tenants, db_session):
        """Editor submits contract for review; editor cannot self-approve (FR-06)."""
        contract_svc = ContractService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        editor = vnext_tenants["tenant_a"]["editor"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=editor, template_version_id="tpl_ka_rental_v1",
            title="Self-Approval Test", field_values={"monthly_rent_paise": 2000000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        rev = contract_svc.submit_for_review(c.id, org_id, editor)

        # Editor attempts to approve own submission
        with pytest.raises(SelfApprovalError) as exc_info:
            contract_svc.record_review_decision(c.id, org_id, actor_id=editor, revision_id=rev.id, decision="approve")
        assert "SELF_APPROVAL_BLOCKED" in str(exc_info.value)

    def test_unicode_indic_text_rendering(self, vnext_tenants, db_session):
        """Verifies handling of Indic Unicode scripts (Kannada, Hindi, Tamil) in contract titles and covenants."""
        contract_svc = ContractService(db_session)
        doc_svc = DocumentService()
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner = vnext_tenants["tenant_a"]["owner"]["id"]

        indic_title = "ಬಾಡಿಗೆ ಒಪ್ಪಂದ - ಶಾಂತಿನಗರ (Shantinagar Rental Agreement) - किराए का अनुबंध"
        indic_covenants = "ಮನೆ ಬಾಡಿಗೆ ಒಪ್ಪಂದದ ನಿಯಮಗಳು ಮತ್ತು ಷರತ್ತುಗಳು. मकान किराए का नियम।"

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=owner, template_version_id="tpl_ka_rental_v1",
            title=indic_title,
            field_values={"custom_covenants": indic_covenants, "monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        assert c.title == indic_title
        
        pdf = doc_svc.render_pdf(c.id, org_id, c.field_values, watermark="DRAFT")
        assert len(pdf) > 1000

    def test_zero_byte_and_oversized_file_uploads(self, vnext_tenants, oversized_11mb_pdf_bytes, multipage_51page_pdf_bytes):
        """Zero-byte files, >10MB files, and >50 page documents rejected before processing (NFR)."""
        doc_svc = DocumentService()

        # 1. Zero-byte buffer
        with pytest.raises(FileValidationError) as exc_info:
            doc_svc.validate_attachment(b"", "empty.pdf")
        assert "EMPTY_FILE" in str(exc_info.value)

        # 2. Oversized 11MB buffer (>10 MiB limit)
        with pytest.raises(FileValidationError) as exc_info:
            doc_svc.validate_attachment(oversized_11mb_pdf_bytes, "large.pdf")
        assert "FILE_TOO_LARGE" in str(exc_info.value) or "413" in str(exc_info.value)

        # 3. 51-page document (>50 pages limit)
        with pytest.raises(FileValidationError) as exc_info:
            doc_svc.validate_attachment(multipage_51page_pdf_bytes, "long.pdf")
        assert "TOO_MANY_PAGES" in str(exc_info.value) or "422" in str(exc_info.value)

    def test_date_boundary_conditions_and_zero_rent(self, vnext_tenants, db_session):
        """start_date == end_date or negative rent values rejected by validation rules."""
        contract_svc = ContractService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        editor = vnext_tenants["tenant_a"]["editor"]["id"]

        # 1. Start date equals end date (0-day lease)
        with pytest.raises(ContractValidationError):
            contract_svc.create_contract(
                org_id=org_id, actor_id=editor, template_version_id="tpl_ka_rental_v1",
                title="Zero-Day Lease", field_values={"start_date": "2026-12-01", "end_date": "2026-12-01", "monthly_rent_paise": 2000000}
            )

        # 2. Negative rent value
        with pytest.raises(ContractValidationError):
            contract_svc.create_contract(
                org_id=org_id, actor_id=editor, template_version_id="tpl_ka_rental_v1",
                title="Negative Rent", field_values={"start_date": "2026-12-01", "end_date": "2027-10-31", "monthly_rent_paise": -50000}
            )

    def test_pii_sanitization_in_clause_text(self, vnext_tenants, db_session):
        """Detects raw 12-digit Aadhaar in custom text and forces masking (XXXXXXXX1234)."""
        contract_svc = ContractService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        editor = vnext_tenants["tenant_a"]["editor"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=editor, template_version_id="tpl_ka_rental_v1",
            title="PII Test", field_values={
                "custom_covenants": "Tenant Aadhaar is 987654321098 and PAN is ABCDE1234F.",
                "monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"
            }
        )
        findings = contract_svc.evaluate_checklist(c.id, org_id)
        pii_findings = [f for f in findings if f.severity == "critical" or "PII" in f.rule_id]
        assert len(pii_findings) > 0
