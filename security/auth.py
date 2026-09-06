"""
GoLegal Authentication, Registration & Suspicious-Ingress Detection

- Password hashing: PBKDF2-HMAC-SHA256 with per-user random salt (stdlib only).
- Mobile OTP login: DB-persisted challenge with expiry, attempt counter and lockout.
- Suspicious ingress: every login is journaled; a login is flagged when the
  device fingerprint, IP subnet, or geo-location has never been seen for the
  account before, and an alert record is written (PRD US-02).
"""
from __future__ import annotations

import base64
import hashlib
import re
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from config import settings
from domain.models import LoginEvent, OtpChallenge, User, utc_now
from services.validation import validate_email, validate_phone


class AuthError(Exception):
    pass


class AccountLockedError(AuthError):
    pass


@dataclass
class IngressContext:
    ip_address: str = "127.0.0.1"
    user_agent: str = "Mozilla/5.0"
    device_fingerprint: Optional[str] = None
    geo_location: str = "Bangalore, IN"

    def fingerprint(self) -> str:
        if self.device_fingerprint:
            return self.device_fingerprint
        return hashlib.sha256(f"{self.user_agent}|{self.ip_address.rsplit('.', 1)[0]}".encode()).hexdigest()[:32]


@dataclass
class LoginResult:
    user: User
    event: LoginEvent
    suspicious: bool = False
    risk_reasons: list = field(default_factory=list)


class AuthService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ passwords
    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, settings.password_iterations)
        return f"pbkdf2_sha256${settings.password_iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"

    @staticmethod
    def verify_password(password: str, stored: Optional[str]) -> bool:
        if not stored:
            return False
        try:
            _, iterations, salt_b64, digest_b64 = stored.split("$")
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(digest_b64)
        except (ValueError, TypeError):
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)

    # ------------------------------------------------------------------ registration
    def register(self, full_name: str, email: str, phone: str, password: Optional[str] = None,
                 state_code: str = "KA", address: Optional[str] = None) -> User:
        if not full_name or len(full_name.strip()) < 2:
            raise AuthError("Please enter your full legal name.")
        if not validate_email(email):
            raise AuthError("Please enter a valid email address.")
        if not validate_phone(phone):
            raise AuthError("Please enter a valid 10-digit Indian mobile number.")
        email = email.strip().lower()
        if self.session.query(User).filter_by(email=email).first():
            raise AuthError("An account with this email already exists. Sign in instead.")
        if password is not None and len(password) < 8:
            raise AuthError("Password must be at least 8 characters.")
        user = User(
            full_name=full_name.strip(),
            email=email,
            phone=re.sub(r"\D", "", phone)[-10:],
            state_code=state_code,
            address=address,
            password_hash=self.hash_password(password) if password else None,
        )
        self.session.add(user)
        self.session.commit()
        return user

    # ------------------------------------------------------------------ OTP login
    def request_login_otp(self, phone: str) -> str:
        """Issue an OTP challenge for a mobile number. Returns the OTP in mock mode."""
        if not validate_phone(phone):
            raise AuthError("Please enter a valid 10-digit Indian mobile number.")
        phone = re.sub(r"\D", "", phone)[-10:]
        self._assert_not_locked(phone, "LOGIN")
        otp = settings.mock_otp if settings.mock_gateways else f"{secrets.randbelow(10**6):06d}"
        # Invalidate previous open challenges
        for old in self.session.query(OtpChallenge).filter_by(subject=phone, purpose="LOGIN", consumed=False):
            old.consumed = True
        self.session.add(OtpChallenge(
            subject=phone,
            purpose="LOGIN",
            otp_hash=self._hash_otp(otp),
            expires_at=utc_now() + timedelta(seconds=settings.otp_ttl_seconds),
        ))
        self.session.commit()
        return otp

    def verify_login_otp(self, phone: str, otp: str, ctx: Optional[IngressContext] = None,
                         full_name_if_new: Optional[str] = None) -> LoginResult:
        phone = re.sub(r"\D", "", phone or "")[-10:]
        ctx = ctx or IngressContext()
        challenge = self._latest_challenge(phone, "LOGIN")
        if not challenge:
            self._journal(None, phone, "OTP", ctx, success=False)
            raise AuthError("No active OTP. Please request a new code.")
        self._check_challenge(challenge, otp)

        user = self.session.query(User).filter_by(phone=phone).first()
        if not user:
            if not full_name_if_new:
                raise AuthError("New number detected. Please register with your name and email first.")
            user = User(full_name=full_name_if_new, email=f"{phone}@golegal.local", phone=phone, state_code="KA")
            self.session.add(user)
            self.session.flush()
        return self._finish_login(user, phone, "OTP", ctx)

    # ------------------------------------------------------------------ password login
    def login_with_password(self, email: str, password: str, ctx: Optional[IngressContext] = None) -> LoginResult:
        ctx = ctx or IngressContext()
        email = (email or "").strip().lower()
        user = self.session.query(User).filter_by(email=email).first()
        if not user or not self.verify_password(password, user.password_hash):
            self._journal(user.id if user else None, email, "PASSWORD", ctx, success=False)
            raise AuthError("Email or password is incorrect.")
        if not user.is_active:
            raise AccountLockedError("This account has been suspended. Contact support@golegal.in.")
        return self._finish_login(user, email, "PASSWORD", ctx)

    def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if user.password_hash and not self.verify_password(current_password, user.password_hash):
            raise AuthError("Current password is incorrect.")
        if len(new_password) < 8:
            raise AuthError("New password must be at least 8 characters.")
        user.password_hash = self.hash_password(new_password)
        self.session.commit()

    # ------------------------------------------------------------------ suspicious ingress
    def assess_ingress(self, user: User, ctx: IngressContext) -> list[str]:
        """Compare this login against the account's history. Returns risk reasons (empty = normal)."""
        history = (
            self.session.query(LoginEvent)
            .filter_by(user_id=user.id, success=True)
            .order_by(LoginEvent.created_at.desc())
            .limit(50)
            .all()
        )
        if not history:
            return []  # first ever login establishes the baseline
        reasons = []
        known_fps = {h.device_fingerprint for h in history}
        known_subnets = {h.ip_address.rsplit(".", 1)[0] for h in history if h.ip_address}
        known_geos = {(h.geo_location or "").lower() for h in history}
        if ctx.fingerprint() not in known_fps:
            reasons.append("Unrecognised device or browser fingerprint")
        if ctx.ip_address.rsplit(".", 1)[0] not in known_subnets:
            reasons.append(f"New IP network ({ctx.ip_address})")
        if (ctx.geo_location or "").lower() not in known_geos:
            reasons.append(f"New location ({ctx.geo_location})")
        return reasons

    def recent_security_events(self, user: User, limit: int = 10) -> list[LoginEvent]:
        return (
            self.session.query(LoginEvent)
            .filter_by(user_id=user.id)
            .order_by(LoginEvent.created_at.desc())
            .limit(limit)
            .all()
        )

    # ------------------------------------------------------------------ internals
    def _finish_login(self, user: User, identifier: str, method: str, ctx: IngressContext) -> LoginResult:
        reasons = self.assess_ingress(user, ctx)
        event = self._journal(user.id, identifier, method, ctx, success=True, reasons=reasons)
        user.last_login_at = utc_now()
        self.session.commit()
        return LoginResult(user=user, event=event, suspicious=bool(reasons), risk_reasons=reasons)

    def _journal(self, user_id, identifier, method, ctx: IngressContext, success: bool, reasons=None) -> LoginEvent:
        reasons = reasons or []
        event = LoginEvent(
            user_id=user_id,
            identifier=identifier,
            method=method,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            device_fingerprint=ctx.fingerprint(),
            geo_location=ctx.geo_location,
            success=success,
            suspicious=bool(reasons),
            risk_reasons=json.dumps(reasons),
            alert_dispatched=bool(reasons),  # mock email/SMS alert dispatched synchronously
        )
        self.session.add(event)
        self.session.commit()
        return event

    @staticmethod
    def _hash_otp(otp: str) -> str:
        return hashlib.sha256(f"{settings.cbac_secret}:{otp}".encode()).hexdigest()

    def _latest_challenge(self, subject: str, purpose: str) -> Optional[OtpChallenge]:
        return (
            self.session.query(OtpChallenge)
            .filter_by(subject=subject, purpose=purpose, consumed=False)
            .order_by(OtpChallenge.created_at.desc())
            .first()
        )

    def _assert_not_locked(self, subject: str, purpose: str) -> None:
        latest = (
            self.session.query(OtpChallenge)
            .filter_by(subject=subject, purpose=purpose)
            .order_by(OtpChallenge.created_at.desc())
            .first()
        )
        if latest and latest.locked_until and latest.locked_until > utc_now():
            raise AccountLockedError("Too many failed attempts. Try again in 15 minutes.")

    def _check_challenge(self, challenge: OtpChallenge, otp: str) -> None:
        now = utc_now()
        if challenge.locked_until and challenge.locked_until > now:
            raise AccountLockedError("Too many failed attempts. Try again in 15 minutes.")
        if challenge.expires_at < now:
            raise AuthError("This OTP has expired. Please request a new code.")
        if not hmac.compare_digest(self._hash_otp((otp or "").strip()), challenge.otp_hash):
            challenge.attempts += 1
            remaining = settings.otp_max_attempts - challenge.attempts
            if remaining <= 0:
                challenge.locked_until = now + timedelta(seconds=settings.otp_lockout_seconds)
                self.session.commit()
                raise AccountLockedError("Too many failed attempts. Try again in 15 minutes.")
            self.session.commit()
            raise AuthError(f"Incorrect OTP. {remaining} attempts remaining.")
        challenge.consumed = True
        self.session.commit()
