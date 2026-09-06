"""
GoLegal UI - Sign in, registration, account & security centre
"""
from __future__ import annotations

import streamlit as st

from config import settings
from domain.models import User
from security.auth import AccountLockedError, AuthError, AuthService
from services.notification import NotificationService
from services.payment_service import PaymentService
from ui import components as c
from ui.state import go, ingress_context, sign_in, sign_out


def _handle_login_result(result) -> None:
    sign_in(result.user)
    if result.suspicious:
        NotificationService().dispatch_security_alert(result.user.email, result.risk_reasons, result.event.ip_address)
        st.session_state["security_alert"] = {"reasons": result.risk_reasons, "ip": result.event.ip_address,
                                              "location": result.event.geo_location, "device": result.event.user_agent}
    st.toast(f"Signed in as {result.user.full_name}")


def render_sign_in(session, compact: bool = False) -> None:
    """Sign-in / register block. Used on the Account page and inline wherever login is required."""
    auth = AuthService(session)
    ctx = ingress_context()
    tabs = st.tabs(["Mobile OTP", "Email & password", "Create account", "Demo personas"])

    with tabs[0]:
        phone = st.text_input("Mobile number", placeholder="10-digit Indian mobile", key="li_phone")
        if not st.session_state.get("login_otp_sent"):
            if st.button("Send OTP", type="primary", key="li_send"):
                try:
                    otp = auth.request_login_otp(phone)
                    st.session_state["login_otp_sent"] = True
                    st.session_state["login_otp_phone"] = phone
                    if settings.mock_gateways:
                        st.info(f"Sandbox mode: your OTP is **{otp}** (expires in 5 minutes).")
                    st.rerun()
                except (AuthError, AccountLockedError) as exc:
                    st.error(str(exc))
        else:
            st.caption(f"OTP sent to {st.session_state.get('login_otp_phone')}" + (" · sandbox code 123456" if settings.mock_gateways else ""))
            otp = st.text_input("6-digit OTP", max_chars=6, key="li_otp")
            new_name = st.text_input("Your name (only for first-time numbers)", key="li_newname")
            b1, b2 = st.columns(2)
            if b1.button("Verify and sign in", type="primary", key="li_verify"):
                try:
                    result = auth.verify_login_otp(st.session_state["login_otp_phone"], otp, ctx, full_name_if_new=new_name or None)
                    st.session_state["login_otp_sent"] = False
                    _handle_login_result(result)
                    go("My agreements")
                except (AuthError, AccountLockedError) as exc:
                    st.error(str(exc))
            if b2.button("Use a different number", key="li_reset"):
                st.session_state["login_otp_sent"] = False
                st.rerun()

    with tabs[1]:
        email = st.text_input("Email", key="li_email")
        pwd = st.text_input("Password", type="password", key="li_pwd")
        if st.button("Sign in", type="primary", key="li_pw_btn"):
            try:
                result = auth.login_with_password(email, pwd, ctx)
                _handle_login_result(result)
                go("My agreements")
            except (AuthError, AccountLockedError) as exc:
                st.error(str(exc))
        st.caption("Demo accounts use the password GoLegal@123.")

    with tabs[2]:
        with st.form("register_form"):
            name = st.text_input("Full legal name")
            r_email = st.text_input("Email")
            r_phone = st.text_input("Mobile number")
            r_state = st.selectbox("Home state", ["KA", "DL", "MH", "TN", "TS", "HR", "UP", "GJ", "WB"], index=0)
            r_pwd = st.text_input("Password (8+ characters)", type="password")
            agree = st.checkbox("I accept the Terms of Service and Privacy Policy")
            if st.form_submit_button("Create account", type="primary"):
                if not agree:
                    st.error("Please accept the terms to continue.")
                else:
                    try:
                        user = auth.register(name, r_email, r_phone, r_pwd, state_code=r_state)
                        result = auth.login_with_password(user.email, r_pwd, ctx)
                        _handle_login_result(result)
                        go("Create agreement")
                    except AuthError as exc:
                        st.error(str(exc))

    with tabs[3]:
        st.caption("Jump straight into a persona from the PRD. Each is a real account in the database.")
        for acct in settings.demo_accounts:
            role = "Platform admin" if acct["user_type"] == "Admin" else ("Owner / landlord" if "owner" in acct["id"] else "Tenant")
            cols = st.columns([3, 1.2])
            cols[0].markdown(f"**{acct['full_name']}** · {role}<br/><span style='color:#64748B;font-size:.85rem'>{acct['email']}</span>", unsafe_allow_html=True)
            if cols[1].button("Sign in", key=f"demo_{acct['id']}", use_container_width=True):
                try:
                    result = auth.login_with_password(acct["email"], "GoLegal@123", ctx)
                    _handle_login_result(result)
                    go("Admin" if acct["user_type"] == "Admin" else "My agreements")
                except AuthError as exc:
                    st.error(str(exc))


def render_account(session, user: User) -> None:
    auth = AuthService(session)
    st.markdown("### Account & security")
    left, right = st.columns([1.1, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown(f"**{user.full_name}**  {c.status_pill('Completed', 'Admin') if user.is_admin else c.status_pill('info', 'Member')}", unsafe_allow_html=True)
            c.kv({"Email": user.email, "Mobile": user.phone, "Home state": user.state_code or "—",
                  "Member since": user.created_at.strftime("%d %b %Y") if user.created_at else "—",
                  "Last sign-in": user.last_login_at.strftime("%d %b %Y %H:%M UTC") if user.last_login_at else "—"})
            st.write("")
            with st.form("profile_form"):
                name = st.text_input("Full name", value=user.full_name)
                phone = st.text_input("Mobile", value=user.phone)
                address = st.text_area("Address", value=user.address or "", height=70)
                prefs = user.get_notification_prefs()
                p1, p2, p3 = st.columns(3)
                sms = p1.checkbox("SMS", value=prefs.get("sms", True))
                wa = p2.checkbox("WhatsApp", value=prefs.get("whatsapp", True))
                em = p3.checkbox("Email", value=prefs.get("email", True))
                if st.form_submit_button("Save profile", type="primary"):
                    import json
                    user.full_name, user.phone, user.address = name.strip() or user.full_name, phone.strip() or user.phone, address.strip() or None
                    user.notification_prefs = json.dumps({"sms": sms, "whatsapp": wa, "email": em})
                    session.commit()
                    st.success("Profile saved.")
        st.write("")
        with st.container(border=True):
            st.markdown("**Change password**")
            with st.form("pwd_form"):
                cur = st.text_input("Current password", type="password")
                new = st.text_input("New password", type="password")
                if st.form_submit_button("Update password"):
                    try:
                        auth.change_password(user, cur, new)
                        st.success("Password updated.")
                    except AuthError as exc:
                        st.error(str(exc))
        st.write("")
        if st.button("Sign out"):
            sign_out()
            go("Home")

    with right:
        with st.container(border=True):
            st.markdown("**Recent sign-ins**")
            st.caption("GoLegal compares every sign-in with your history. New devices, networks or locations trigger an email alert.")
            events = auth.recent_security_events(user, limit=8)
            if not events:
                st.caption("No sign-ins recorded yet.")
            for e in events:
                pill = c.status_pill("Rejected", "Suspicious") if e.suspicious else (c.status_pill("Signed", "Normal") if e.success else c.status_pill("Expired", "Failed"))
                reasons = "; ".join(e.get_risk_reasons())
                st.markdown(f"{pill} <span style='font-size:.85rem'>{e.created_at.strftime('%d %b %H:%M') if e.created_at else ''} · {c.esc(e.method)} · "
                            f"<span class='gl-mono'>{c.esc(e.ip_address)}</span> · {c.esc(e.geo_location or '')}</span>"
                            + (f"<br/><span style='font-size:.8rem;color:#B91C1C'>{c.esc(reasons)}</span>" if reasons else ""), unsafe_allow_html=True)
            st.write("")
            st.markdown("**Test the detector**")
            st.caption("Simulate a sign-in from an unknown device in another country and watch the alert fire.")
            if st.button("Simulate suspicious sign-in", key="sim_suspicious"):
                st.session_state["ingress_override"] = {"ip_address": "198.51.100.24", "user_agent": "Headless Chrome / Linux x86_64",
                                                        "device_fingerprint": "unknown-device-7f3a", "geo_location": "Bucharest, RO"}
                try:
                    result = auth.login_with_password(user.email, "GoLegal@123", ingress_context())
                    _handle_login_result(result)
                except AuthError:
                    st.warning("Simulation uses the demo password; change it back to GoLegal@123 or sign in again to simulate.")
                finally:
                    st.session_state.pop("ingress_override", None)
                st.rerun()
        st.write("")
        with st.container(border=True):
            st.markdown("**My invoices**")
            payments = PaymentService(session).invoices_for_user(user)
            if not payments:
                st.caption("Tax invoices appear here after your first checkout.")
            for p in payments:
                cols = st.columns([2.2, 1])
                cols[0].markdown(f"<span class='gl-mono'>{c.esc(p.invoice_number)}</span> · {c.money(p.total_amount)} · {p.created_at.strftime('%d %b %Y') if p.created_at else ''}", unsafe_allow_html=True)
                pdf = PaymentService(session).invoice_pdf(p)
                if pdf:
                    cols[1].download_button("PDF", data=pdf, file_name=f"{p.invoice_number}.pdf", mime="application/pdf", key=f"inv_{p.id}", use_container_width=True)


def render_auth_profile(session, user) -> None:
    alert = st.session_state.get("security_alert")
    if alert:
        c.notice(f"<b>Security alert sent to your email.</b> Sign-in from <span class='gl-mono'>{c.esc(alert['ip'])}</span> ({c.esc(alert['location'])}) on "
                 f"{c.esc(alert['device'])}. Reasons: {c.esc('; '.join(alert['reasons']))}. If this wasn't you, change your password now.", "danger")
        if st.button("Dismiss alert", key="dismiss_alert"):
            st.session_state.pop("security_alert", None)
            st.rerun()
    if user:
        render_account(session, user)
    else:
        st.markdown("### Sign in to GoLegal")
        st.caption("Registration is required to initiate an agreement. Invited signers only need their secure link.")
        render_sign_in(session)
