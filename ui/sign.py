"""
GoLegal UI - Counterparty signing page (reached only through a capability link)

This is the page a tenant, co-owner or witness lands on when they tap the
WhatsApp/SMS link. No account is required: the CBAC token is the credential.
Every action is authorised against the token, never against a raw agreement id.
"""
from __future__ import annotations

import streamlit as st

from ai.clause_intelligence import ClauseIntelligence
from config import settings
from domain.models import Agreement, Party
from security.cbac import (
    ACTION_DOWNLOAD_FINAL, ACTION_EXECUTE_ESIGN, ACTION_VIEW_DRAFT, CBACService, TokenExpiredError,
    UnauthorizedCapabilityError,
)
from services.agreement_service import AgreementService
from services.esign_service import AadhaarVerificationError, ESignService, RateLimitLockoutError
from services.rule_engine import get_default_clauses
from services.workflow_service import WorkflowService
from ui import components as c
from ui.state import ingress_context


def _exit_link() -> None:
    if st.button("Leave this page"):
        st.query_params.clear()
        st.session_state.pop("sign_token", None)
        st.rerun()


def render_signing_page(session, token: str, agreement_id: str, party_id: str) -> None:
    cbac = CBACService()
    agreements = AgreementService(session)
    workflow = WorkflowService(session)
    esign = ESignService(session)

    c.brand("Secure signing link")
    st.write("")

    agreement: Agreement | None = agreements.get(agreement_id)
    if not agreement:
        c.notice("This signing link points to an agreement that no longer exists.", "danger")
        _exit_link()
        return

    # Authorise: view first, then decide what else this capability allows.
    try:
        payload = cbac.verify_token(token, agreement_id, ACTION_VIEW_DRAFT)
    except TokenExpiredError:
        c.notice("<b>This link has expired.</b> Signing links are valid for "
                 f"{settings.signing_link_ttl_days} days. Ask the initiator to re-send it.", "warn")
        _exit_link()
        return
    except UnauthorizedCapabilityError as exc:
        # A witness whose capability was downgraded after signing still gets a friendly page.
        try:
            cbac.verify_token(token, agreement_id, "COMPLETED_ACK")
            c.notice("<b>Thank you — your attestation is recorded.</b> As a witness you do not receive a copy of the "
                     "executed deed. This is GoLegal's witness privacy policy.", "ok")
            _exit_link()
            return
        except Exception:
            pass
        c.notice(f"<b>This link cannot be used.</b> {c.esc(str(exc))}", "danger")
        _exit_link()
        return

    party: Party | None = next((p for p in agreement.parties if p.id == party_id), None)
    if not party or payload.get("pty_id") != party_id:
        c.notice("This link does not match a signatory on this agreement.", "danger")
        _exit_link()
        return

    can_sign = ACTION_EXECUTE_ESIGN in payload.get("actions", []) and party.signing_status != "Signed"
    can_download = ACTION_DOWNLOAD_FINAL in payload.get("actions", []) and party.party_type != "Witness"
    progress = workflow.get_signing_progress(agreement.id)

    st.markdown(f"### {c.esc(agreement.display_title)}")
    st.markdown(f"You are signing as **{c.esc(party.full_name)}** ({c.esc(party.party_type)}). "
                f"{c.status_pill(agreement.status)}", unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([1.25, 1], gap="large")

    with left:
        st.markdown("**The agreement**")
        parties_status = [{"name": p.full_name, "type": p.party_type, "status": p.signing_status,
                           "hash": next((s.signature_hash for s in agreement.signatures if s.party_id == p.id), "")}
                          for p in agreement.parties]
        c.deed_preview(agreements.load_payload(agreement),
                       get_default_clauses(agreement.get_clause_toggles(), agreement.agreement_type),
                       estamp={"certificate_number": agreement.estamp.certificate_number,
                               "stamp_amount": agreement.estamp.stamp_amount} if agreement.estamp else None,
                       parties_status=parties_status, sealed=agreement.status == "Completed")

    with right:
        with st.container(border=True):
            c.progress_seal(progress["signed_count"], progress["total_parties"])
            st.write("")
            for p in agreement.parties:
                st.markdown(c.party_row(p.full_name, p.party_type, None, p.signing_status), unsafe_allow_html=True)
        st.write("")

        with st.container(border=True):
            st.markdown("**Read it in plain words**")
            lang = st.selectbox("Language", ["en", "hi", "kn", "ta", "te"], key="sign_lang",
                                format_func=lambda x: {"en": "English", "hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "te": "Telugu"}[x])
            if st.button("Explain this agreement", use_container_width=True, key="sign_explain"):
                st.session_state["sign_summary"] = ClauseIntelligence().plain_language_summary(
                    agreements.load_payload(agreement), language=lang)
            summary = st.session_state.get("sign_summary")
            if summary:
                st.write(summary.get("summary", ""))
                if summary.get("note"):
                    st.caption(summary["note"])

        st.write("")
        if party.signing_status == "Signed":
            sig = next((s for s in agreement.signatures if s.party_id == party.id), None)
            c.notice("<b>You have signed.</b> " + (f"Transaction {c.esc(sig.transaction_ref)} at "
                     f"{sig.signed_at.strftime('%d %b %Y %H:%M UTC')}." if sig else ""), "ok")
        elif can_sign and agreement.status == "Pending_Signatures":
            with st.container(border=True):
                st.markdown("##### Sign with Aadhaar")
                st.markdown("""<div class="gl-notice info"><b>UIDAI consent.</b> I voluntarily authorise GoLegal and its licensed
                eSign Service Provider to authenticate my identity with UIDAI using Aadhaar OTP, solely to affix my electronic
                signature to this deed under Sections 4 and 5 of the Information Technology Act, 2000. My Aadhaar number is not stored.
                <br/><span style="font-size:.85rem">मैं इस अनुबंध पर हस्ताक्षर हेतु आधार OTP द्वारा पहचान सत्यापन की स्वेच्छा से सहमति देता/देती हूँ।</span></div>""",
                            unsafe_allow_html=True)
                consent = st.checkbox("I agree to the UIDAI authentication terms", key="sign_consent")
                subject = party.aadhaar_masked or party.id
                if not st.session_state.get("sign_otp_sent"):
                    if st.button("Send OTP to my Aadhaar-linked mobile", type="primary", use_container_width=True, key="sign_send"):
                        try:
                            otp = esign.request_otp(subject)
                            st.session_state["sign_otp_sent"] = True
                            if settings.mock_gateways:
                                st.info(f"Sandbox: your OTP is **{otp}**")
                            st.rerun()
                        except RateLimitLockoutError as exc:
                            st.error(str(exc))
                else:
                    st.caption(f"Attempts remaining: {esign.remaining_attempts(subject)}")
                    otp = st.text_input("6-digit OTP", max_chars=6, key="sign_otp")
                    b1, b2 = st.columns(2)
                    if b1.button("Verify and sign", type="primary", use_container_width=True, key="sign_verify"):
                        try:
                            ctx = ingress_context()
                            esign.verify_otp_and_sign(agreement.id, party.id, subject, otp, consent,
                                                      client_ip=ctx.ip_address, user_agent=ctx.user_agent)
                            st.session_state.pop("sign_otp_sent", None)
                            if workflow.check_and_complete_signing(agreement.id):
                                st.balloons()
                            st.rerun()
                        except (AadhaarVerificationError, RateLimitLockoutError) as exc:
                            st.error(str(exc))
                    if b2.button("Cancel", use_container_width=True, key="sign_cancel"):
                        st.session_state.pop("sign_otp_sent", None)
                        st.rerun()
        elif agreement.status == "Paid":
            c.notice("The initiator has not opened this agreement for signatures yet.", "info")

        if agreement.status == "Completed":
            st.write("")
            if can_download:
                pdf = workflow.final_pdf(agreement)
                if pdf:
                    st.download_button("Download the sealed agreement", data=pdf, file_name=f"GoLegal_{agreement.id[:8]}.pdf",
                                       mime="application/pdf", type="primary", use_container_width=True, key="sign_dl")
                    st.caption(f"SHA-256 {agreement.final_pdf_sha256}")
            else:
                c.notice("The deed is sealed. As a witness you do not receive a copy — GoLegal's witness privacy policy.", "info")

    st.write("")
    st.caption("This link is a single-purpose capability token. It works only for this agreement and only for your role. "
               "Do not forward it.")
    _exit_link()
