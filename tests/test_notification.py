"""
Tests for Notification & Sign Dispatch Service
"""
import pytest
from services.notification import NotificationService
from security.cbac import CBACService


class TestNotificationService:
    @pytest.fixture
    def notif_svc(self):
        cbac = CBACService(secret_key="test_notif_secret")
        return NotificationService(base_url="http://localhost:8501", cbac_svc=cbac)

    def test_generate_signing_url(self, notif_svc):
        url = notif_svc.generate_signing_url("agr-100", "pty-100", "Tenant")
        assert "http://localhost:8501?sign_token=" in url
        assert "&agr_id=agr-100" in url
        assert "&party_id=pty-100" in url

    def test_dispatch_signing_invitation(self, notif_svc):
        payload = notif_svc.dispatch_signing_invitation(
            agreement_id="agr-100",
            party_name="Mayank Tripathi",
            party_phone="9876543211",
            party_email="mayank@example.com",
            party_role="Tenant",
            party_id="pty-100",
            channel="WHATSAPP"
        )
        assert payload["status"] == "SENT"
        assert payload["party_name"] == "Mayank Tripathi"
        assert "sign securely" in payload["message"]
        assert len(notif_svc.dispatched_messages) == 1

    def test_daily_reminder_scheduler(self, notif_svc):
        pending = [
            {"agreement_id": "agr-100", "id": "p1", "full_name": "Tenant 1", "phone": "9876543211", "email": "t1@ex.com", "party_type": "Tenant", "signing_status": "Pending"},
            {"agreement_id": "agr-100", "id": "p2", "full_name": "Owner 1", "phone": "9876543210", "email": "o1@ex.com", "party_type": "Owner", "signing_status": "Signed"},
            {"agreement_id": "agr-100", "id": "p3", "full_name": "Witness 1", "phone": "9876543212", "email": "w1@ex.com", "party_type": "Witness", "signing_status": "Pending"},
        ]
        reminders = notif_svc.run_daily_reminder_scheduler(pending)
        # Should dispatch reminders only to pending parties (p1 and p3)
        assert len(reminders) == 2
        names = [r["party_name"] for r in reminders]
        assert "Tenant 1" in names
        assert "Witness 1" in names
        assert "Owner 1" not in names
