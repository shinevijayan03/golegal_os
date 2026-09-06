"""
GoLegal - Digital contracting, e-Stamping and multi-party Aadhaar eSign.

Entry point and router. Two entry paths:
  1. The product itself (landing, wizard, workspace, Copilot, admin).
  2. A capability link (?sign_token=...) which opens the counterparty signing
     page with no account required - the token is the credential.
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="GoLegal · Digital contracting & e-Stamping",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ai.llm import get_llm_client  # noqa: E402
from config import settings  # noqa: E402
from persistence.database import SessionLocal, init_db  # noqa: E402
from ui import components as c  # noqa: E402
from ui.admin import render_admin  # noqa: E402
from ui.auth_profile import render_auth_profile  # noqa: E402
from ui.copilot import render_copilot_page, render_copilot_sidebar  # noqa: E402
from ui.dashboard import render_dashboard  # noqa: E402
from ui.landing import render_landing_page  # noqa: E402
from ui.sign import render_signing_page  # noqa: E402
from ui.state import ADMIN_ITEM, NAV_ITEMS, current_user, sign_out, wizard_state  # noqa: E402
from ui.theme import inject_theme  # noqa: E402
from ui.wizard import render_wizard  # noqa: E402


@st.cache_resource
def _bootstrap() -> bool:
    init_db()
    return True


def _top_bar(session, user) -> str:
    inject_theme()
    bar = st.columns([1.7, 4.6, 1.3], vertical_alignment="center")
    with bar[0]:
        c.brand("India")
    with bar[2]:
        if user:
            st.markdown(f"<div style='text-align:right;font-size:.85rem;color:#475569;padding-top:.45rem'>"
                        f"<b>{c.esc(user.full_name)}</b><br/><span style='font-size:.78rem'>"
                        f"{'Platform admin' if user.is_admin else c.esc(user.email)}</span></div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='text-align:right;font-size:.85rem;color:#64748B;padding-top:.6rem'>Not signed in</div>",
                        unsafe_allow_html=True)

    items = list(NAV_ITEMS) + ([ADMIN_ITEM] if user and user.is_admin else [])
    active = st.session_state.get("active_tab", "Home")
    if active not in items:
        active = "Home"
    with bar[1]:
        chosen = st.segmented_control("Navigation", items, default=active, key="nav_control", label_visibility="collapsed")
    chosen = chosen or active
    if chosen != st.session_state.get("active_tab"):
        st.session_state["active_tab"] = chosen
        st.rerun()
    return chosen


def _sidebar(session, user) -> None:
    render_copilot_sidebar(session, user)
    with st.sidebar:
        st.divider()
        wiz = wizard_state()
        if wiz.get("agreement_id"):
            st.caption(f"Active draft · {wiz['agreement_id'][:8]} · step {wiz['step']} of 5")
        llm = get_llm_client()
        st.caption(f"AI: {'Claude ' + llm.model if llm.available else 'built-in rules'}")
        st.caption(f"Gateways: {'sandbox' if settings.mock_gateways else 'live'} · {settings.environment}")
        if user and st.button("Sign out", use_container_width=True, key="side_signout"):
            sign_out()
            st.rerun()


def main() -> None:
    _bootstrap()
    session = SessionLocal()
    try:
        params = st.query_params
        token = params.get("sign_token") or st.session_state.get("sign_token")
        agr_id = params.get("agr_id") or st.session_state.get("sign_agr_id")
        pty_id = params.get("party_id") or st.session_state.get("sign_party_id")

        if token and agr_id and pty_id:
            # Capability-link entry: keep it across reruns, skip the product chrome.
            st.session_state.update({"sign_token": token, "sign_agr_id": agr_id, "sign_party_id": pty_id})
            inject_theme()
            render_signing_page(session, token, agr_id, pty_id)
            return

        user = current_user(session)
        active = _top_bar(session, user)
        _sidebar(session, user)

        if active == "Home":
            render_landing_page(user)
        elif active == "Create agreement":
            render_wizard(session, user)
        elif active == "My agreements":
            render_dashboard(session, user)
        elif active == "Copilot":
            render_copilot_page(session, user)
        elif active == "Account":
            render_auth_profile(session, user)
        elif active == ADMIN_ITEM:
            render_admin(session, user)

        st.write("")
        st.markdown(
            "<div style='border-top:1px solid #E2E8F0;padding-top:.8rem;color:#94A3B8;font-size:.8rem'>"
            "GoLegal by AAS Innovation Labs · Executed under the Information Technology Act 2000 (§§ 4, 5, 10A) with a "
            "Section 65B certificate under the Indian Evidence Act 1872 · e-Stamp duty remitted through Stock Holding "
            "Corporation of India Ltd · Aadhaar numbers are never stored in full."
            "</div>", unsafe_allow_html=True)
    finally:
        session.close()


main()
