"""
GoLegal Notification & Dispatch Service
Handles multi-party sign invitations, tokenized WhatsApp/SMS dispatches, and daily reminder scheduler.
"""
from typing import Dict, List, Any
from security.cbac import CBACService


class NotificationService:
    def __init__(self, base_url: str = "http://localhost:8501", cbac_svc: CBACService = None):
        self.base_url = base_url
        self.cbac_svc = cbac_svc or CBACService()
        self.dispatched_messages: List[Dict[str, Any]] = []

    def generate_signing_url(self, agreement_id: str, party_id: str, role: str) -> str:
        """Generate a tokenized capability signing link."""
        allowed_actions = ["VIEW_DRAFT", "EXECUTE_ESIGN"]
        if role in ["Owner", "Tenant"]:
            allowed_actions.append("DOWNLOAD_FINAL")

        token = self.cbac_svc.generate_token(
            agreement_id=agreement_id,
            party_id=party_id,
            role=role,
            allowed_actions=allowed_actions
        )
        return f"{self.base_url}?sign_token={token}&agr_id={agreement_id}&party_id={party_id}"

    def dispatch_signing_invitation(
        self,
        agreement_id: str,
        party_name: str,
        party_phone: str,
        party_email: str,
        party_role: str,
        party_id: str,
        channel: str = "ALL"
    ) -> Dict[str, Any]:
        """Dispatch personalized signing invitation via SMS, WhatsApp, and Email."""
        signing_url = self.generate_signing_url(agreement_id, party_id, party_role)
        message_body = (
            f"Hello {party_name}, you have been invited to review and e-sign a legally binding rental agreement "
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
            "status": "SENT"
        }
        self.dispatched_messages.append(payload)
        return payload

    def run_daily_reminder_scheduler(self, pending_parties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Simulate daily reminder cron for parties who have not completed their signatures."""
        reminders = []
        for p in pending_parties:
            if p.get("signing_status") != "Signed":
                r = self.dispatch_signing_invitation(
                    agreement_id=p["agreement_id"],
                    party_name=p["full_name"],
                    party_phone=p["phone"],
                    party_email=p["email"],
                    party_role=p["party_type"],
                    party_id=p["id"],
                    channel="WHATSAPP_REMINDER"
                )
                reminders.append(r)
        return reminders
