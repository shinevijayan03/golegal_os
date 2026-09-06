"""
Session-state helpers shared by every page.

Only the user's id is kept in the session; the User row is re-read per run so
role changes and suspensions take effect immediately.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st
from sqlalchemy.orm import Session

from domain.models import User
from security.auth import IngressContext
from services.agreement_service import empty_payload

NAV_ITEMS = ["Home", "Create agreement", "My agreements", "Copilot", "Account"]
ADMIN_ITEM = "Admin"


def current_user(session: Session) -> Optional[User]:
    uid = st.session_state.get("user_id")
    if not uid:
        return None
    user = session.query(User).filter_by(id=uid).first()
    if not user or not user.is_active:
        st.session_state.pop("user_id", None)
        return None
    return user


def sign_in(user: User) -> None:
    st.session_state["user_id"] = user.id
    st.session_state.pop("copilot_history", None)


def sign_out() -> None:
    for key in ("user_id", "wiz", "copilot_history", "security_alert", "active_signing_party"):
        st.session_state.pop(key, None)


def go(tab: str) -> None:
    st.session_state["active_tab"] = tab
    st.rerun()


def ingress_context() -> IngressContext:
    """Best-effort device/IP context from Streamlit's request headers; falls back to a stable per-session fingerprint."""
    ip, ua = "127.0.0.1", "Streamlit"
    try:
        headers = st.context.headers  # available in Streamlit >= 1.37
        ip = headers.get("X-Forwarded-For", headers.get("Remote-Addr", ip)).split(",")[0].strip() or ip
        ua = headers.get("User-Agent", ua)
    except Exception:
        pass
    override = st.session_state.get("ingress_override")
    if override:
        return IngressContext(**override)
    # Leave device_fingerprint unset: AuthService derives a stable one from the
    # user agent and IP subnet, so the same browser on the same network is
    # recognised across sessions instead of alerting on every sign-in.
    return IngressContext(ip_address=ip, user_agent=ua, geo_location="Bangalore, IN")


def wizard_state() -> Dict[str, Any]:
    """The live draft: step, payload, persisted agreement id and cached analyses."""
    if "wiz" not in st.session_state:
        st.session_state["wiz"] = {"step": 1, "payload": empty_payload(), "agreement_id": None, "quote": None,
                                   "risk": None, "summary": None, "dispatched": None, "estamp": None}
    return st.session_state["wiz"]


def reset_wizard(payload: Optional[Dict[str, Any]] = None, agreement_id: Optional[str] = None, step: int = 1) -> Dict[str, Any]:
    st.session_state["wiz"] = {"step": step, "payload": payload or empty_payload(), "agreement_id": agreement_id, "quote": None,
                               "risk": None, "summary": None, "dispatched": None, "estamp": None}
    st.session_state.pop("active_signing_party", None)
    return st.session_state["wiz"]
