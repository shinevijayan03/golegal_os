"""
GoLegal UIDAI / ESP Aadhaar eSign Gateway Service
Simulates Aadhaar e-KYC OTP challenge, verification, and PKCS#7 digital signature stamping.

OTP challenges and failed-attempt counters are persisted (otp_challenges table)
so rate limiting holds across service instances, reruns and processes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from domain.models import AuditLog, OtpChallenge, Party, Signature, utc_now


class AadhaarVerificationError(Exception):
    pass


class RateLimitLockoutError(Exception):
    pass


class ESignService:
    PURPOSE = "ESIGN"

    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _hash_otp(otp: str) -> str:
        return hashlib.sha256(f"{settings.cbac_secret}:{otp}".encode()).hexdigest()

    def _latest(self, subject: str) -> Optional[OtpChallenge]:
        return (
            self.session.query(OtpChallenge)
            .filter_by(subject=subject, purpose=self.PURPOSE)
            .order_by(OtpChallenge.created_at.desc())
            .first()
        )

    def _assert_not_locked(self, challenge: Optional[OtpChallenge]) -> None:
        if challenge and challenge.locked_until and challenge.locked_until > utc_now():
            raise RateLimitLockoutError("Aadhaar authentication locked due to excessive failed attempts. Try again in 15 minutes.")

    def _open_challenge(self, subject: str, otp: Optional[str] = None) -> OtpChallenge:
        """Return the open challenge for a subject or create one (mock OTP in sandbox mode)."""
        latest = self._latest(subject)
        self._assert_not_locked(latest)
        # Failed attempts carry over to a re-issued OTP so re-requesting cannot reset the counter.
        carry_attempts = latest.attempts if (latest and latest.locked_until is None and not latest.consumed) else 0
        if latest and not latest.consumed and latest.expires_at > utc_now():
            if otp is None:
                return latest
            latest.consumed = True  # replaced by a fresh challenge
        otp = otp or settings.mock_otp
        challenge = OtpChallenge(
            subject=subject,
            purpose=self.PURPOSE,
            otp_hash=self._hash_otp(otp),
            attempts=carry_attempts,
            expires_at=utc_now() + timedelta(seconds=settings.otp_ttl_seconds),
        )
        self.session.add(challenge)
        self.session.commit()
        return challenge

    # ------------------------------------------------------------------ API
    def request_otp(self, aadhaar_masked: str) -> str:
        """Issue an OTP challenge to the Aadhaar-linked mobile. Returns the OTP in sandbox mode."""
        latest = self._latest(aadhaar_masked)
        if latest and latest.attempts >= settings.otp_max_attempts:
            self._assert_not_locked(latest)
        otp = settings.mock_otp if settings.mock_gateways else f"{secrets.randbelow(10**6):06d}"
        self._open_challenge(aadhaar_masked, otp)
        return otp if settings.mock_gateways else "SENT"

    def remaining_attempts(self, aadhaar_masked: str) -> int:
        latest = self._latest(aadhaar_masked)
        if not latest:
            return settings.otp_max_attempts
        return max(0, settings.otp_max_attempts - latest.attempts)

    def verify_otp_and_sign(
        self,
        agreement_id: str,
        party_id: str,
        aadhaar_masked: str,
        submitted_otp: str,
        consent_accepted: bool,
        client_ip: str = "127.0.0.1",
        user_agent: str = "Mozilla/5.0",
    ) -> Signature:
        """
        Verify Aadhaar OTP, affix digital signature hash, and mark party signed.
        """
        if not consent_accepted:
            raise AadhaarVerificationError("Mandatory UIDAI eSign consent not accepted")

        latest = self._latest(aadhaar_masked)
        if latest and latest.attempts >= settings.otp_max_attempts:
            self._assert_not_locked(latest)
        challenge = self._open_challenge(aadhaar_masked)

        if not hmac.compare_digest(self._hash_otp((submitted_otp or "").strip()), challenge.otp_hash):
            challenge.attempts += 1
            remaining = settings.otp_max_attempts - challenge.attempts
            if remaining <= 0:
                challenge.locked_until = utc_now() + timedelta(seconds=settings.otp_lockout_seconds)
            self.session.commit()
            raise AadhaarVerificationError(f"Invalid OTP. {max(remaining, 0)} attempts remaining.")

        challenge.attempts = 0
        challenge.consumed = True

        party = self.session.query(Party).filter_by(id=party_id, agreement_id=agreement_id).first()
        if not party:
            self.session.commit()
            raise AadhaarVerificationError("Signatory party not found for this agreement")

        if party.signing_status == "Signed":
            existing_sig = self.session.query(Signature).filter_by(agreement_id=agreement_id, party_id=party_id).first()
            if existing_sig:
                self.session.commit()
                return existing_sig

        tx_ref = f"ESP-{uuid.uuid4().hex[:12].upper()}"
        signed_at = utc_now()
        raw_token = f"{agreement_id}:{party_id}:{tx_ref}:{signed_at.isoformat()}"
        sig_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        signature = Signature(
            agreement_id=agreement_id,
            party_id=party_id,
            auth_type="Aadhaar_OTP",
            transaction_ref=tx_ref,
            cert_issuer="GoLegal Licensed CCA ESP (NSDL/eMudhra)",
            signature_hash=sig_hash,
            signed_at=signed_at,
            ip_address=client_ip,
            user_agent=user_agent,
        )
        self.session.add(signature)
        party.signing_status = "Signed"

        self.session.add(AuditLog(
            agreement_id=agreement_id,
            event_type="PARTY_ESIGNED",
            triggered_by=f"PARTY_{party.party_type.upper()}_{party.id[:8]}",
            event_data=json.dumps({
                "party_id": party_id,
                "party_type": party.party_type,
                "party_name": party.full_name,
                "aadhaar_masked": aadhaar_masked,
                "transaction_ref": tx_ref,
                "signature_hash": sig_hash,
                "ip_address": client_ip,
                "user_agent": user_agent,
                "signed_at": signed_at.isoformat(),
            }),
        ))
        self.session.commit()
        return signature
