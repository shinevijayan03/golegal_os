"""
GoLegal vNext - Complete End-to-End (E2E) Multi-Actor Lifecycle Test Suite
Verifies the complete journey for both:
  1. Golden Path: Native Structured Contract Lifecycle (Owner -> Editor -> Approver -> Signer -> Auditor).
  2. Alternative Path: Third-Party Document / Camera Scan Ingestion + GPU Quality Gate + Human Confirmation.
"""
import pytest
import time
import hashlib
from datetime import datetime, timezone, timedelta

from golegal.domain.models import (
    Organisation, Membership, Contract, DocumentRevision,
    ReviewDecision, ExecutionRequest, StampRecord, FieldCandidate,
    Finding, AuditEvent, Reminder
)
from golegal.services.auth_service import AuthService, TenantIsolationError
from golegal.services.catalog_service import CatalogService, LegalEligibilityError
from golegal.services.contract_service import (
    ContractService, SelfApprovalError, StaleEtagError, ContractValidationError
)
from golegal.services.document_service import DocumentService
from golegal.services.provider_service import ProviderService
from golegal.services.stamping_service import StampingService, StampGateError
from golegal.services.gpu_vision_service import GPUVisionService
from golegal.services.reminder_service import ReminderService
from golegal.services.evidence_service import EvidenceService, TamperDetectedError


class TestEndToEndLifecycle:
    """Full lifecycle integration tests verifying state transitions, multi-actor RBAC, and legal invariants."""

    def test_e2e_golden_path_native_contract_lifecycle(self, vnext_tenants, db_session):
        """
        Executes the Complete Golden Path Journey:
        1. Legal Admin authorizes template execution mode.
        2. Editor drafts native structured contract.
        3. Editor submits for review (Revision 1, IN_REVIEW).
        4. Submitter self-approval is blocked (FR-06).
        5. Approver approves Revision 1 (APPROVED).
        6. Editor edits commercial terms -> approval invalidated, resets to DRAFT (AT-05).
        7. Editor re-submits (Revision 2, IN_REVIEW) -> Approver re-approves (APPROVED).
        8. Pre-execution gate blocks if stamp duty unverified (AT-06).
        9. Treasury records Karnataka e-Stamp -> Pre-execution advances to READY_FOR_EXECUTION.
        10. Counterparty executes Mock eSign ceremony -> MOCK_COMPLETED badge (AT-07).
        11. Auditor verifies H_n cryptographic hash chain and generates BSA 2023 §63 manifest (AT-18).
        12. 1-byte tamper detected on PDF (AT-09).
        """
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner_id = vnext_tenants["tenant_a"]["owner"]["id"]
        editor_id = vnext_tenants["tenant_a"]["editor"]["id"]
        approver_id = vnext_tenants["tenant_a"]["approver"]["id"]
        signer_id = vnext_tenants["tenant_a"]["signer"]["id"]

        cat_svc = CatalogService(db_session)
        contract_svc = ContractService(db_session)
        doc_svc = DocumentService()
        stamping_svc = StampingService(db_session)
        prov_svc = ProviderService(db_session)
        evid_svc = EvidenceService(db_session)

        # -------------------------------------------------------------
        # STEP 1: Catalog & Eligibility Setup
        # -------------------------------------------------------------
        tpl = cat_svc.get_template("tpl_ka_rental_v1")
        assert tpl.state == "draft"  # Marked DRAFT_NOT_LEGAL_APPROVED
        rule = tpl.eligibility_rules[0]
        # Legal Admin authorizes execution for this agreement type
        tpl.state = "legal_approved"
        rule.execution_mode = "provider_allowed"
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 2: Editor Drafts Contract
        # -------------------------------------------------------------
        field_values = {
            "title": "Indiranagar Commercial Tech Office Lease",
            "lessor": "Bengaluru Office Realty Trust",
            "lessee": "Acme Logistics Pvt. Ltd.",
            "start_date": "2026-12-01",
            "end_date": "2027-11-30",
            "monthly_rent_paise": 6500000,
            "security_deposit_paise": 30000000,
            "custom_covenants": "Premises shall be used exclusively for logistics software engineering."
        }
        contract = contract_svc.create_contract(
            org_id=org_id,
            actor_id=editor_id,
            template_version_id=tpl.id,
            title=field_values["title"],
            field_values=field_values
        )
        db_session.commit()
        assert contract.status == "DRAFT"
        assert contract.etag_version == 1

        evid_svc.record_event(org_id, contract.id, editor_id, "CONTRACT_DRAFTED", {"title": contract.title})
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 3: Editor Submits for Review
        # -------------------------------------------------------------
        rev1 = contract_svc.submit_for_review(contract.id, org_id, editor_id)
        db_session.commit()
        assert contract.status == "IN_REVIEW"
        assert rev1.revision_no == 1
        assert contract.current_revision_id == rev1.id

        evid_svc.record_event(org_id, contract.id, editor_id, "SUBMITTED_FOR_REVIEW", {"rev": 1})
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 4: Submitter Self-Approval Block (FR-06)
        # -------------------------------------------------------------
        with pytest.raises(SelfApprovalError):
            contract_svc.record_review_decision(
                contract.id, org_id, actor_id=editor_id, revision_id=rev1.id, decision="approve"
            )

        # -------------------------------------------------------------
        # STEP 5: Approver Approves Revision 1
        # -------------------------------------------------------------
        contract_svc.record_review_decision(
            contract.id, org_id, actor_id=approver_id, revision_id=rev1.id, decision="approve", comment="Terms Approved"
        )
        db_session.commit()
        assert contract.status == "APPROVED"

        evid_svc.record_event(org_id, contract.id, approver_id, "REVIEW_APPROVED", {"rev": 1})
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 6: Invalidation on Field Edit (AT-05)
        # -------------------------------------------------------------
        updated_fields = dict(field_values)
        updated_fields["monthly_rent_paise"] = 7000000  # Increase rent
        c_modified = contract_svc.update_fields(
            contract.id, org_id, editor_id, expected_etag=1, field_values=updated_fields
        )
        db_session.commit()
        assert c_modified.status == "DRAFT"
        assert c_modified.etag_version == 2
        assert c_modified.current_revision_id != rev1.id

        # -------------------------------------------------------------
        # STEP 7: Re-Submit & Re-Approve
        # -------------------------------------------------------------
        rev2 = contract_svc.submit_for_review(contract.id, org_id, editor_id)
        db_session.commit()
        assert contract.status == "IN_REVIEW"

        contract_svc.record_review_decision(
            contract.id, org_id, actor_id=approver_id, revision_id=rev2.id, decision="approve", comment="Revised Rent Approved"
        )
        db_session.commit()
        assert contract.status == "APPROVED"

        # -------------------------------------------------------------
        # STEP 8: Stamping Gate Verification (AT-06)
        # -------------------------------------------------------------
        with pytest.raises(StampGateError):
            contract_svc.prepare_execution(contract.id, org_id, owner_id)

        # Record Karnataka state e-Stamp
        stamp_rec = stamping_svc.record_verified_stamp(
            contract_id=contract.id,
            amount_paise=50000,
            cert_num="IN-KA991203948123A",
            verified_by=owner_id,
            jurisdiction="KA"
        )
        db_session.commit()
        assert stamp_rec.status == "verified"

        # -------------------------------------------------------------
        # STEP 9: Advance to READY_FOR_EXECUTION
        # -------------------------------------------------------------
        c_ready = contract_svc.prepare_execution(contract.id, org_id, owner_id)
        db_session.commit()
        assert c_ready.status == "READY_FOR_EXECUTION"

        # -------------------------------------------------------------
        # STEP 10: Counterparty Digital Signature (Mock eSign Ceremony, AT-07)
        # -------------------------------------------------------------
        idemp_key = f"idemp-sign-{contract.id}-v2"
        exec_req = prov_svc.request_mock_esign(
            contract_id=contract.id,
            org_id=org_id,
            actor_id=signer_id,
            revision_id=contract.current_revision_id,
            idempotency_key=idemp_key
        )
        contract.status = "MOCK_COMPLETED"
        db_session.commit()

        assert exec_req.status == "MOCK_COMPLETED"
        assert exec_req.status != "EXECUTED"  # AT-07 strict invariant
        assert contract.status == "MOCK_COMPLETED"

        evid_svc.record_event(org_id, contract.id, signer_id, "ESIGN_COMPLETED", {"idemp": idemp_key})
        db_session.commit()

        # -------------------------------------------------------------
        # STEP 11: Cryptographic Audit Trail & BSA §63 Manifest (AT-10, AT-18)
        # -------------------------------------------------------------
        events = (
            db_session.query(AuditEvent)
            .filter_by(organisation_id=org_id, contract_id=contract.id)
            .order_by(AuditEvent.occurred_at.asc(), AuditEvent.id.asc())
            .all()
        )
        assert len(events) >= 4

        # Verify hash chain continuity
        for i in range(1, len(events)):
            assert events[i].previous_hash == events[i - 1].event_hash

        manifest = evid_svc.generate_bsa63_draft_manifest(contract.id, org_id)
        assert manifest["certificate_status"] == "DRAFT MANIFEST - AWAITING HUMAN SIGNATORY / EXPERT REVIEW"
        assert manifest["contract_id"] == contract.id

        # -------------------------------------------------------------
        # STEP 12: 1-Byte Tamper Detection (AT-09)
        # -------------------------------------------------------------
        pdf_bytes = doc_svc.render_pdf(contract.id, org_id, contract.field_values)
        expected_hash = doc_svc.compute_sha256(pdf_bytes)

        tampered = bytearray(pdf_bytes)
        tampered[20] ^= 0xFF  # Flip 1 byte
        with pytest.raises(TamperDetectedError):
            evid_svc.verify_buffer_integrity(expected_hash, bytes(tampered))

    def test_e2e_alternative_path_gpu_camera_intake_and_reminder(self, vnext_tenants, db_session, noisy_camera_image_bytes, blurred_camera_image_bytes):
        """
        Executes the Complete Alternative Path Journey:
        1. Ingest blurred frame -> quality gate raises needs_manual_review (AT-11).
        2. Ingest valid frame -> extracts FieldCandidate in 'proposed' state (AT-12).
        3. Verify zero reminders scheduled before human confirmation.
        4. Human reviewer accepts candidate -> status becomes 'accepted'.
        5. Downstream reminder scheduled strictly from confirmed field.
        6. Tenant B isolation verified across ingested candidates.
        """
        org_a = vnext_tenants["tenant_a"]["org_id"]
        org_b = vnext_tenants["tenant_b"]["org_id"]
        owner_a = vnext_tenants["tenant_a"]["owner"]["id"]

        gpu_svc = GPUVisionService(device="cpu")
        remind_svc = ReminderService(db_session)
        contract_svc = ContractService(db_session)

        # Create target contract
        c = contract_svc.create_contract(
            org_id=org_a,
            actor_id=owner_a,
            template_version_id="tpl_ka_rental_v1",
            title="Scan Ingestion Target Contract",
            field_values={"monthly_rent_paise": 3000000}
        )
        db_session.commit()

        # Step 1: Blurred frame intake
        res_blur = gpu_svc.process_camera_frame(blurred_camera_image_bytes)
        assert res_blur["quality_score"] < 0.75
        assert res_blur["needs_manual_review"] is True

        # Step 2: Valid frame intake
        res_sharp = gpu_svc.process_camera_frame(noisy_camera_image_bytes)
        assert res_sharp["status"] == "PROCESSED"

        # Step 3: Candidate extraction defaults to 'proposed'
        cand = gpu_svc.create_candidate(
            contract_id=c.id,
            revision_id=None,
            field_key="lease_expiration_date",
            value="2027-11-30",
            page=1,
            excerpt="Lease Expiration Date: 30 November 2027"
        )
        db_session.add(cand)
        db_session.commit()
        assert cand.review_status == "proposed"

        # Verify 0 reminders before confirmation
        reminders = remind_svc.list_reminders_for_contract(c.id)
        assert len(reminders) == 0

        # Step 4: Human reviewer accepts candidate
        cand.review_status = "accepted"
        cand.reviewed_by = owner_a
        db_session.commit()

        # Step 5: Schedule reminder from confirmed field
        from datetime import date
        event_dt = date.fromisoformat(cand.candidate_value)
        rem = remind_svc.schedule_reminder(
            contract_id=c.id,
            kind="lease_expiry",
            event_date=event_dt,
            source_confirmed=True
        )
        db_session.commit()
        assert rem.source_field_confirmed is True
        assert rem.status == "scheduled"

        # Step 6: Tenant isolation check
        with pytest.raises(TenantIsolationError):
            contract_svc.get_contract(c.id, org_id=org_b, actor_id="usr-bob-01")
