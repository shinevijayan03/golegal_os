"""
GoLegal UIDAI / ESP Aadhaar eSign Gateway Service
Simulates Aadhaar e-KYC OTP challenge, verification, and PKCS#7 digital signature stamping.
"""
import hashlib
import uuid
from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session
from domain.models import Signature, Party, Agreement, AuditLog


class AadhaarVerificationError(Exception):
    pass


class RateLimitLockoutError(Exception):
    pass


class ESignService:
    def __init__(self, session: Session):
        self.session = session
        # Ephemeral in-memory OTP and attempt trackers
        self._active_otps: dict[str, str] = {}
        self._failed_attempts: dict[str, int] = {}

    def request_otp(self, aadhaar_masked: str) -> str:
        """Issue mock OTP challenge (standard mock is '123456')."""
        if self._failed_attempts.get(aadhaar_masked, 0) >= 5:
            raise RateLimitLockoutError("Too many failed attempts. Account locked for 15 minutes.")
        
        # Default mock OTP
        mock_otp = "123456"
        self._active_otps[aadhaar_masked] = mock_otp
        return mock_otp

    def verify_otp_and_sign(
        self,
        agreement_id: str,
        party_id: str,
        aadhaar_masked: str,
        submitted_otp: str,
        consent_accepted: bool,
        client_ip: str = "127.0.0.1",
        user_agent: str = "Mozilla/5.0"
    ) -> Signature:
        """
        Verify Aadhaar OTP, affix digital signature hash, and mark party signed.
        """
        if not consent_accepted:
            raise AadhaarVerificationError("Mandatory UIDAI eSign consent not accepted")

        attempts = self._failed_attempts.get(aadhaar_masked, 0)
        if attempts >= 5:
            raise RateLimitLockoutError("Aadhaar authentication locked due to excessive failed attempts")

        expected_otp = self._active_otps.get(aadhaar_masked, "123456")
        if submitted_otp.strip() != expected_otp:
            self._failed_attempts[aadhaar_masked] = attempts + 1
            remaining = 5 - (attempts + 1)
            raise AadhaarVerificationError(f"Invalid OTP. {remaining} attempts remaining.")

        # Reset failed attempts upon success
        self._failed_attempts[aadhaar_masked] = 0

        party = self.session.query(Party).filter_by(id=party_id, agreement_id=agreement_id).first()
        if not party:
            raise AadhaarVerificationError("Signatory party not found for this agreement")

        if party.signing_status == "Signed":
            # Idempotent response
            existing_sig = self.session.query(Signature).filter_by(
                agreement_id=agreement_id, party_id=party_id
            ).first()
            if existing_sig:
                return existing_sig

        tx_ref = f"ESP-{uuid.uuid4().hex[:12].upper()}"
        raw_token = f"{agreement_id}:{party_id}:{tx_ref}:{datetime.now(timezone.utc).isoformat()}"
        sig_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        signature = Signature(
            agreement_id=agreement_id,
            party_id=party_id,
            auth_type="Aadhaar_OTP",
            transaction_ref=tx_ref,
            cert_issuer="GoLegal Licensed CCA ESP (NSDL/eMudhra)",
            signature_hash=sig_hash,
            signed_at=datetime.now(timezone.utc),
            ip_address=client_ip,
            user_agent=user_agent
        )
        self.session.add(signature)

        party.signing_status = "Signed"

        audit = AuditLog(
            agreement_id=agreement_id,
            event_type="PARTY_ESIGNED",
            triggered_by=f"PARTY_{party.party_type.upper()}_{party.id[:8]}",
            event_data=json.dumps({
                "party_id": party_id,
                "party_type": party.party_type,
                "aadhaar_masked": aadhaar_masked,
                "transaction_ref": tx_ref,
                "signature_hash": sig_hash,
                "ip_address": client_ip
            })
        )
        self.session.add(audit)
        self.session.commit()
        return signature
