"""
Tests for Workflow & Asynchronous Signing State Machine (TC-WORKFLOW)
"""
import pytest
from services.workflow_service import InvalidStateTransitionError
from domain.models import Party


class TestWorkflowService:
    # -------------------------------------------------------------
    # Valid State Transitions (TC-WORKFLOW-01)
    # -------------------------------------------------------------
    def test_valid_state_transitions(self, workflow_svc, sample_agreement):
        assert sample_agreement.status == "Draft"

        # Draft -> Paid
        workflow_svc.transition_state(sample_agreement, "Paid")
        assert sample_agreement.status == "Paid"

        # Paid -> Pending_Signatures
        workflow_svc.transition_state(sample_agreement, "Pending_Signatures")
        assert sample_agreement.status == "Pending_Signatures"

        # Pending_Signatures -> Completed
        workflow_svc.transition_state(sample_agreement, "Completed")
        assert sample_agreement.status == "Completed"
        assert sample_agreement.executed_at is not None

    def test_invalid_state_transition(self, workflow_svc, sample_agreement):
        # Draft -> Completed directly is invalid
        with pytest.raises(InvalidStateTransitionError):
            workflow_svc.transition_state(sample_agreement, "Completed")

    # -------------------------------------------------------------
    # Asynchronous Signing Order Independence (TC-WORKFLOW-02)
    # -------------------------------------------------------------
    def test_asynchronous_order_independence(self, workflow_svc, esign_svc, sample_agreement, db_session):
        workflow_svc.transition_state(sample_agreement, "Paid")
        workflow_svc.transition_state(sample_agreement, "Pending_Signatures")

        parties = db_session.query(Party).filter_by(agreement_id=sample_agreement.id).all()
        owner = next(p for p in parties if p.party_type == "Owner")
        tenant = next(p for p in parties if p.party_type == "Tenant")
        witness = next(p for p in parties if p.party_type == "Witness")

        # Non-traditional order: Witness signs 1st, Tenant signs 2nd, Owner signs 3rd
        esign_svc.verify_otp_and_sign(sample_agreement.id, witness.id, witness.aadhaar_masked, "123456", True)
        assert witness.signing_status == "Signed"
        assert not workflow_svc.check_and_complete_signing(sample_agreement.id)
        assert sample_agreement.status == "Pending_Signatures"

        esign_svc.verify_otp_and_sign(sample_agreement.id, tenant.id, tenant.aadhaar_masked, "123456", True)
        assert tenant.signing_status == "Signed"
        assert not workflow_svc.check_and_complete_signing(sample_agreement.id)
        assert sample_agreement.status == "Pending_Signatures"

        # Final signature: Owner
        esign_svc.verify_otp_and_sign(sample_agreement.id, owner.id, owner.aadhaar_masked, "123456", True)
        assert owner.signing_status == "Signed"

        # Now all parties have signed -> atomically seals to Completed (TC-WORKFLOW-03)
        completed = workflow_svc.check_and_complete_signing(sample_agreement.id)
        assert completed is True
        assert sample_agreement.status == "Completed"
        assert sample_agreement.executed_at is not None

    # -------------------------------------------------------------
    # Real-Time Progress Digest
    # -------------------------------------------------------------
    def test_signing_progress_digest(self, workflow_svc, esign_svc, sample_agreement, db_session):
        progress = workflow_svc.get_signing_progress(sample_agreement.id)
        assert progress["total_parties"] == 3
        assert progress["signed_count"] == 0
        assert progress["all_signed"] is False

        # Sign 1 party
        party = db_session.query(Party).filter_by(agreement_id=sample_agreement.id).first()
        esign_svc.verify_otp_and_sign(sample_agreement.id, party.id, party.aadhaar_masked, "123456", True)

        progress = workflow_svc.get_signing_progress(sample_agreement.id)
        assert progress["signed_count"] == 1
        assert progress["all_signed"] is False
