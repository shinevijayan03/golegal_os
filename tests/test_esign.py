"""
Tests for UIDAI / ESP Aadhaar eSign Gateway Service (TC-ESIGN)
"""
import pytest
from services.esign_service import ESignService, AadhaarVerificationError, RateLimitLockoutError
from domain.models import Party, Signature, AuditLog


class TestESignService:
    # -------------------------------------------------------------
    # Valid Aadhaar eSign Flow (TC-ESIGN-01)
    # -------------------------------------------------------------
    def test_valid_aadhaar_otp_signing(self, esign_svc, sample_agreement, db_session):
        party = db_session.query(Party).filter_by(agreement_id=sample_agreement.id, party_type="Owner").first()
        assert party.signing_status == "Pending"

        # Request OTP
        otp = esign_svc.request_otp(party.aadhaar_masked)
        assert otp == "123456"

        # Execute signing
        sig = esign_svc.verify_otp_and_sign(
            agreement_id=sample_agreement.id,
            party_id=party.id,
            aadhaar_masked=party.aadhaar_masked,
            submitted_otp=otp,
            consent_accepted=True,
            client_ip="192.168.1.50",
            user_agent="GoLegal_TestRunner"
        )

        assert sig is not None
        assert sig.signature_hash is not None
        assert len(sig.signature_hash) == 64  # SHA-256 length
        assert sig.party_id == party.id
        assert sig.auth_type == "Aadhaar_OTP"
        assert party.signing_status == "Signed"

        # Audit log verified
        audit = db_session.query(AuditLog).filter_by(agreement_id=sample_agreement.id, event_type="PARTY_ESIGNED").first()
        assert audit is not None
        assert sig.signature_hash in audit.event_data

    # -------------------------------------------------------------
    # Mandatory Consent Disclaimer (TC-ESIGN-04)
    # -------------------------------------------------------------
    def test_consent_mandatory_check(self, esign_svc, sample_agreement, db_session):
        party = db_session.query(Party).filter_by(agreement_id=sample_agreement.id, party_type="Tenant").first()

        with pytest.raises(AadhaarVerificationError) as exc_info:
            esign_svc.verify_otp_and_sign(
                agreement_id=sample_agreement.id,
                party_id=party.id,
                aadhaar_masked=party.aadhaar_masked,
                submitted_otp="123456",
                consent_accepted=False  # Unchecked consent
            )
        assert "consent" in str(exc_info.value).lower()
        assert party.signing_status == "Pending"

    # -------------------------------------------------------------
    # Invalid OTP Rejection (TC-ESIGN-02)
    # -------------------------------------------------------------
    def test_invalid_otp_rejection(self, esign_svc, sample_agreement, db_session):
        party = db_session.query(Party).filter_by(agreement_id=sample_agreement.id, party_type="Witness").first()

        with pytest.raises(AadhaarVerificationError) as exc_info:
            esign_svc.verify_otp_and_sign(
                agreement_id=sample_agreement.id,
                party_id=party.id,
                aadhaar_masked=party.aadhaar_masked,
                submitted_otp="999999",  # Incorrect
                consent_accepted=True
            )
        assert "invalid otp" in str(exc_info.value).lower()
        assert "4 attempts remaining" in str(exc_info.value).lower()
        assert party.signing_status == "Pending"

    # -------------------------------------------------------------
    # Rate Limiting & Account Lockout (TC-ESIGN-03)
    # -------------------------------------------------------------
    def test_rate_limit_lockout_after_five_failures(self, esign_svc, sample_agreement, db_session):
        party = db_session.query(Party).filter_by(agreement_id=sample_agreement.id, party_type="Witness").first()

        # Fail 5 times
        for _ in range(5):
            try:
                esign_svc.verify_otp_and_sign(
                    agreement_id=sample_agreement.id,
                    party_id=party.id,
                    aadhaar_masked=party.aadhaar_masked,
                    submitted_otp="000000",
                    consent_accepted=True
                )
            except AadhaarVerificationError:
                pass

        # 6th attempt triggers RateLimitLockoutError
        with pytest.raises(RateLimitLockoutError):
            esign_svc.verify_otp_and_sign(
                agreement_id=sample_agreement.id,
                party_id=party.id,
                aadhaar_masked=party.aadhaar_masked,
                submitted_otp="123456",
                consent_accepted=True
            )

    # -------------------------------------------------------------
    # Idempotent Signing
    # -------------------------------------------------------------
    def test_idempotent_signing_call(self, esign_svc, sample_agreement, db_session):
        party = db_session.query(Party).filter_by(agreement_id=sample_agreement.id, party_type="Owner").first()
        sig1 = esign_svc.verify_otp_and_sign(
            sample_agreement.id, party.id, party.aadhaar_masked, "123456", True
        )
        # Calling again should return existing signature
        sig2 = esign_svc.verify_otp_and_sign(
            sample_agreement.id, party.id, party.aadhaar_masked, "123456", True
        )
        assert sig1.id == sig2.id
        assert sig1.signature_hash == sig2.signature_hash
