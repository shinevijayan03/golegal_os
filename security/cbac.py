"""
GoLegal Capability-Based Access Control (CBAC) & Security Service
Implements tokenized capabilities, IDOR prevention, witness privacy rules, and input sanitization.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
import json
import re
import time
from typing import Any, Dict, List, Optional

from config import settings

# Kept for backwards compatibility with existing imports; the live secret comes from config.
DEFAULT_SECRET_KEY = settings.cbac_secret

ACTION_VIEW_DRAFT = "VIEW_DRAFT"
ACTION_EXECUTE_ESIGN = "EXECUTE_ESIGN"
ACTION_DOWNLOAD_FINAL = "DOWNLOAD_FINAL"
ACTION_COMPLETED_ACK = "COMPLETED_ACK"


class UnauthorizedCapabilityError(Exception):
    pass


class TokenExpiredError(Exception):
    pass


def actions_for_role(role: str, signed: bool = False) -> List[str]:
    """Capability set for a party role. Witness tokens are downgraded once signed."""
    if role == "Witness":
        return [ACTION_COMPLETED_ACK] if signed else [ACTION_VIEW_DRAFT, ACTION_EXECUTE_ESIGN]
    actions = [ACTION_VIEW_DRAFT, ACTION_EXECUTE_ESIGN, ACTION_DOWNLOAD_FINAL]
    return actions


class CBACService:
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = (secret_key or settings.cbac_secret).encode("utf-8")

    def generate_token(
        self,
        agreement_id: str,
        party_id: str,
        role: str,
        allowed_actions: List[str],
        ttl_seconds: int = 604800,  # 7 days
    ) -> str:
        """
        Generate a cryptographically signed capability token.
        Token = base64url(payload) . hmac_sha256
        """
        payload = {
            "agr_id": agreement_id,
            "pty_id": party_id,
            "role": role,
            "actions": allowed_actions,
            "exp": int(time.time()) + ttl_seconds,
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        signature = hmac.new(self.secret_key, payload_bytes, hashlib.sha256).hexdigest()
        return f"{payload_b64}.{signature}"

    def decode_unverified(self, token: str) -> Dict[str, Any]:
        """Decode payload WITHOUT verifying. Only for routing hints, never for authorization."""
        if not token or "." not in token:
            raise UnauthorizedCapabilityError("Invalid capability token format")
        payload_b64 = token.split(".")[0]
        pad = len(payload_b64) % 4
        if pad:
            payload_b64 += "=" * (4 - pad)
        try:
            return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
        except Exception as exc:
            raise UnauthorizedCapabilityError("Unable to decode capability token payload") from exc

    def verify_token(
        self,
        token: str,
        required_agreement_id: str,
        required_action: str,
    ) -> Dict[str, Any]:
        """
        Validate capability token, verify signature, check expiration,
        prevent IDOR by matching required_agreement_id, and verify action permission.
        """
        if not token or "." not in token:
            raise UnauthorizedCapabilityError("Invalid capability token format")

        parts = token.split(".")
        if len(parts) != 2:
            raise UnauthorizedCapabilityError("Malformed capability token")

        payload_b64, signature = parts
        pad = len(payload_b64) % 4
        if pad:
            payload_b64 += "=" * (4 - pad)

        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64)
            payload = json.loads(payload_bytes.decode("utf-8"))
        except Exception:
            raise UnauthorizedCapabilityError("Unable to decode capability token payload")

        expected_sig = hmac.new(self.secret_key, payload_bytes, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            raise UnauthorizedCapabilityError("Cryptographic signature mismatch on capability token")

        if time.time() > payload.get("exp", 0):
            raise TokenExpiredError("Capability token has expired")

        if payload.get("agr_id") != required_agreement_id:
            raise UnauthorizedCapabilityError(
                f"IDOR Violation: Token issued for agreement {payload.get('agr_id')} cannot access {required_agreement_id}"
            )

        allowed_actions = payload.get("actions", [])
        if required_action not in allowed_actions:
            raise UnauthorizedCapabilityError(
                f"Action '{required_action}' not permitted. Authorized actions: {allowed_actions}"
            )

        if payload.get("role") == "Witness" and required_action == ACTION_DOWNLOAD_FINAL:
            raise UnauthorizedCapabilityError(
                "Witness Privacy Policy: Witnesses are restricted from post-execution contract retrieval"
            )

        return payload

    @staticmethod
    def sanitize_input(text: str) -> str:
        """Sanitize user input to prevent Cross-Site Scripting (XSS)."""
        if not text:
            return ""
        escaped = html.escape(text.strip())
        clean = re.sub(r"javascript:", "", escaped, flags=re.IGNORECASE)
        return clean

    @staticmethod
    def should_purge_draft(created_at_timestamp: float, consent_granted: bool, retention_days: int = 27) -> bool:
        """
        Evaluate if unexecuted draft should be purged.
        Drafts with consent=False are purged after retention_days.
        """
        if consent_granted:
            return False
        age_seconds = time.time() - created_at_timestamp
        return age_seconds > retention_days * 86400
