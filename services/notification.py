"""
GoLegal Notification & Dispatch Service
Handles multi-party sign invitations, tokenized WhatsApp/SMS/Email dispatches, reminders,
and completion notices. Every dispatch is journaled in the notifications table when a
database session is supplied (the in-memory list is kept for lightweight use and tests).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from domain.models import Notification, Party, utc_now
from security.cbac import CBACService, actions_for_role


class NotificationService:
    def __init__(self, base_url: Optional[str] = None, cbac_svc: Optional[CBACService] = None,
                 session: Optional[Session] = None):
        self.base_url = base_url or settings.base_url
        self.cbac_svc = cbac_svc or CBACService()
        self.session = session
        self.dispatched_messages: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ links
    def generate_signing_url(self, agreement_id: str, party_id: str, role: str, signed: bool = False,
                             ttl_seconds: Optional[int] = None) -> str:
        """Generate a tokenized capability signing link."""
        token = self.cbac_svc.generate_token(
            agreement_id=agreement_id,
            party_id=party_id,
            role=role,
            allowed_actions=actions_for_role(role, signed=signed),
            ttl_seconds=ttl_seconds or settings.signing_link_ttl_days * 86400,
        )
        return f"{self.base_url}?sign_token={token}&agr_id={agreement_id}&party_id={party_id}"

    # ------------------------------------------------------------------ dispatch
    def _record(self, payload: Dict[str, Any], kind: str, triggered_by: str) -> Dict[str, Any]:
        self.dispatched_messages.append(payload)
        if self.session is not None:
            self.session.add(Notification(
                agreement_id=payload["agreement_id"],
                party_id=payload.get("party_id"),
                kind=kind,
                channel=payload.get("channel", "ALL"),
                recipient=payload.get("phone") or payload.get("email") or "-",
                message=payload["message"],
                signing_url=payload.get("signing_url"),
                status=payload.get("status", "SENT"),
                triggered_by=triggered_by,
            ))
            self.session.commit()
        return payload

    def dispatch_signing_invitation(
        self,
        agreement_id: str,
        party_name: str,
        party_phone: str,
        party_email: str,
        party_role: str,
        party_id: str,
        channel: str = "ALL",
        triggered_by: str = "SYSTEM",
        agreement_title: str = "a legally binding rental agreement",
    ) -> Dict[str, Any]:
        """Dispatch personalized signing invitation via SMS, WhatsApp, and Email."""
        signing_url = self.generate_signing_url(agreement_id, party_id, party_role)
        message_body = (
            f"Hello {party_name}, you have been invited to review and e-sign {agreement_title} "
            f"as {party_role} on GoLegal. Click here to sign securely: {signing_url}"
        )
        payload = {
            "agreement_id": agreement_id,
            "party_id": party_id,
            "party_name": party_name,
            "phone": party_phone,
            "email": party_email,
            "role": party_role,
            "channel": channel,
            "signing_url": signing_url,
            "message": message_body,
            "status": "SENT",
        }
        kind = "REMINDER" if "REMINDER" in channel.upper() else "INVITE"
        return self._record(payload, kind, triggered_by)

    def dispatch_completion_notice(self, agreement_id: str, party: Party, download_allowed: bool,
                                   triggered_by: str = "SEALING_ENGINE") -> Dict[str, Any]:
        if download_allowed:
            url = self.generate_signing_url(agreement_id, party.id, party.party_type, signed=True)
            body = (f"Hello {party.full_name}, all parties have signed. Your sealed, e-stamped agreement is ready. "
                    f"Download it here: {url}")
        else:
            url = None
            body = (f"Hello {party.full_name}, thank you for attesting as witness. The agreement has been sealed. "
                    f"As a witness you will not receive a copy of the executed deed.")
        payload = {
            "agreement_id": agreement_id, "party_id": party.id, "party_name": party.full_name,
            "phone": party.phone, "email": party.email, "role": party.party_type, "channel": "ALL",
            "signing_url": url, "message": body, "status": "SENT",
        }
        return self._record(payload, "COMPLETION", triggered_by)

    def dispatch_security_alert(self, user_email: str, reasons: List[str], ip: str) -> Dict[str, Any]:
        body = (f"Security alert: a sign-in to your GoLegal account was detected from {ip}. "
                f"Reasons: {'; '.join(reasons)}. If this was not you, reset your password immediately.")
        payload = {"agreement_id": None, "email": user_email, "channel": "EMAIL", "message": body, "status": "SENT"}
        self.dispatched_messages.append(payload)
        return payload

    # ------------------------------------------------------------------ reminders
    def run_daily_reminder_scheduler(self, pending_parties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Daily reminder cron for parties who have not completed their signatures."""
        reminders = []
        for p in pending_parties:
            if p.get("signing_status") != "Signed":
                reminders.append(self.dispatch_signing_invitation(
                    agreement_id=p["agreement_id"],
                    party_name=p["full_name"],
                    party_phone=p["phone"],
                    party_email=p["email"],
                    party_role=p["party_type"],
                    party_id=p["id"],
                    channel="WHATSAPP_REMINDER",
                    triggered_by="REMINDER_CRON",
                ))
        return reminders

    def remind_pending_parties(self, parties: List[Party], triggered_by: str = "REMINDER_CRON") -> List[Dict[str, Any]]:
        """ORM-aware reminder that also updates reminder counters."""
        sent = []
        for party in parties:
            if party.signing_status == "Signed":
                continue
            sent.append(self.dispatch_signing_invitation(
                agreement_id=party.agreement_id, party_name=party.full_name, party_phone=party.phone,
                party_email=party.email, party_role=party.party_type, party_id=party.id,
                channel="WHATSAPP_REMINDER", triggered_by=triggered_by,
            ))
            party.reminder_count = (party.reminder_count or 0) + 1
            party.last_notified_at = utc_now()
        if self.session is not None and sent:
            self.session.commit()
        return sent

    def history(self, agreement_id: str) -> List[Notification]:
        if self.session is None:
            return []
        return (self.session.query(Notification).filter_by(agreement_id=agreement_id)
                .order_by(Notification.created_at.desc()).all())
