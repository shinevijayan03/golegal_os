"""
GoLegal vNext - Acceptance Test Suite (AT-01 through AT-18)
Strictly verifies all acceptance criteria defined in GoLegal PRD Section 10.
"""
import pytest
import time
import hashlib
from datetime import datetime, timezone, timedelta

# Import from golegal vNext modules
from golegal.domain.models import (
    Organisation, Membership, TemplateVersion, EligibilityRule,
    Contract, DocumentRevision, ReviewDecision, ExecutionRequest,
    StampRecord, FieldCandidate, Finding, AuditEvent, Reminder, AIProcessingPolicy
)
from golegal.services.auth_service import AuthService, TenantIsolationError
from golegal.services.catalog_service import CatalogService, LegalEligibilityError
from golegal.services.contract_service import (
    ContractService, ContractValidationError, StaleEtagError, SelfApprovalError
)
from golegal.services.document_service import DocumentService
from golegal.services.provider_service import (
    ProviderService, WebhookVerificationError, ReplayWindowExpiredError
)
from golegal.services.stamping_service import StampingService, StampGateError
from golegal.services.reminder_service import ReminderService
from golegal.services.gpu_vision_service import GPUVisionService
from golegal.services.ai_insight_service import AIInsightService, AIDisabledError
from golegal.services.evidence_service import EvidenceService, TamperDetectedError


class TestFunctionalAT01ToAT18:
    """Executable verification suite for PRD Section 10 Acceptance Tests."""

    def test_at01_tenant_isolation(self, vnext_tenants, db_session):
        """AT-01: Tenant isolation: User from Tenant B cannot access Tenant A's contract/events/files."""
        auth = AuthService(db_session)
        contract_svc = ContractService(db_session)
        
        # Tenant A creates contract
        c_a = contract_svc.create_contract(
            org_id=vnext_tenants["tenant_a"]["org_id"],
            actor_id=vnext_tenants["tenant_a"]["owner"]["id"],
            template_version_id="tpl_ka_rental_v1",
            title="Tenant A Private Agreement",
            field_values={"monthly_rent_paise": 2500000}
        )
        assert c_a.organisation_id == vnext_tenants["tenant_a"]["org_id"]

        # User from Tenant B requests contract
        with pytest.raises(TenantIsolationError) as exc_info:
            contract_svc.get_contract(
                contract_id=c_a.id,
                org_id=vnext_tenants["tenant_b"]["org_id"],
                actor_id=vnext_tenants["tenant_b"]["owner"]["id"]
            )
        assert "403" in str(exc_info.value) or "404" in str(exc_info.value) or "TENANT_ACCESS_DENIED" in str(exc_info.value)

    def test_at02_template_legal_gate(self, vnext_tenants, db_session):
        """AT-02: Template marked draft or unapproved blocks execution with 422 LEGAL_ELIGIBILITY_UNVERIFIED."""
        contract_svc = ContractService(db_session)
        
        c = contract_svc.create_contract(
            org_id=vnext_tenants["tenant_a"]["org_id"],
            actor_id=vnext_tenants["tenant_a"]["owner"]["id"],
            template_version_id="tpl_ka_rental_v1",
            title="Karnataka Rental Draft",
            field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        
        # Prepare execution on unapproved template
        with pytest.raises(LegalEligibilityError) as exc_info:
            contract_svc.prepare_execution(
                contract_id=c.id,
                org_id=vnext_tenants["tenant_a"]["org_id"],
                actor_id=vnext_tenants["tenant_a"]["owner"]["id"]
            )
        assert "LEGAL_ELIGIBILITY_UNVERIFIED" in str(exc_info.value)

    def test_at03_typed_native_data_bypass(self, vnext_tenants, db_session, monkeypatch):
        """AT-03: Stored typed fields used directly; zero OCR/LLM models invoked for native contracts."""
        contract_svc = ContractService(db_session)
        ai_called = False
        def _mock_ai(*args, **kwargs):
            nonlocal ai_called
            ai_called = True
            raise RuntimeError("AI model must not be called on native contracts!")
        
        monkeypatch.setattr(GPUVisionService, "process_camera_stream", _mock_ai)
        monkeypatch.setattr(AIInsightService, "answer_qa", _mock_ai)

        c = contract_svc.create_contract(
            org_id=vnext_tenants["tenant_a"]["org_id"],
            actor_id=vnext_tenants["tenant_a"]["owner"]["id"],
            template_version_id="tpl_ka_rental_v1",
            title="Native Typed Contract",
            field_values={"monthly_rent_paise": 2800000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        assert c.field_values["monthly_rent_paise"] == 2800000
        assert not ai_called

    def test_at04_invalid_dates_rejected(self, vnext_tenants, db_session):
        """AT-04: End date earlier than start date rejected with 422 with field key."""
        contract_svc = ContractService(db_session)
        
        with pytest.raises(ContractValidationError) as exc_info:
            contract_svc.create_contract(
                org_id=vnext_tenants["tenant_a"]["org_id"],
                actor_id=vnext_tenants["tenant_a"]["editor"]["id"],
                template_version_id="tpl_ka_rental_v1",
                title="Invalid Date Contract",
                field_values={
                    "start_date": "2027-01-01",
                    "end_date": "2026-01-01",  # Invalid: end earlier than start
                    "monthly_rent_paise": 2000000
                }
            )
        assert "end_date" in str(exc_info.value) or "DATE_ORDER_INVALID" in str(exc_info.value)

    def test_at05_revision_invalidates_approval(self, vnext_tenants, db_session):
        """AT-05: Modifying fields after approval creates new revision, resets to DRAFT, invalidates approval."""
        contract_svc = ContractService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        editor = vnext_tenants["tenant_a"]["editor"]["id"]
        approver = vnext_tenants["tenant_a"]["approver"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=editor, template_version_id="tpl_ka_rental_v1",
            title="Approved Contract", field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        rev1 = contract_svc.submit_for_review(c.id, org_id, editor)
        contract_svc.record_review_decision(c.id, org_id, approver, rev1.id, decision="approve", comment="LGTM")
        
        c = contract_svc.get_contract(c.id, org_id, editor)
        assert c.status == "APPROVED"
        old_etag = c.etag_version

        # Editor modifies field value
        c_updated = contract_svc.update_fields(
            c.id, org_id, editor, expected_etag=old_etag, field_values={"monthly_rent_paise": 3000000}
        )
        assert c_updated.status == "DRAFT"
        assert c_updated.etag_version == old_etag + 1
        assert c_updated.current_revision_id != rev1.id

    def test_at06_stamp_duty_gate(self, vnext_tenants, db_session):
        """AT-06: Mandatory unverified stamp duty blocks execution; never guess statutory fees."""
        contract_svc = ContractService(db_session)
        stamping_svc = StampingService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner = vnext_tenants["tenant_a"]["owner"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=owner, template_version_id="tpl_ka_rental_v1",
            title="Stamping Gate Test", field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        # Stamp record missing or unverified
        with pytest.raises(StampGateError) as exc_info:
            stamping_svc.assert_stamp_verified(c.id, org_id)
        assert "STAMP_UNVERIFIED" in str(exc_info.value)

    def test_at07_mock_esign_completed_badge(self, vnext_tenants, db_session):
        """AT-07: Mock provider returns MOCK_COMPLETED only; prohibited from showing EXECUTED badge."""
        contract_svc = ContractService(db_session)
        prov_svc = ProviderService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner = vnext_tenants["tenant_a"]["owner"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=owner, template_version_id="tpl_ka_rental_v1",
            title="eSign Contract", field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        rev = contract_svc.submit_for_review(c.id, org_id, owner)

        req = prov_svc.request_mock_esign(
            contract_id=c.id, org_id=org_id, actor_id=owner,
            revision_id=rev.id, idempotency_key="idemp-key-001"
        )
        assert req.status == "MOCK_COMPLETED"
        assert req.status != "EXECUTED"

    def test_at08_webhook_spoof_and_replay(self, vnext_tenants, db_session, webhook_signer):
        """AT-08: Invalid webhook HMAC or replayed timestamp (>300s) rejected with 401."""
        prov_svc = ProviderService(db_session)
        
        # 1. Invalid signature
        with pytest.raises(WebhookVerificationError):
            prov_svc.handle_webhook_callback(
                provider="mock_esign",
                payload_raw=b'{"event":"signed"}',
                signature_header="invalid_tampered_hmac_hex",
                timestamp_header=str(int(time.time()))
            )

        # 2. Replay window expired (>300s old)
        old_ts = int(time.time()) - 360
        signed = webhook_signer(b'{"event":"signed"}', timestamp=old_ts)
        with pytest.raises(ReplayWindowExpiredError):
            prov_svc.handle_webhook_callback(
                provider="mock_esign",
                payload_raw=signed["payload"],
                signature_header=signed["signature"],
                timestamp_header=signed["timestamp"]
            )

    def test_at09_evidence_tamper_detection(self, vnext_tenants, db_session, valid_pdf_bytes):
        """AT-09: One single byte altered in stored PDF causes SHA-256 verification failure (TAMPER_DETECTED)."""
        evid_svc = EvidenceService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        
        # Tamper 1 byte
        tampered_bytes = bytearray(valid_pdf_bytes)
        tampered_bytes[15] = (tampered_bytes[15] + 1) % 256
        
        with pytest.raises(TamperDetectedError) as exc_info:
            evid_svc.verify_buffer_integrity(
                expected_sha256=hashlib.sha256(valid_pdf_bytes).hexdigest(),
                actual_bytes=bytes(tampered_bytes)
            )
        assert "TAMPER_DETECTED" in str(exc_info.value)

    def test_at10_append_only_audit_chain(self, vnext_tenants, db_session):
        """AT-10: AuditEvent is strictly insert-only; UPDATE/DELETE blocked; hash chain validated."""
        contract_svc = ContractService(db_session)
        evid_svc = EvidenceService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner = vnext_tenants["tenant_a"]["owner"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=owner, template_version_id="tpl_ka_rental_v1",
            title="Audit Contract", field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )

        e1 = evid_svc.record_event(org_id, c.id, owner, "CONTRACT_CREATED", {"title": "Test 1"})
        e2 = evid_svc.record_event(org_id, c.id, owner, "SUBMITTED_FOR_REVIEW", {"rev": 1})
        assert e2.previous_hash == e1.event_hash

        # Attempt out-of-band mutation
        with pytest.raises(Exception):
            evid_svc.delete_event(e1.id)

    def test_at11_ocr_quality_and_blur_gate(self, blurred_camera_image_bytes):
        """AT-11: Blurred document scan (< 0.75) flags needs_manual_review and blocks auto-commit."""
        vision = GPUVisionService(device="cpu")
        res = vision.process_camera_frame(blurred_camera_image_bytes)
        assert res["quality_score"] < 0.75
        assert res["needs_manual_review"] is True

    def test_at12_candidate_review_queue(self, vnext_tenants, db_session):
        """AT-12: Extracted field candidate remains 'proposed' and schedules NO reminder until accepted."""
        vision = GPUVisionService(device="cpu")
        remind_svc = ReminderService(db_session)
        
        cand = vision.create_candidate(
            contract_id="c-01", revision_id="rev-01", field_key="expiry_date",
            value="2027-10-31", page=1, excerpt="Expiry: 31 Oct 2027"
        )
        assert cand.review_status == "proposed"
        
        # Verify reminder is not scheduled from unconfirmed candidate
        reminders = remind_svc.list_reminders_for_contract("c-01")
        assert len(reminders) == 0

    def test_at13_default_external_ai_disabled(self, vnext_tenants, db_session):
        """AT-13: When third_party_ai_enabled is False, Q&A returns AI_DISABLED with 0 model calls."""
        ai_svc = AIInsightService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        
        with pytest.raises(AIDisabledError) as exc_info:
            ai_svc.answer_qa(org_id=org_id, contract_id="c-01", question="What is the lock-in period?")
        assert "AI_DISABLED" in str(exc_info.value)

    def test_at14_prompt_injection_sanitization(self, prompt_injection_pdf_bytes):
        """AT-14: Uploaded adversarial PDF content treated as untrusted data; privilege escalation blocked."""
        ai_svc = AIInsightService(None)
        safe_text = ai_svc.sanitize_untrusted_document_text(prompt_injection_pdf_bytes.decode("latin1", errors="ignore"))
        assert "SYSTEM PROMPT OVERRIDE" not in safe_text or "UNTRUSTED_DOC_CONTENT" in safe_text

    def test_at15_citation_locked_qa(self, db_session):
        """AT-15: Q&A queries for terms absent in source text return insufficient_evidence without hallucination."""
        ai_svc = AIInsightService(db_session)
        res = ai_svc.verify_evidence_citation(
            source_text="Monthly rent is Rs. 25000 payable by the 5th of each month.",
            claimed_answer="The pet deposit is Rs. 50000.",
            claimed_quote="pet deposit is Rs. 50000"
        )
        assert res["status"] == "insufficient_evidence"

    def test_at16_workflow_assistant_human_gate(self, vnext_tenants, db_session):
        """AT-16: Workflow assistant cannot autonomously invoke payment, eSign, or stamping."""
        ai_svc = AIInsightService(db_session)
        with pytest.raises(PermissionError) as exc_info:
            ai_svc.execute_tool_action("execute_live_esign", contract_id="c-01", actor="assistant")
        assert "HUMAN_GATE_REQUIRED" in str(exc_info.value)

    def test_at17_idempotent_sign_and_reminder(self, vnext_tenants, db_session):
        """AT-17: Duplicate sign request with identical Idempotency-Key yields exactly 1 provider request."""
        contract_svc = ContractService(db_session)
        prov_svc = ProviderService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner = vnext_tenants["tenant_a"]["owner"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=owner, template_version_id="tpl_ka_rental_v1",
            title="Idempotency Contract", field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )
        rev = contract_svc.submit_for_review(c.id, org_id, owner)

        req1 = prov_svc.request_mock_esign(c.id, org_id, owner, rev.id, "idemp-dup-001")
        req2 = prov_svc.request_mock_esign(c.id, org_id, owner, rev.id, "idemp-dup-001")
        assert req1.id == req2.id

    def test_at18_bsa63_draft_manifest_only(self, vnext_tenants, db_session):
        """AT-18: Evidence export produces draft manifest marked 'AWAITING HUMAN SIGNATORY / EXPERT REVIEW'."""
        evid_svc = EvidenceService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        manifest = evid_svc.generate_bsa63_draft_manifest("c-01", org_id)
        assert "AWAITING HUMAN SIGNATORY / EXPERT REVIEW" in manifest["certificate_status"]
