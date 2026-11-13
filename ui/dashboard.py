"""
GoLegal UI - My agreements workspace
"""
from __future__ import annotations

from typing import List

import streamlit as st

from domain.models import Agreement, Feedback, User, utc_now
from services.agreement_service import AgreementService
from services.payment_service import PaymentService
from services.rule_engine import AGREEMENT_TYPE_LABELS
from services.workflow_service import WorkflowService
from ui import components as c
from ui.state import go, reset_wizard

SORTS = {"Newest first": lambda a: (a.created_at or utc_now()), "Counterparty name": lambda a: (a.parties[0].full_name if a.parties else ""),
         "Agreement type": lambda a: a.agreement_type, "Status": lambda a: a.status}


def _agreement_card(session, agreement: Agreement, user: User, workflow: WorkflowService, agreements: AgreementService) -> None:
    prop = agreement.get_property_details()
    terms = agreement.get_commercial_terms()
    signed, total = agreement.signed_count(), len(agreement.parties)
    counterparties = ", ".join(p.full_name for p in agreement.parties if p.party_type != "Witness")

    with st.container(border=True):
        head = st.columns([3, 1.2, 1.4])
        with head[0]:
            st.markdown(f"**{c.esc(agreement.display_title)}** {c.status_pill(agreement.status)}", unsafe_allow_html=True)
            st.markdown(f"<span style='color:#64748B;font-size:.85rem'>{c.esc(AGREEMENT_TYPE_LABELS.get(agreement.agreement_type, agreement.agreement_type))} · "
                        f"{c.esc(agreement.state_code)} · {c.money(terms.get('monthly_rent'))}/month · {c.esc(counterparties)}</span>", unsafe_allow_html=True)
            if prop.get("address"):
                st.markdown(f"<span style='color:#94A3B8;font-size:.8rem'>{c.esc(prop.get('premises_name', ''))} {c.esc(prop.get('address'))} {c.esc(prop.get('city', ''))}</span>", unsafe_allow_html=True)
        with head[1]:
            st.markdown(f"<div style='text-align:right'><span class='gl-mono'>{signed}/{total} signed</span><br/>"
                        f"<span style='font-size:.78rem;color:#64748B'>{agreement.created_at.strftime('%d %b %Y') if agreement.created_at else ''}</span></div>",
                        unsafe_allow_html=True)
        with head[2]:
            if agreement.status == "Draft" and agreement.initiator_id == user.id:
                if st.button("Continue", key=f"cont_{agreement.id}", type="primary", use_container_width=True):
                    reset_wizard(agreements.load_payload(agreement), agreement.id, step=2)
                    go("Create agreement")
            elif agreement.status in ("Paid", "Pending_Signatures"):
                if st.button("Open signing", key=f"open_{agreement.id}", type="primary", use_container_width=True):
                    reset_wizard(agreements.load_payload(agreement), agreement.id, step=5)
                    go("Create agreement")
            elif agreement.status == "Completed":
                pdf = workflow.final_pdf(agreement)
                is_witness_only = all(p.party_type == "Witness" for p in agreement.parties
                                      if (p.email or "").lower() == (user.email or "").lower())
                if pdf and not is_witness_only:
                    st.download_button("Download deed", data=pdf, file_name=f"GoLegal_OS_{agreement.id[:8]}.pdf", mime="application/pdf",
                                       key=f"dl_{agreement.id}", use_container_width=True, type="primary")

        with st.expander("Details, parties and actions"):
            d1, d2 = st.columns([1.2, 1])
            with d1:
                st.markdown("**Signatories**")
                for p in agreement.parties:
                    sig = next((s for s in agreement.signatures if s.party_id == p.id), None)
                    extra = f"<span class='gl-mono' style='font-size:.7rem'>{c.esc((sig.signature_hash or '')[:16])}…</span>" if sig else ""
                    st.markdown(c.party_row(p.full_name, p.party_type, p.aadhaar_masked, p.signing_status, extra), unsafe_allow_html=True)
                if agreement.status == "Pending_Signatures" and agreement.initiator_id == user.id:
                    if st.button("Re-send links to pending parties", key=f"rs_{agreement.id}"):
                        sent = workflow.resend_invitations(agreement, triggered_by=user.id)
                        st.success(f"Reminded {len(sent)} party(ies)." if sent else "Everyone has signed already.")
            with d2:
                pairs = {"Agreement id": agreement.id, "Status": agreement.status.replace("_", " "),
                         "Term": f"{terms.get('lease_months', 11)} months", "Deposit": c.money(terms.get("security_deposit")),
                         "Storage consent": "Yes" if agreement.cloud_storage_consent else "No — purged after retention"}
                if agreement.estamp:
                    pairs["e-Stamp"] = agreement.estamp.certificate_number
                if agreement.payment:
                    pairs["Invoice"] = agreement.payment.invoice_number or "—"
                if agreement.expires_at and agreement.status == "Pending_Signatures":
                    pairs["Signing window ends"] = agreement.expires_at.strftime("%d %b %Y")
                if agreement.final_pdf_sha256:
                    pairs["Sealed digest"] = agreement.final_pdf_sha256
                c.kv(pairs)
                st.write("")
                if agreement.initiator_id == user.id:
                    a1, a2 = st.columns(2)
                    with a1:
                        new_title = st.text_input("Rename", value=agreement.display_title, key=f"rn_{agreement.id}", label_visibility="collapsed")
                        if st.button("Rename", key=f"rnb_{agreement.id}", use_container_width=True):
                            agreements.rename(agreement, user, new_title)
                            st.rerun()
                    with a2:
                        if st.button("Archive from my workspace", key=f"ar_{agreement.id}", use_container_width=True):
                            agreements.archive(agreement, user)
                            st.toast("Archived. Counterparties keep their access.")
                            st.rerun()
                if agreement.status == "Completed":
                    share = f"https://wa.me/?text=Our%20executed%20agreement%20is%20ready:%20{agreement.id[:8]}"
                    st.markdown(f"[Share on WhatsApp]({share})")


def _nps_block(session, user: User) -> None:
    st.markdown("**How likely are you to recommend GoLegal OS?**")
    score = st.slider("0 = not at all, 10 = extremely likely", 0, 10, 9, key="nps_score")
    category, comment = None, ""
    if score <= 8:
        st.caption("Sorry we fell short. What should we fix first?")
        category = st.selectbox("Area", ["e-Stamp processing speed", "Aadhaar OTP delivery", "Clause customisation",
                                         "Pricing", "Mobile readability", "Something else"], key="nps_cat")
        comment = st.text_area("Tell us more", key="nps_comment", height=80)
    elif score == 9:
        st.caption("Thank you. What would make it a 10?")
        comment = st.text_area("Optional", key="nps_comment9", height=68)
    else:
        st.caption("That means a lot. Would you refer a friend or leave a Google review?")
    if st.button("Submit feedback", type="primary", key="nps_submit"):
        session.add(Feedback(user_id=user.id if user else None, score=score, category=category, comment=comment or None,
                             sentiment="Detractor" if score <= 8 else ("Happy" if score == 9 else "Delighted")))
        session.commit()
        st.success("Logged. Our product team reads every response.")


def render_dashboard(session, user) -> None:
    if not user:
        st.markdown("### My agreements")
        c.notice("Sign in to see your drafts, pending signatures and executed deeds.", "info")
        if st.button("Go to sign in", type="primary"):
            go("Account")
        return

    agreements = AgreementService(session)
    workflow = WorkflowService(session)
    rows: List[Agreement] = agreements.list_for_user(user)
    counts = agreements.status_counts(user)

    head = st.columns([3, 1.3])
    head[0].markdown("### My agreements")
    with head[1]:
        if st.button("New agreement", type="primary", use_container_width=True):
            reset_wizard()
            go("Create agreement")

    m = st.columns(4)
    with m[0]:
        c.stat("Drafts", str(counts.get("Draft", 0)), "not yet paid")
    with m[1]:
        c.stat("Awaiting signatures", str(counts.get("Paid", 0) + counts.get("Pending_Signatures", 0)), "links dispatched")
    with m[2]:
        c.stat("Executed", str(counts.get("Completed", 0)), "sealed and certified", tone="ok")
    with m[3]:
        invoices = PaymentService(session).invoices_for_user(user)
        c.stat("Paid to date", c.money(sum(p.total_amount for p in invoices)), f"{len(invoices)} invoice(s)")

    st.write("")
    tabs = st.tabs([f"Awaiting signatures ({counts.get('Paid', 0) + counts.get('Pending_Signatures', 0)})",
                    f"Executed ({counts.get('Completed', 0)})", f"Drafts ({counts.get('Draft', 0)})",
                    "Invoices", "Archived", "Rate GoLegal OS"])

    with tabs[0]:
        pending = [a for a in rows if a.status in ("Paid", "Pending_Signatures")]
        if not pending:
            c.empty_state("✍️", "Nothing awaiting signatures", "Once you pay and dispatch links, live signing progress appears here.")
        for a in pending:
            _agreement_card(session, a, user, workflow, agreements)

    with tabs[1]:
        done = [a for a in rows if a.status == "Completed"]
        if not done:
            c.empty_state("📜", "No executed agreements yet", "Sealed deeds carry the e-Stamp certificate and a Section 65B evidentiary page.")
        for a in done:
            _agreement_card(session, a, user, workflow, agreements)

    with tabs[2]:
        drafts = [a for a in rows if a.status in ("Draft", "Cancelled", "Expired")]
        if not drafts:
            c.empty_state("📝", "No drafts", "Start one from the wizard or ask Copilot to draft it from a sentence.")
        sort_key = st.selectbox("Sort by", list(SORTS), key="draft_sort") if drafts else None
        for a in sorted(drafts, key=SORTS[sort_key], reverse=(sort_key == "Newest first")) if drafts else []:
            _agreement_card(session, a, user, workflow, agreements)

    with tabs[3]:
        payments = PaymentService(session)
        invoices = payments.invoices_for_user(user)
        if not invoices:
            c.empty_state("🧾", "No invoices yet", "GST invoices are issued the moment a payment is captured.")
        for p in invoices:
            cols = st.columns([1.4, 1, 1, 1, 1])
            cols[0].markdown(f"<span class='gl-mono'>{c.esc(p.invoice_number)}</span>", unsafe_allow_html=True)
            cols[1].markdown(c.money(p.stamp_duty_amount) + "<br/><span style='font-size:.75rem;color:#64748B'>duty</span>", unsafe_allow_html=True)
            cols[2].markdown(c.money(p.platform_fee + p.gst_amount) + "<br/><span style='font-size:.75rem;color:#64748B'>fee + GST</span>", unsafe_allow_html=True)
            cols[3].markdown(f"**{c.money(p.total_amount)}**<br/><span style='font-size:.75rem;color:#64748B'>{p.created_at.strftime('%d %b %Y') if p.created_at else ''}</span>", unsafe_allow_html=True)
            pdf = payments.invoice_pdf(p)
            if pdf:
                cols[4].download_button("PDF", data=pdf, file_name=f"{p.invoice_number}.pdf", mime="application/pdf",
                                        key=f"dinv_{p.id}", use_container_width=True)

    with tabs[4]:
        archived = [a for a in agreements.list_for_user(user, include_archived=True) if a.is_archived]
        if not archived:
            c.empty_state("🗂️", "Nothing archived", "Archiving removes an agreement from your workspace but never from your counterparties'.")
        for a in archived:
            cols = st.columns([3, 1])
            cols[0].markdown(f"**{c.esc(a.display_title)}** {c.status_pill(a.status)}", unsafe_allow_html=True)
            if cols[1].button("Restore", key=f"rest_{a.id}", use_container_width=True):
                agreements.restore(a, user)
                st.rerun()

    with tabs[5]:
        _nps_block(session, user)
