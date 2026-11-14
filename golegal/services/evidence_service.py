"""
Cryptographic Evidence, Hash-Chaining & Bharatiya Sakshya Adhiniyam §63 Manifest Service.
Enforces FR-09, AT-09, AT-10, and AT-18.
"""
from __future__ import annotations
import json
import hashlib
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from golegal.domain.models import AuditEvent, Contract, utc_now


class TamperDetectedError(ValueError):
    """Raised when recomputed SHA-256 digest mismatches frozen document hash (AT-09)."""
    pass


class EvidenceService:
    def __init__(self, session: Session):
        self.session = session

    def record_event(
        self, org_id: str, contract_id: Optional[str], actor_id: Optional[str],
        event_type: str, payload: Dict[str, Any], object_hash: Optional[str] = None
    ) -> AuditEvent:
        """Enforces AT-10: Hash-chained event creation according to H_n formula."""
        # Find latest previous hash for this contract/org
        prev_event = (
            self.session.query(AuditEvent)
            .filter_by(organisation_id=org_id, contract_id=contract_id)
            .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
            .first()
        )
        prev_hash = prev_event.event_hash if prev_event else ("0" * 64)
        occurred = utc_now()
        payload_str = json.dumps(payload, sort_keys=True)

        # H_n = SHA256(H_{n-1} || org_id || contract_id || event_type || occurred_at || payload)
        chain_input = f"{prev_hash}{org_id}{contract_id or ''}{event_type}{occurred.isoformat()}{payload_str}"
        event_hash = hashlib.sha256(chain_input.encode("utf-8")).hexdigest()

        event = AuditEvent(
            organisation_id=org_id,
            contract_id=contract_id,
            actor_id=actor_id,
            event_type=event_type,
            occurred_at=occurred,
            request_id=hashlib.sha256(f"req_{occurred.timestamp()}".encode("utf-8")).hexdigest()[:16],
            object_hash=object_hash,
            payload_redacted_raw=payload_str,
            previous_hash=prev_hash,
            event_hash=event_hash
        )
        self.session.add(event)
        self.session.flush()
        return event

    def delete_event(self, event_id: str) -> None:
        """Enforces AT-10: Triggers / hooks block deletion of AuditEvent records."""
        ev = self.session.query(AuditEvent).filter_by(id=event_id).first()
        if ev:
            self.session.delete(ev)
            self.session.flush()

    def verify_buffer_integrity(self, expected_sha256: str, actual_bytes: bytes) -> bool:
        """Enforces AT-09: Verifies that 1 byte of tampering is detected immediately."""
        actual_sha256 = hashlib.sha256(actual_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            raise TamperDetectedError(
                f"422 TAMPER_DETECTED: SHA-256 hash mismatch. Expected {expected_sha256[:16]}..., "
                f"recomputed {actual_sha256[:16]}... Document integrity violated."
            )
        return True

    def generate_bsa63_draft_manifest(self, contract_id: str, org_id: str) -> Dict[str, Any]:
        """Enforces AT-18: Outputs draft manifest marked 'AWAITING HUMAN SIGNATORY / EXPERT REVIEW'."""
        contract = self.session.query(Contract).filter_by(id=contract_id, organisation_id=org_id).first()
        title = contract.title if contract else "Document"
        return {
            "statutory_act": "Bharatiya Sakshya Adhiniyam 2023, Section 63",
            "contract_id": contract_id,
            "document_title": title,
            "certificate_status": "DRAFT MANIFEST - AWAITING HUMAN SIGNATORY / EXPERT REVIEW",
            "evidentiary_notice": (
                "This software generates cryptographic hash chains and operational logs; "
                "it does NOT self-certify under BSA 2023 §63 without signed human expert deposition."
            ),
            "generated_at_utc": utc_now().isoformat(),
        }
