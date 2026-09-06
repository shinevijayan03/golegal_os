"""
GoLegal Agreement Workflow & Asynchronous Signing State Machine

Owns every lifecycle transition:
  Draft -> Paid -> Pending_Signatures -> Completed (sealed)
                                     -> Expired (signing window breached)
  Draft / Paid / Pending_Signatures -> Cancelled

plus the operational jobs an autonomous platform needs: invitation dispatch,
reminders, expiry sweeps, consent-based draft purge and cryptographic sealing.
"""
from __future__ import annotations

import json
import socket
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from domain.models import Agreement, AuditLog, Party, Signature, SysConfig, utc_now
from security.cbac import CBACService, actions_for_role
from services.doc_assembly import DocumentAssemblyEngine
from services.document_service import DocumentService
from services.notification import NotificationService
from services.rule_engine import calculate_stamp_duty, get_default_clauses


class InvalidStateTransitionError(Exception):
    pass


class WorkflowService:
    VALID_TRANSITIONS = {
        "Draft": ["Paid", "Cancelled"],
        "Paid": ["Pending_Signatures", "Cancelled"],
        "Pending_Signatures": ["Completed", "Expired", "Cancelled"],
        "Completed": [],
        "Cancelled": [],
        "Expired": [],
    }

    def __init__(self, session: Session, notifier: Optional[NotificationService] = None):
        self.session = session
        self.cbac = CBACService()
        self.notifier = notifier or NotificationService(session=session, cbac_svc=self.cbac)
        self.documents = DocumentService(session)
        self.engine = DocumentAssemblyEngine()

    # ------------------------------------------------------------------ audit helper
    def _audit(self, agreement_id: str, event_type: str, triggered_by: str, data: Dict[str, Any]) -> None:
        self.session.add(AuditLog(agreement_id=agreement_id, event_type=event_type, triggered_by=triggered_by,
                                  event_data=json.dumps(data, default=str)))

    # ------------------------------------------------------------------ transitions
    def transition_state(self, agreement: Agreement, new_state: str, triggered_by: str = "SYSTEM"):
        """Enforce strict lifecycle transitions."""
        current = agreement.status
        allowed = self.VALID_TRANSITIONS.get(current, [])
        if new_state not in allowed:
            raise InvalidStateTransitionError(
                f"Cannot transition agreement from '{current}' to '{new_state}'. Permitted: {allowed}"
            )
        agreement.status = new_state
        if new_state == "Completed":
            agreement.executed_at = utc_now()
        self._audit(agreement.id, "STATE_TRANSITION", triggered_by,
                    {"from_state": current, "to_state": new_state, "timestamp": utc_now().isoformat()})
        self.session.commit()

    def open_for_signatures(self, agreement: Agreement, triggered_by: str = "INITIATOR",
                            dispatch: bool = True) -> List[Dict[str, Any]]:
        """Paid -> Pending_Signatures: mint capability tokens for every party and dispatch invitations."""
        if agreement.status == "Pending_Signatures":
            return []
        self.transition_state(agreement, "Pending_Signatures", triggered_by)
        agreement.expires_at = utc_now() + timedelta(days=settings.signing_link_ttl_days)
        dispatched = []
        for party in agreement.parties:
            party.access_token = self.notifier.generate_signing_url(agreement.id, party.id, party.party_type).split("sign_token=")[1].split("&")[0]
            party.access_token_expires_at = agreement.expires_at
            if party.signing_status == "Pending":
                party.signing_status = "Sent"
            if dispatch:
                dispatched.append(self.notifier.dispatch_signing_invitation(
                    agreement_id=agreement.id, party_name=party.full_name, party_phone=party.phone,
                    party_email=party.email, party_role=party.party_type, party_id=party.id,
                    triggered_by=triggered_by, agreement_title=agreement.display_title,
                ))
                party.last_notified_at = utc_now()
        self._audit(agreement.id, "SIGN_LINKS_DISPATCHED", triggered_by,
                    {"parties": [p.id for p in agreement.parties], "expires_at": agreement.expires_at})
        self.session.commit()
        return dispatched

    def signing_url_for(self, party: Party) -> str:
        signed = party.signing_status == "Signed"
        return self.notifier.generate_signing_url(party.agreement_id, party.id, party.party_type, signed=signed)

    def resend_invitations(self, agreement: Agreement, party_ids: Optional[List[str]] = None,
                           triggered_by: str = "INITIATOR") -> List[Dict[str, Any]]:
        targets = [p for p in agreement.parties if p.signing_status != "Signed" and (not party_ids or p.id in party_ids)]
        sent = self.notifier.remind_pending_parties(targets, triggered_by=triggered_by)
        if sent:
            self._audit(agreement.id, "REMINDER_SENT", triggered_by, {"party_ids": [p.id for p in targets]})
            self.session.commit()
        return sent

    def cancel(self, agreement: Agreement, triggered_by: str = "INITIATOR") -> None:
        self.transition_state(agreement, "Cancelled", triggered_by)

    # ------------------------------------------------------------------ signing completion
    def check_and_complete_signing(self, agreement_id: str) -> bool:
        """
        Evaluate non-atomic multi-party signing progress.
        If all designated owners, tenants, and witnesses have signed,
        atomically transition agreement to 'Completed' and seal the document.
        """
        agreement = self.session.query(Agreement).filter_by(id=agreement_id).first()
        if not agreement:
            raise ValueError("Agreement not found")

        if agreement.status != "Pending_Signatures":
            return agreement.status == "Completed"

        parties = self.session.query(Party).filter_by(agreement_id=agreement_id).all()
        if not parties:
            return False

        if all(p.signing_status == "Signed" for p in parties):
            self.transition_state(agreement, "Completed", triggered_by="SIGNING_COMPLETION_ENGINE")
            self.seal_agreement(agreement)
            return True
        return False

    def get_signing_progress(self, agreement_id: str) -> dict:
        """Return real-time signatory completion matrix."""
        parties = self.session.query(Party).filter_by(agreement_id=agreement_id).all()
        total = len(parties)
        signed_count = sum(1 for p in parties if p.signing_status == "Signed")
        return {
            "agreement_id": agreement_id,
            "total_parties": total,
            "signed_count": signed_count,
            "all_signed": total > 0 and signed_count == total,
            "parties": [
                {"party_id": p.id, "name": p.full_name, "type": p.party_type, "email": p.email,
                 "phone": p.phone, "status": p.signing_status, "reminders": p.reminder_count or 0}
                for p in parties
            ],
        }

    # ------------------------------------------------------------------ document build
    def build_agreement_payload(self, agreement: Agreement) -> Dict[str, Any]:
        prop = agreement.get_property_details()
        terms = agreement.get_commercial_terms()
        clauses = get_default_clauses(agreement.get_clause_toggles(), agreement.agreement_type)
        quote = calculate_stamp_duty(agreement.state_code, terms.get("monthly_rent", 0),
                                     terms.get("security_deposit", 0), int(terms.get("lease_months", 11) or 11))
        address = ", ".join(x for x in [prop.get("premises_name"), prop.get("address"), prop.get("city"),
                                        str(prop.get("pincode", "")).strip()] if x)
        return {
            "agreement_id": agreement.id,
            "agreement_type": agreement.agreement_type,
            "state_code": agreement.state_code,
            "city": prop.get("city", ""),
            "property_address": address,
            "inclusions": prop.get("inclusions", ""),
            "monthly_rent": float(terms.get("monthly_rent", 0) or 0),
            "security_deposit": float(terms.get("security_deposit", 0) or 0),
            "lease_months": int(terms.get("lease_months", 11) or 11),
            "lease_start": terms.get("lease_start", ""),
            "lock_in_months": int(terms.get("lock_in_months", 0) or 0),
            "notice_days": int(terms.get("notice_days", 30) or 30),
            "rent_due_day": int(terms.get("rent_due_day", 5) or 5),
            "escalation_pct": terms.get("escalation_pct", 5),
            "consideration": quote["consideration"],
            "stamp_duty": quote["stamp_duty_amount"],
            "clauses": clauses,
            "custom_clauses": agreement.custom_clauses or "",
            "executed_on": agreement.executed_at or utc_now(),
        }

    @staticmethod
    def party_dicts(agreement: Agreement) -> List[Dict[str, Any]]:
        return [{"id": p.id, "name": p.full_name, "type": p.party_type, "phone": p.phone, "email": p.email,
                 "pan": p.pan, "address": p.address, "aadhaar_masked": p.aadhaar_masked,
                 "status": p.signing_status} for p in agreement.parties]

    def signature_dicts(self, agreement: Agreement) -> List[Dict[str, Any]]:
        sigs = self.session.query(Signature).filter_by(agreement_id=agreement.id).order_by(Signature.signed_at).all()
        party_map = {p.id: p for p in agreement.parties}
        return [{"party_name": party_map[s.party_id].full_name if s.party_id in party_map else "Signatory",
                 "party_type": party_map[s.party_id].party_type if s.party_id in party_map else "Party",
                 "signed_at": s.signed_at, "ip_address": s.ip_address, "signature_hash": s.signature_hash,
                 "transaction_ref": s.transaction_ref} for s in sigs]

    def estamp_dict(self, agreement: Agreement) -> Optional[Dict[str, Any]]:
        e = agreement.estamp
        if not e:
            return None
        return {"certificate_number": e.certificate_number, "stamp_amount": e.stamp_amount, "state_code": e.state_code,
                "purchased_by": e.purchased_by, "issued_at": e.issued_at}

    def build_pdf(self, agreement: Agreement, is_draft: bool) -> bytes:
        audit_events = [{"recorded_at": a.recorded_at, "event_type": a.event_type, "triggered_by": a.triggered_by}
                        for a in sorted(agreement.audit_logs, key=lambda x: x.recorded_at or utc_now())]
        return self.engine.generate_pdf_agreement(
            agreement_data=self.build_agreement_payload(agreement),
            parties=self.party_dicts(agreement),
            estamp=self.estamp_dict(agreement),
            signatures=None if is_draft else self.signature_dicts(agreement),
            is_draft=is_draft,
            audit={"server_host": socket.gethostname(), "events": audit_events,
                   "generated_at": utc_now(), "sealed_at": agreement.executed_at},
        )

    def seal_agreement(self, agreement: Agreement) -> bytes:
        """Generate the final PDF exactly once, persist it, record its digest, downgrade witness tokens, notify."""
        existing = self.documents.latest(agreement.id, "FINAL")
        if existing and agreement.final_pdf_sha256 == existing.sha256:
            return existing.content
        pdf = self.build_pdf(agreement, is_draft=False)
        doc = self.documents.store(agreement.id, "FINAL", f"GoLegal_Sealed_{agreement.id[:8]}.pdf", pdf)
        agreement.final_pdf_url = f"/documents/{doc.id}"
        agreement.final_pdf_sha256 = doc.sha256
        for party in agreement.parties:
            party.access_token = self.cbac.generate_token(agreement.id, party.id, party.party_type,
                                                          actions_for_role(party.party_type, signed=True),
                                                          ttl_seconds=settings.agreement_retain_days * 86400)
            self.notifier.dispatch_completion_notice(agreement.id, party, download_allowed=party.party_type != "Witness")
        self._audit(agreement.id, "DOCUMENT_SEALED", "GOLEGAL_CORPORATE_DSC",
                    {"final_sha256": doc.sha256, "size_bytes": doc.size_bytes, "server_host": socket.gethostname()})
        self.session.commit()
        return pdf

    def final_pdf(self, agreement: Agreement) -> Optional[bytes]:
        doc = self.documents.latest(agreement.id, "FINAL")
        return doc.content if doc else None

    # ------------------------------------------------------------------ scheduled jobs
    def expire_stale_agreements(self, now=None) -> int:
        now = now or utc_now()
        stale = (self.session.query(Agreement)
                 .filter(Agreement.status == "Pending_Signatures", Agreement.expires_at.isnot(None), Agreement.expires_at < now)
                 .all())
        for agr in stale:
            self.transition_state(agr, "Expired", triggered_by="EXPIRY_SWEEP")
        return len(stale)

    def purge_unconsented_drafts(self, now=None) -> int:
        """Zero document hoarding: delete unexecuted drafts without storage consent past the retention window."""
        now = now or utc_now()
        config = self.session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
        days = config.data_pruning_days if config else settings.draft_pruning_days
        cutoff = now - timedelta(days=days)
        victims = (self.session.query(Agreement)
                   .filter(Agreement.status.in_(["Draft", "Cancelled", "Expired"]),
                           Agreement.cloud_storage_consent.is_(False), Agreement.created_at < cutoff)
                   .all())
        for agr in victims:
            self.session.delete(agr)
        self.session.commit()
        return len(victims)

    def run_reminder_sweep(self, now=None, min_hours_between: int = 20) -> int:
        """Daily reminder cron: nudge every pending party not contacted in the last day."""
        now = now or utc_now()
        pending = (self.session.query(Party).join(Agreement)
                   .filter(Agreement.status == "Pending_Signatures", Party.signing_status != "Signed").all())
        due = [p for p in pending if not p.last_notified_at or (now - p.last_notified_at) >= timedelta(hours=min_hours_between)]
        sent = self.notifier.remind_pending_parties(due, triggered_by="REMINDER_CRON")
        return len(sent)
