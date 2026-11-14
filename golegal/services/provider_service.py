"""
Mock Provider Outbox, HMAC Webhook Verification & Idempotency Service.
Enforces FR-07, AT-07, AT-08, and AT-17.
"""
from __future__ import annotations
import hmac
import hashlib
import time
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from golegal.domain.models import ExecutionRequest, utc_now
from golegal.config import settings


class WebhookVerificationError(PermissionError):
    """Raised when HMAC signature on incoming webhook callback is invalid (401)."""
    pass


class ReplayWindowExpiredError(ValueError):
    """Raised when incoming webhook timestamp exceeds the 300-second replay window."""
    pass


class ProviderService:
    def __init__(self, session: Session):
        self.session = session
        self.secret = settings.webhook_secret
        self.replay_window = settings.webhook_replay_window_seconds

    def request_mock_esign(
        self, contract_id: str, org_id: str, actor_id: str, revision_id: str, idempotency_key: str
    ) -> ExecutionRequest:
        """Enforces AT-07 & AT-17: Returns MOCK_COMPLETED badge; idempotent per key."""
        existing = (
            self.session.query(ExecutionRequest)
            .filter_by(contract_id=contract_id, idempotency_key=idempotency_key)
            .first()
        )
        if existing:
            return existing

        req = ExecutionRequest(
            contract_id=contract_id,
            revision_id=revision_id,
            provider_key="mock_esign",
            idempotency_key=idempotency_key,
            mode="mock",
            status="MOCK_COMPLETED",  # AT-07 Invariant: MOCK_COMPLETED, NOT EXECUTED
            signed_object_key=f"signed/{contract_id}/{revision_id}_mock_signed.pdf",
            signed_sha256=hashlib.sha256(f"MOCK_SIGNED_{contract_id}".encode("utf-8")).hexdigest(),
            completed_at=utc_now()
        )
        self.session.add(req)
        self.session.flush()
        return req

    def handle_webhook_callback(
        self, provider: str, payload_raw: bytes, signature_header: str, timestamp_header: str
    ) -> Dict[str, Any]:
        """Enforces AT-08: Verifies HMAC-SHA256 signature and checks 300-second replay window."""
        try:
            ts = int(timestamp_header)
        except (ValueError, TypeError):
            raise WebhookVerificationError("401 INVALID_TIMESTAMP: Timestamp header is missing or non-integer.")

        # Replay window check
        now = int(time.time())
        if abs(now - ts) > self.replay_window:
            raise ReplayWindowExpiredError(
                f"401 REPLAY_EXPIRED: Webhook timestamp {ts} is older than {self.replay_window} seconds."
            )

        # HMAC signature verification
        expected_body = f"{ts}.".encode("utf-8") + payload_raw
        expected_sig = hmac.new(self.secret.encode("utf-8"), expected_body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(expected_sig, signature_header):
            raise WebhookVerificationError("401 INVALID_SIGNATURE: HMAC signature verification failed.")

        return {"status": "accepted", "provider": provider, "processed_at": utc_now().isoformat()}
