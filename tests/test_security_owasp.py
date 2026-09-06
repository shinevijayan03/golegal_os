"""
Tests for Security, Capability-Based Access Control (CBAC), and OWASP Matrix (TC-SEC)
"""
import pytest
import time
from security.cbac import TokenExpiredError, UnauthorizedCapabilityError
from domain.models import Agreement


class TestSecurityAndOWASP:
    # -------------------------------------------------------------
    # IDOR Prevention via CBAC Tokens (TC-SEC-01)
    # -------------------------------------------------------------
    def test_idor_horizontal_escalation_blocked(self, cbac_svc):
        # Token generated for Agreement A
        token = cbac_svc.generate_token(
            agreement_id="agr-alpha-111",
            party_id="pty-001",
            role="Tenant",
            allowed_actions=["VIEW_DRAFT", "EXECUTE_ESIGN"]
        )

        # Valid access to Agreement A
        payload = cbac_svc.verify_token(
            token=token,
            required_agreement_id="agr-alpha-111",
            required_action="VIEW_DRAFT"
        )
        assert payload["agr_id"] == "agr-alpha-111"

        # Attempt to access Agreement B using Agreement A token -> IDOR Blocked!
        with pytest.raises(UnauthorizedCapabilityError) as exc_info:
            cbac_svc.verify_token(
                token=token,
                required_agreement_id="agr-beta-222", # Target different agreement
                required_action="VIEW_DRAFT"
            )
        assert "idor violation" in str(exc_info.value).lower()

    # -------------------------------------------------------------
    # Witness Privacy Policy (TC-SEC-02)
    # -------------------------------------------------------------
    def test_witness_restricted_from_final_download(self, cbac_svc):
        witness_token = cbac_svc.generate_token(
            agreement_id="agr-alpha-111",
            party_id="pty-witness-01",
            role="Witness",
            allowed_actions=["VIEW_DRAFT", "EXECUTE_ESIGN", "DOWNLOAD_FINAL"]
        )

        # Allowed action
        payload = cbac_svc.verify_token(witness_token, "agr-alpha-111", "EXECUTE_ESIGN")
        assert payload["role"] == "Witness"

        # Forbidden action for Witness
        with pytest.raises(UnauthorizedCapabilityError) as exc_info:
            cbac_svc.verify_token(witness_token, "agr-alpha-111", "DOWNLOAD_FINAL")
        assert "witness privacy policy" in str(exc_info.value).lower()

    # -------------------------------------------------------------
    # Token Expiration & Tampering
    # -------------------------------------------------------------
    def test_expired_token_rejection(self, cbac_svc):
        # Generate token with negative TTL
        expired_token = cbac_svc.generate_token(
            agreement_id="agr-001",
            party_id="pty-01",
            role="Owner",
            allowed_actions=["VIEW_DRAFT"],
            ttl_seconds=-10
        )
        with pytest.raises(TokenExpiredError):
            cbac_svc.verify_token(expired_token, "agr-001", "VIEW_DRAFT")

    def test_tampered_token_signature_rejection(self, cbac_svc):
        token = cbac_svc.generate_token("agr-001", "pty-01", "Owner", ["VIEW_DRAFT"])
        payload_part, sig_part = token.split(".")
        tampered_sig = ("0" if sig_part[0] != "0" else "1") + sig_part[1:]
        tampered_token = f"{payload_part}.{tampered_sig}"

        with pytest.raises(UnauthorizedCapabilityError) as exc_info:
            cbac_svc.verify_token(tampered_token, "agr-001", "VIEW_DRAFT")
        assert "signature mismatch" in str(exc_info.value).lower()

    # -------------------------------------------------------------
    # XSS Input Sanitization (TC-SEC-04)
    # -------------------------------------------------------------
    def test_xss_input_sanitization(self, cbac_svc):
        raw_input = "<script>alert('XSS_ATTACK')</script>"
        sanitized = cbac_svc.sanitize_input(raw_input)
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized

        js_input = "javascript:document.cookie"
        sanitized_js = cbac_svc.sanitize_input(js_input)
        assert "javascript:" not in sanitized_js

    # -------------------------------------------------------------
    # Storage Consent vs 27-Day Purge Rule (TC-SEC-05)
    # -------------------------------------------------------------
    def test_storage_consent_and_draft_purge_rule(self, cbac_svc):
        now = time.time()
        # 1. User gave consent -> never purged
        assert cbac_svc.should_purge_draft(
            created_at_timestamp=now - (30 * 86400), # 30 days old
            consent_granted=True,
            retention_days=27
        ) is False

        # 2. No consent, fresh draft (< 27 days old) -> not purged yet
        assert cbac_svc.should_purge_draft(
            created_at_timestamp=now - (10 * 86400), # 10 days old
            consent_granted=False,
            retention_days=27
        ) is False

        # 3. No consent, old draft (> 27 days old) -> PURGE!
        assert cbac_svc.should_purge_draft(
            created_at_timestamp=now - (28 * 86400), # 28 days old
            consent_granted=False,
            retention_days=27
        ) is True

    # -------------------------------------------------------------
    # SQL Parameterization Check (TC-SEC-03)
    # -------------------------------------------------------------
    def test_sql_injection_safety(self, db_session, sample_agreement):
        # Query using malicious parameter via ORM
        malicious_input = "' OR '1'='1"
        result = db_session.query(Agreement).filter_by(state_code=malicious_input).all()
        # Safe parameterization ensures zero records returned
        assert len(result) == 0
