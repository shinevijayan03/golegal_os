"""
Tests for Authentication, OTP login, password hashing and suspicious-ingress detection (TC-AUTH)
"""
import pytest

from domain.models import LoginEvent, User
from security.auth import AccountLockedError, AuthError, AuthService, IngressContext


class TestAuthService:
    def test_password_hash_roundtrip(self):
        h = AuthService.hash_password("Secret@123")
        assert h.startswith("pbkdf2_sha256$")
        assert AuthService.verify_password("Secret@123", h)
        assert not AuthService.verify_password("wrong", h)
        assert not AuthService.verify_password("x", None)

    def test_register_validates_and_creates_user(self, auth_svc, db_session):
        user = auth_svc.register("Anushka Verma", "Anushka@Example.com", "+91 98765 43215", "Str0ngPass!")
        assert user.email == "anushka@example.com"
        assert user.phone == "9876543215"
        assert db_session.query(User).filter_by(email="anushka@example.com").one()
        with pytest.raises(AuthError):
            auth_svc.register("Anushka Verma", "anushka@example.com", "9876543215", "Str0ngPass!")  # duplicate
        with pytest.raises(AuthError):
            auth_svc.register("X", "bad-email", "123", "short")

    def test_password_login_success_and_failure_journal(self, auth_svc, sample_users, db_session):
        result = auth_svc.login_with_password("mayank.tripathi@example.com", "Tenant@12345")
        assert result.user.id == "usr-tenant-001"
        assert result.suspicious is False  # first login sets the baseline
        with pytest.raises(AuthError):
            auth_svc.login_with_password("mayank.tripathi@example.com", "nope")
        events = db_session.query(LoginEvent).filter_by(user_id="usr-tenant-001").all()
        assert {e.success for e in events} == {True, False}

    def test_otp_login_flow_and_lockout(self, auth_svc, sample_users):
        otp = auth_svc.request_login_otp("9876543210")
        assert otp == "123456"
        for _ in range(4):
            with pytest.raises(AuthError):
                auth_svc.verify_login_otp("9876543210", "000000")
        with pytest.raises(AccountLockedError):
            auth_svc.verify_login_otp("9876543210", "000000")  # 5th failure locks
        with pytest.raises(AccountLockedError):
            auth_svc.request_login_otp("9876543210")  # cannot re-request while locked

    def test_otp_login_success(self, auth_svc, sample_users):
        auth_svc.request_login_otp("9876543211")
        result = auth_svc.verify_login_otp("9876543211", "123456")
        assert result.user.full_name == "Mayank Tripathi"
        with pytest.raises(AuthError):
            auth_svc.verify_login_otp("9876543211", "123456")  # consumed

    def test_suspicious_ingress_detection(self, auth_svc, sample_users):
        home = IngressContext(ip_address="49.207.10.5", user_agent="Chrome/Android", geo_location="Bangalore, IN")
        first = auth_svc.login_with_password("mayank.tripathi@example.com", "Tenant@12345", home)
        assert first.suspicious is False
        again = auth_svc.login_with_password("mayank.tripathi@example.com", "Tenant@12345", home)
        assert again.suspicious is False
        foreign = IngressContext(ip_address="198.51.100.24", user_agent="Headless Chrome Linux", geo_location="Bucharest, RO")
        alert = auth_svc.login_with_password("mayank.tripathi@example.com", "Tenant@12345", foreign)
        assert alert.suspicious is True
        assert len(alert.risk_reasons) == 3
        assert alert.event.alert_dispatched is True
        recent = auth_svc.recent_security_events(alert.user)
        assert recent[0].suspicious is True

    def test_change_password(self, auth_svc, sample_users):
        user = sample_users["owner"]
        with pytest.raises(AuthError):
            auth_svc.change_password(user, "wrong", "NewPass@123")
        auth_svc.change_password(user, "Owner@12345", "NewPass@123")
        assert auth_svc.login_with_password(user.email, "NewPass@123").user.id == user.id
