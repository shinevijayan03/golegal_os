"""
End-to-end lifecycle tests: payment + invoice, tokenized dispatch, counterparty signing via CBAC link,
atomic sealing, witness privacy, expiry sweep and consent-based purge (TC-E2E)
"""
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from domain.models import AuditLog, Document, Notification, Payment, utc_now
from security.cbac import ACTION_DOWNLOAD_FINAL, ACTION_EXECUTE_ESIGN, CBACService, UnauthorizedCapabilityError
from services.agreement_service import AgreementService, demo_payload
from services.doc_assembly import DocumentAssemblyEngine
from services.document_service import DocumentService
from services.esign_service import ESignService
from services.payment_service import PaymentService
from services.stamping_service import StampingService
from services.workflow_service import InvalidStateTransitionError, WorkflowService


def _token_from(url: str) -> str:
    return parse_qs(urlparse(url).query)["sign_token"][0]


class TestPaymentService:
    def test_checkout_creates_payment_invoice_and_audit(self, payment_svc, sample_agreement, sample_users, db_session):
        payment = payment_svc.checkout(sample_agreement, sample_users["owner"], payment_mode="UPI")
        assert payment.status == "Success"
        assert payment.invoice_number.startswith("INV-")
        assert payment.total_amount == pytest.approx(100 + 299 + 299 * 0.18, abs=0.01)
        doc = db_session.query(Document).filter_by(agreement_id=sample_agreement.id, doc_type="INVOICE").one()
        assert doc.content.startswith(b"%PDF-")
        assert DocumentService(db_session).verify(doc)
        assert payment_svc.invoice_pdf(payment) == doc.content
        assert db_session.query(AuditLog).filter_by(agreement_id=sample_agreement.id, event_type="PAYMENT_CAPTURED").count() == 1
        # idempotent
        again = payment_svc.checkout(sample_agreement, sample_users["owner"])
        assert again.id == payment.id
        assert db_session.query(Payment).count() == 1
        assert payment_svc.invoices_for_user(sample_users["owner"])[0].id == payment.id
        assert payment_svc.invoices_for_user(sample_users["tenant"]) == []


class TestEndToEndLifecycle:
    def test_full_lifecycle_with_tokenized_links(self, db_session, sample_users):
        owner = sample_users["owner"]
        agreements = AgreementService(db_session)
        workflow = WorkflowService(db_session)
        payments = PaymentService(db_session)
        stamping = StampingService(db_session)
        esign = ESignService(db_session)
        cbac = CBACService()

        # 1. Draft from wizard payload
        agr = agreements.save_draft(owner, demo_payload(), validate=True)
        assert agr.status == "Draft" and len(agr.parties) == 3

        # 2. Pay + procure e-stamp (human step) -> Paid
        quote = payments.quote(agr)
        payments.checkout(agr, owner)
        stamping.procure_estamp(agr.id, agr.state_code, quote["stamp_duty_amount"], owner.full_name)
        workflow.transition_state(agr, "Paid", triggered_by=owner.id)
        assert stamping.get_prepaid_balance() == 50000 - quote["stamp_duty_amount"]

        # 3. Open for signatures -> tokens + invitations to every party
        dispatched = workflow.open_for_signatures(agr, triggered_by=owner.id)
        assert agr.status == "Pending_Signatures"
        assert agr.expires_at is not None
        assert len(dispatched) == 3
        assert db_session.query(Notification).filter_by(agreement_id=agr.id, kind="INVITE").count() == 3
        assert all(p.access_token for p in agr.parties)

        # 4. Counterparties open their link: token verifies for their agreement only (IDOR)
        links = {d["role"]: d["signing_url"] for d in dispatched}
        witness_payload = cbac.verify_token(_token_from(links["Witness"]), agr.id, ACTION_EXECUTE_ESIGN)
        assert witness_payload["role"] == "Witness"
        with pytest.raises(UnauthorizedCapabilityError):
            cbac.verify_token(_token_from(links["Witness"]), "some-other-agreement", ACTION_EXECUTE_ESIGN)
        with pytest.raises(UnauthorizedCapabilityError):
            cbac.verify_token(_token_from(links["Witness"]), agr.id, ACTION_DOWNLOAD_FINAL)

        # 5. Non-atomic signing in arbitrary order; reminders for laggards
        parties = {p.party_type: p for p in agr.parties}
        esign.verify_otp_and_sign(agr.id, parties["Witness"].id, parties["Witness"].aadhaar_masked, "123456", True, client_ip="10.0.0.7")
        assert workflow.check_and_complete_signing(agr.id) is False
        reminded = workflow.resend_invitations(agr, triggered_by=owner.id)
        assert {r["party_name"] for r in reminded} == {"Ramakiran Reddy", "Mayank Tripathi"}
        assert parties["Tenant"].reminder_count == 1
        esign.verify_otp_and_sign(agr.id, parties["Tenant"].id, parties["Tenant"].aadhaar_masked, "123456", True)
        esign.verify_otp_and_sign(agr.id, parties["Owner"].id, parties["Owner"].aadhaar_masked, "123456", True)

        # 6. Atomic completion + sealing
        assert workflow.check_and_complete_signing(agr.id) is True
        assert agr.status == "Completed" and agr.executed_at is not None
        final = DocumentService(db_session).latest(agr.id, "FINAL")
        assert final is not None and final.sha256 == agr.final_pdf_sha256
        assert DocumentAssemblyEngine.verify_tamper_evidence(final.content, agr.final_pdf_sha256)
        assert workflow.final_pdf(agr) == final.content
        assert b"%PDF-" in final.content[:8]
        # The final PDF is generated exactly once: sealing again returns identical bytes
        assert workflow.seal_agreement(agr) == final.content

        # 7. Post-execution tokens: owner/tenant may download, witness downgraded
        owner_token = parties["Owner"].access_token
        assert cbac.verify_token(owner_token, agr.id, ACTION_DOWNLOAD_FINAL)["role"] == "Owner"
        with pytest.raises(UnauthorizedCapabilityError):
            cbac.verify_token(parties["Witness"].access_token, agr.id, ACTION_DOWNLOAD_FINAL)
        completion_notes = db_session.query(Notification).filter_by(agreement_id=agr.id, kind="COMPLETION").all()
        assert len(completion_notes) == 3
        assert any(n.signing_url is None for n in completion_notes if n.recipient == parties["Witness"].phone)

        # 8. Terminal state is immutable
        with pytest.raises(InvalidStateTransitionError):
            workflow.transition_state(agr, "Cancelled")
        events = {a.event_type for a in db_session.query(AuditLog).filter_by(agreement_id=agr.id)}
        assert {"PAYMENT_CAPTURED", "ESTAMP_PROCURED", "SIGN_LINKS_DISPATCHED", "REMINDER_SENT", "PARTY_ESIGNED",
                "STATE_TRANSITION", "DOCUMENT_SEALED"} <= events

    def test_expiry_sweep_and_consent_purge(self, db_session, sample_users):
        agreements = AgreementService(db_session)
        workflow = WorkflowService(db_session)
        owner = sample_users["owner"]

        stale = agreements.save_draft(owner, demo_payload())
        workflow.transition_state(stale, "Paid")
        workflow.open_for_signatures(stale, dispatch=False)
        stale.expires_at = utc_now() - timedelta(days=1)
        db_session.commit()
        assert workflow.expire_stale_agreements() == 1
        assert stale.status == "Expired"

        payload = demo_payload()
        payload["cloud_storage_consent"] = False
        old_draft = agreements.save_draft(owner, payload)
        old_draft.created_at = utc_now() - timedelta(days=28)
        consented = agreements.save_draft(owner, demo_payload())
        consented.created_at = utc_now() - timedelta(days=400)
        db_session.commit()
        assert workflow.purge_unconsented_drafts() == 1
        assert agreements.get(old_draft.id) is None
        assert agreements.get(consented.id) is not None

    def test_reminder_sweep_respects_daily_cadence(self, db_session, sample_users):
        agreements = AgreementService(db_session)
        workflow = WorkflowService(db_session)
        agr = agreements.save_draft(sample_users["owner"], demo_payload())
        workflow.transition_state(agr, "Paid")
        workflow.open_for_signatures(agr)  # notifies everyone now
        assert workflow.run_reminder_sweep() == 0  # nobody due yet
        for p in agr.parties:
            p.last_notified_at = utc_now() - timedelta(hours=25)
        db_session.commit()
        assert workflow.run_reminder_sweep() == 3
