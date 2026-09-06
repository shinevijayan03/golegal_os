"""
GoLegal UI - 5-step agreement wizard

Step 1 Jurisdiction & type      Step 2 Parties, property, terms
Step 3 Clauses, risk & preview  Step 4 Checkout & e-Stamp
Step 5 Aadhaar eSign & dispatch
"""
from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from ai.clause_intelligence import ClauseIntelligence
from ai.contract_ingest import extract_terms, extract_text_from_pdf, merge_into_payload
from ai.rent_benchmark import benchmark
from config import settings
from domain.models import Party, User
from services.agreement_service import AgreementAccessError, AgreementService, demo_payload
from services.esign_service import AadhaarVerificationError, ESignService, RateLimitLockoutError
from services.payment_service import PaymentService
from services.rule_engine import (
    AGREEMENT_TYPE_LABELS, OPTIONAL_TOGGLES, STATE_STAMP_RULES, calculate_stamp_duty, get_default_clauses,
)
from services.stamping_service import InsufficientStampingBalanceError, StampingService
from services.validation import validate_wizard_payload
from services.workflow_service import WorkflowService
from ui import components as c
from ui.state import go, reset_wizard, wizard_state

STEPS = ["Jurisdiction", "Parties & terms", "Clauses & preview", "Checkout & e-Stamp", "Sign & seal"]
PARTY_TEMPLATE = {"name": "", "phone": "", "email": "", "pan": "", "aadhaar": "", "address": ""}


# ----------------------------------------------------------------------- helpers
def _goto(step: int) -> None:
    wizard_state()["step"] = step
    st.rerun()


def _party_form(group_key: str, label: str, wiz_payload: Dict[str, Any], require_pan: bool = False,
                max_count: int = 4, aadhaar: bool = True) -> None:
    people: List[Dict[str, Any]] = wiz_payload.setdefault(group_key, [])
    if not people and group_key != "witnesses":
        people.append(dict(PARTY_TEMPLATE))

    for idx, person in enumerate(people):
        for k, v in PARTY_TEMPLATE.items():
            person.setdefault(k, v)
        with st.container(border=True):
            head = st.columns([4, 1])
            head[0].markdown(f"**{label} {idx + 1}**" if len(people) > 1 else f"**{label}**")
            if len(people) > (0 if group_key == "witnesses" else 1):
                if head[1].button("Remove", key=f"rm_{group_key}_{idx}", use_container_width=True):
                    people.pop(idx)
                    st.rerun()
            r1 = st.columns(2)
            person["name"] = r1[0].text_input("Full legal name", value=person["name"], key=f"{group_key}_{idx}_name")
            person["phone"] = r1[1].text_input("Mobile", value=person["phone"], key=f"{group_key}_{idx}_phone",
                                               help="Signing link and Aadhaar OTP go to this number")
            r2 = st.columns(2)
            person["email"] = r2[0].text_input("Email", value=person["email"], key=f"{group_key}_{idx}_email")
            if aadhaar:
                raw = r2[1].text_input("Aadhaar (stored masked)", value=person["aadhaar"], key=f"{group_key}_{idx}_aadhaar",
                                       type="password", help="Used once for OTP. GoLegal stores only XXXXXXXX1234.")
                person["aadhaar"] = raw
            if group_key != "witnesses":
                r3 = st.columns([1, 2])
                person["pan"] = r3[0].text_input("PAN" + (" (required)" if require_pan else ""), value=person["pan"],
                                                 key=f"{group_key}_{idx}_pan", placeholder="ABCDE1234F")
                person["address"] = r3[1].text_input("Permanent address", value=person["address"], key=f"{group_key}_{idx}_addr")

    if len(people) < max_count:
        add_label = {"owners": "Add co-owner", "tenants": "Add co-tenant", "witnesses": "Add witness"}[group_key]
        if st.button(f"＋ {add_label}", key=f"add_{group_key}"):
            people.append(dict(PARTY_TEMPLATE))
            st.rerun()


def _ingest_panel(wiz: Dict[str, Any]) -> None:
    """Digitise an existing contract or a plain-English brief into the draft."""
    with st.expander("Start from an existing contract or a sentence", expanded=False):
        st.caption("Paste an old agreement, upload a PDF, or just describe the tenancy. GoLegal extracts the terms and fills the form.")
        text = st.text_area("Paste text or describe the tenancy", height=110, key="ingest_text",
                            placeholder="2BHK at Sunrise Apartments 402, Bellandur, Bangalore 560103. Rent 28,000, deposit 1.2 lakh, "
                                        "11 months, lock-in 6, notice 30 days. Owner Ramakiran Reddy 9876543210, tenant Mayank Tripathi 9876543211.")
        upload = st.file_uploader("or upload a PDF / text contract", type=["pdf", "txt"], key="ingest_file")
        if st.button("Extract and fill", type="primary", key="ingest_run"):
            source = text or ""
            if upload is not None:
                data = upload.getvalue()
                source = extract_text_from_pdf(data) if upload.name.lower().endswith(".pdf") else data.decode("utf-8", "ignore")
            if not source.strip():
                st.warning("Add some text or a file first.")
            else:
                with st.spinner("Reading the contract…"):
                    result = extract_terms(source)
                if not result.fields_found:
                    st.warning(result.notes[0] if result.notes else "Nothing recognisable found.")
                else:
                    wiz["payload"] = merge_into_payload(wiz["payload"], result.payload_updates)
                    wiz["risk"] = wiz["summary"] = None
                    st.success(f"Filled {len(result.fields_found)} field group(s) via {result.model}: {', '.join(result.fields_found)}.")
                    st.rerun()


# ----------------------------------------------------------------------- steps
def _step_jurisdiction(wiz: Dict[str, Any]) -> None:
    p = wiz["payload"]
    st.markdown("#### What are we executing, and where?")
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        with st.container(border=True):
            types = list(AGREEMENT_TYPE_LABELS)
            p["agreement_type"] = st.selectbox("Agreement type", types, index=types.index(p.get("agreement_type", "Rental_Residential")),
                                               format_func=lambda x: AGREEMENT_TYPE_LABELS[x])
            state_names = {k: v["name"] for k, v in STATE_STAMP_RULES.items()}
            codes = list(state_names)
            p["state_code"] = st.selectbox("Property state (sets statutory stamp duty)", codes,
                                           index=codes.index(p.get("state_code", "KA")) if p.get("state_code") in codes else 0,
                                           format_func=lambda x: f"{state_names[x]} ({x})")
            p["title"] = st.text_input("Give it a name (optional)", value=p.get("title", ""), placeholder="Sunrise Apartments 402 — rental")
            if p["agreement_type"] == "Rental_Residential":
                c.notice("11-month residential tenancies need e-Stamp duty only. A term of 12 months or more must also be "
                         "registered with the Sub-Registrar, which GoLegal does not do.", "info")
        st.write("")
        _ingest_panel(wiz)
    with right:
        rule = STATE_STAMP_RULES.get(p["state_code"], {})
        c.stat("Statutory duty", c.money(rule.get("flat_duty", 100)) + (" min" if rule.get("pct_rate") else " flat"),
               rule.get("article", ""))
        st.write("")
        c.card("What you get", "Government e-Stamp certificate as page one, lawyer-vetted clauses, Aadhaar eSign for every party, "
                               "a sealed PDF and a Section 65B evidentiary certificate.", accent=True)
        st.write("")
        if st.button("Load the demo tenancy", use_container_width=True):
            wiz["payload"] = demo_payload()
            wiz["risk"] = wiz["summary"] = None
            st.rerun()

    nav = st.columns([3, 1])
    if nav[1].button("Next: parties →", type="primary", use_container_width=True):
        _goto(2)


def _step_parties(wiz: Dict[str, Any]) -> None:
    p = wiz["payload"]
    st.markdown("#### Who is involved, and on what terms?")
    _ingest_panel(wiz)
    tabs = st.tabs(["First party (owner)", "Second party (tenant)", "Property & money", "Witnesses"])
    with tabs[0]:
        _party_form("owners", "Owner / lessor", p, require_pan=True)
    with tabs[1]:
        _party_form("tenants", "Tenant / lessee", p)
    with tabs[2]:
        prop, comm = p.setdefault("property", {}), p.setdefault("commercials", {})
        with st.container(border=True):
            st.markdown("**Premises**")
            r1 = st.columns(2)
            prop["premises_name"] = r1[0].text_input("Building / flat", value=prop.get("premises_name", ""))
            prop["property_type"] = r1[1].selectbox("Type", ["Apartment", "1BHK Apartment", "2BHK Apartment", "3BHK Apartment", "Independent house", "Villa", "Floor", "Commercial unit"],
                                                    index=0 if prop.get("property_type", "Apartment") not in ["Apartment", "1BHK Apartment", "2BHK Apartment", "3BHK Apartment", "Independent house", "Villa", "Floor", "Commercial unit"]
                                                    else ["Apartment", "1BHK Apartment", "2BHK Apartment", "3BHK Apartment", "Independent house", "Villa", "Floor", "Commercial unit"].index(prop.get("property_type", "Apartment")))
            prop["address"] = st.text_input("Street address", value=prop.get("address", ""))
            r2 = st.columns(2)
            prop["city"] = r2[0].text_input("City", value=prop.get("city", ""))
            prop["pincode"] = r2[1].text_input("PIN code", value=str(prop.get("pincode", "")), max_chars=6)
            prop["inclusions"] = st.text_input("Fixtures, parking, keys handed over", value=prop.get("inclusions", ""),
                                               placeholder="2 fans, 3 lights, geyser, 1 covered parking, 2 sets of keys")
        st.write("")
        with st.container(border=True):
            st.markdown("**Commercial terms**")
            m1 = st.columns(3)
            comm["monthly_rent"] = m1[0].number_input("Monthly rent (₹)", min_value=500, max_value=10_000_000,
                                                      value=int(comm.get("monthly_rent", 25000) or 25000), step=1000)
            comm["security_deposit"] = m1[1].number_input("Security deposit (₹)", min_value=0, max_value=50_000_000,
                                                          value=int(comm.get("security_deposit", 100000) or 0), step=5000)
            comm["rent_due_day"] = m1[2].number_input("Rent due day", min_value=1, max_value=28, value=int(comm.get("rent_due_day", 5) or 5))
            m2 = st.columns(4)
            comm["lease_months"] = m2[0].number_input("Term (months)", min_value=1, max_value=60, value=int(comm.get("lease_months", 11) or 11))
            comm["lock_in_months"] = m2[1].number_input("Lock-in (months)", min_value=0, max_value=60, value=int(comm.get("lock_in_months", 6) or 0))
            comm["notice_days"] = m2[2].number_input("Notice (days)", min_value=0, max_value=180, value=int(comm.get("notice_days", 30) or 30))
            comm["escalation_pct"] = m2[3].number_input("Escalation (%)", min_value=0.0, max_value=50.0,
                                                        value=float(comm.get("escalation_pct", 5) or 0), step=0.5)
            comm["lease_start"] = st.text_input("Start date (YYYY-MM-DD)", value=comm.get("lease_start", ""), placeholder="2026-10-01")

            rent, dep = comm["monthly_rent"], comm["security_deposit"]
            if prop.get("city"):
                bhk = "3BHK" if "3" in str(prop.get("property_type", "")) else "1BHK" if "1" in str(prop.get("property_type", "")) else "2BHK"
                b = benchmark(prop["city"], prop.get("address", ""), bhk, rent, dep)
                if b.get("supported"):
                    tone = {"above_market": "warn", "below_market": "info", "fair": "ok"}.get(b.get("rent_position"), "info")
                    c.notice("<b>Market check.</b> " + " ".join(c.esc(i) for i in b.get("insights", [])), tone)
    with tabs[3]:
        st.caption("Witnesses attest the execution. They sign but never receive a copy of the executed deed.")
        _party_form("witnesses", "Witness", p, max_count=2)
        if not p.get("witnesses"):
            c.notice("No witnesses added. Rental deeds are customarily attested by two witnesses; GoLegal also offers an "
                     "institutional witness service.", "warn")

    st.write("")
    p["cloud_storage_consent"] = st.checkbox(
        "Store my executed agreement encrypted (AES-256) so I can download it any time.",
        value=p.get("cloud_storage_consent", True),
        help=f"Without consent, unexecuted drafts are permanently purged after {settings.draft_pruning_days} days.")

    nav = st.columns([1, 3, 1.4])
    if nav[0].button("← Back", use_container_width=True):
        _goto(1)
    if nav[2].button("Next: clauses →", type="primary", use_container_width=True):
        errors = validate_wizard_payload(p)
        if errors:
            for e in errors[:8]:
                st.error(e)
        else:
            wiz["risk"] = wiz["summary"] = None
            _goto(3)


def _step_clauses(wiz: Dict[str, Any]) -> None:
    p = wiz["payload"]
    st.markdown("#### Tune the covenants. The deed updates as you type.")
    left, right = st.columns([1, 1.25], gap="large")

    with left:
        with st.container(border=True):
            st.markdown("**Optional covenants**")
            toggles = p.setdefault("clause_toggles", {})
            for key, spec in OPTIONAL_TOGGLES.items():
                toggles[key] = st.toggle(spec["label"], value=toggles.get(key, spec["default"]), key=f"tg_{key}")
        st.write("")
        with st.container(border=True):
            st.markdown("**Your own terms**")
            p["custom_clauses"] = st.text_area("Additional covenants", value=p.get("custom_clauses", ""), height=120,
                                               placeholder="Quiet hours after 11 PM. Society maintenance paid by the owner.",
                                               label_visibility="collapsed")
            b1, b2 = st.columns(2)
            if b1.button("Check for risk", use_container_width=True):
                wiz["risk"] = ClauseIntelligence().assess_risk(
                    p.get("custom_clauses", ""), p.get("commercials", {}), toggles, p.get("agreement_type"), p.get("state_code")).to_dict()
                if wiz["risk"].get("redacted_text") is not None:
                    p["custom_clauses"] = wiz["risk"]["redacted_text"]
                st.rerun()
            if b2.button("Explain in simple words", use_container_width=True):
                wiz["summary"] = ClauseIntelligence().plain_language_summary(p)
                st.rerun()
            lang = st.selectbox("Summary language", ["en", "hi", "kn", "ta", "te"], format_func=lambda x: {"en": "English", "hi": "Hindi", "kn": "Kannada", "ta": "Tamil", "te": "Telugu"}[x], key="sum_lang")
            if lang != "en" and st.button(f"Summarise in {lang.upper()}", use_container_width=True):
                wiz["summary"] = ClauseIntelligence().plain_language_summary(p, language=lang)
                st.rerun()

        if wiz.get("risk"):
            st.write("")
            c.risk_panel(wiz["risk"])
        if wiz.get("summary"):
            st.write("")
            with st.container(border=True):
                st.markdown("**In plain words**")
                st.write(wiz["summary"].get("summary", ""))
                if wiz["summary"].get("note"):
                    st.caption(wiz["summary"]["note"])

        st.write("")
        with st.expander("Statutory clauses (cannot be edited)"):
            for cl in get_default_clauses(p.get("clause_toggles"), p.get("agreement_type")):
                if not cl["derogable"]:
                    st.markdown(f"🔒 **{cl['title']}** — <span style='color:#64748B;font-size:.85rem'>{c.esc(cl['text'])}</span>", unsafe_allow_html=True)

    with right:
        quote = calculate_stamp_duty(p["state_code"], p["commercials"]["monthly_rent"], p["commercials"]["security_deposit"],
                                     int(p["commercials"].get("lease_months", 11) or 11))
        c.deed_preview(p, get_default_clauses(p.get("clause_toggles"), p.get("agreement_type")), quote=quote)

    nav = st.columns([1, 3, 1.4])
    if nav[0].button("← Back", use_container_width=True):
        _goto(2)
    if nav[2].button("Next: checkout →", type="primary", use_container_width=True):
        _goto(4)


def _step_checkout(wiz: Dict[str, Any], session, user: User) -> None:
    p = wiz["payload"]
    st.markdown("#### Pay once. Stamp duty and platform fee, itemised.")
    if not user:
        c.notice("Sign in to pay and procure the e-Stamp certificate. Your draft is kept in this session.", "warn")
        if st.button("Go to sign in", type="primary"):
            go("Account")
        return

    agreements = AgreementService(session)
    payments = PaymentService(session)
    stamping = StampingService(session)
    workflow = WorkflowService(session)

    errors = validate_wizard_payload(p)
    if errors:
        c.notice("<b>Complete these before paying:</b><br/>" + "<br/>".join("• " + c.esc(e) for e in errors[:8]), "danger")
        if st.button("← Back to parties"):
            _goto(2)
        return

    # Persist the draft so payment is always attached to a real agreement row.
    # Once it leaves Draft the row is authoritative and must not be re-written.
    existing = agreements.get(wiz["agreement_id"]) if wiz.get("agreement_id") else None
    try:
        if existing and existing.status != "Draft":
            agreement = agreements.get_accessible(existing.id, user)
        else:
            agreement = agreements.save_draft(user, p, agreement_id=wiz.get("agreement_id"))
        wiz["agreement_id"] = agreement.id
    except AgreementAccessError as exc:
        st.error(str(exc))
        return

    quote = payments.quote(agreement)
    wiz["quote"] = quote
    paid = agreement.payment is not None and agreement.payment.status == "Success"
    estamp = agreement.estamp

    left, right = st.columns([1.25, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("**Tax invoice preview**")
            st.markdown(f"""
| Item | Amount |
| :--- | ---: |
| State stamp duty — {c.esc(quote['state_name'])} ({c.esc(quote['article'])}) | {c.money(quote['stamp_duty_amount'])} |
| GoLegal platform fee | {c.money(quote['platform_fee'])} |
| GST @ 18% on platform fee | {c.money(quote['gst_amount'])} |
| **Total payable** | **{c.money(quote['total_payable'])}** |
""")
            st.caption("Stamp duty is collected as pure agent and remitted to the state through StockHolding; GST applies to the platform fee only.")
        st.write("")
        if not paid:
            with st.container(border=True):
                st.markdown("**Payment method**")
                mode = st.radio("Method", ["UPI", "Card", "NetBanking"], horizontal=True, label_visibility="collapsed", key="pay_mode")
                if mode == "UPI":
                    st.text_input("UPI ID", value="mayank@okhdfcbank", key="pay_upi")
                elif mode == "Card":
                    cc = st.columns([2, 1, 1])
                    cc[0].text_input("Card number", value="4111 1111 1111 1111", key="pay_card")
                    cc[1].text_input("Expiry", value="12/28", key="pay_exp")
                    cc[2].text_input("CVV", value="123", type="password", key="pay_cvv")
                else:
                    st.selectbox("Bank", ["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank"], key="pay_bank")
                if settings.mock_gateways:
                    st.caption("Sandbox gateway — no real money moves.")
                if st.button(f"Pay {c.money(quote['total_payable'])} and procure e-Stamp", type="primary", use_container_width=True):
                    try:
                        with st.spinner("Capturing payment and calling StockHolding…"):
                            payments.checkout(agreement, user, payment_mode=mode)
                            stamping.procure_estamp(agreement.id, agreement.state_code, quote["stamp_duty_amount"], user.full_name)
                            workflow.transition_state(agreement, "Paid", triggered_by=user.id)
                        st.rerun()
                    except InsufficientStampingBalanceError:
                        st.error("The platform's stamping account is temporarily depleted. Our operations team has been alerted; "
                                 "your payment was not captured. Please retry shortly.")
                    except Exception as exc:
                        st.error(f"Checkout failed: {exc}")
        else:
            c.notice(f"<b>Payment captured.</b> Invoice <span class='gl-mono'>{c.esc(agreement.payment.invoice_number)}</span> for "
                     f"{c.money(agreement.payment.total_amount)} is in your account.", "ok")
            pdf = payments.invoice_pdf(agreement.payment)
            if pdf:
                st.download_button("Download tax invoice", data=pdf, file_name=f"{agreement.payment.invoice_number}.pdf",
                                   mime="application/pdf", key="dl_invoice")

    with right:
        if estamp:
            with st.container(border=True):
                st.markdown("**e-Stamp certificate issued**")
                c.kv({"Certificate": estamp.certificate_number, "State": estamp.state_code,
                      "Duty": c.money(estamp.stamp_amount), "Vendor": estamp.vendor,
                      "Issued": estamp.issued_at.strftime("%d %b %Y %H:%M UTC") if estamp.issued_at else "—"})
                st.caption("This certificate becomes page one of the executed deed.")
            st.write("")
            if st.button("Next: signatures →", type="primary", use_container_width=True):
                _goto(5)
        else:
            c.stat("Platform stamping pool", c.money(stamping.get_prepaid_balance()),
                   "Live SHCIL prepaid balance", tone="danger" if stamping.is_low_balance() else "ok")
            st.write("")
            c.card("What happens on payment", "GoLegal debits the state duty from its SHCIL prepaid account, receives a certificate "
                                              "number, and merges the certificate into your deed. Every debit is journaled for reconciliation.")

    nav = st.columns([1, 4])
    if nav[0].button("← Back", use_container_width=True):
        _goto(3)


def _step_sign(wiz: Dict[str, Any], session, user: User) -> None:
    st.markdown("#### Everyone signs — in any order, from anywhere.")
    if not user or not wiz.get("agreement_id"):
        c.notice("Complete checkout first; signatory records are created when the e-Stamp is procured.", "warn")
        if st.button("← Back to checkout"):
            _goto(4)
        return

    agreements = AgreementService(session)
    workflow = WorkflowService(session)
    esign = ESignService(session)
    try:
        agreement = agreements.get_accessible(wiz["agreement_id"], user)
    except AgreementAccessError as exc:
        st.error(str(exc))
        return

    if agreement.status == "Paid":
        c.notice("Ready to dispatch. GoLegal will send each party a private, single-purpose link over WhatsApp, SMS and email.", "info")
        if st.button("Send signing links to all parties", type="primary"):
            with st.spinner("Minting capability tokens and dispatching…"):
                wiz["dispatched"] = workflow.open_for_signatures(agreement, triggered_by=user.id)
            st.rerun()

    progress = workflow.get_signing_progress(agreement.id)
    left, right = st.columns([1.1, 1], gap="large")

    with left:
        with st.container(border=True):
            c.progress_seal(progress["signed_count"], progress["total_parties"])
            st.write("")
            for party in agreement.parties:
                cols = st.columns([2.6, 1])
                with cols[0]:
                    st.markdown(c.party_row(party.full_name, party.party_type, party.aadhaar_masked, party.signing_status), unsafe_allow_html=True)
                with cols[1]:
                    if party.signing_status != "Signed" and agreement.status == "Pending_Signatures":
                        if st.button("Sign now", key=f"sign_{party.id}", use_container_width=True, type="primary"):
                            st.session_state["active_signing_party"] = party.id
                            st.rerun()
                    elif party.signing_status == "Signed":
                        sig = next((s for s in agreement.signatures if s.party_id == party.id), None)
                        if sig:
                            st.caption(f"{sig.signed_at.strftime('%d %b %H:%M') if sig.signed_at else ''} · {sig.transaction_ref}")
            if agreement.status == "Pending_Signatures":
                st.write("")
                b1, b2 = st.columns(2)
                if b1.button("Re-send links to pending", use_container_width=True):
                    sent = workflow.resend_invitations(agreement, triggered_by=user.id)
                    st.success(f"Reminded {len(sent)} party(ies)." if sent else "Everyone has already signed.")
                if b2.button("Copy signing links", use_container_width=True):
                    st.session_state["show_links"] = not st.session_state.get("show_links")
                    st.rerun()
                if st.session_state.get("show_links"):
                    for party in agreement.parties:
                        if party.signing_status != "Signed":
                            st.text_input(f"{party.full_name} ({party.party_type})", value=workflow.signing_url_for(party), key=f"lnk_{party.id}")

        active_id = st.session_state.get("active_signing_party")
        if active_id:
            party = next((p for p in agreement.parties if p.id == active_id), None)
            if party:
                _esign_modal(session, esign, workflow, agreement, party)

    with right:
        if agreement.status == "Completed":
            c.notice("<b>Executed and sealed.</b> The corporate DSC is applied and the Section 65B certificate is attached.", "ok")
            pdf = workflow.final_pdf(agreement)
            if pdf:
                st.download_button("Download sealed agreement", data=pdf, file_name=f"GoLegal_{agreement.id[:8]}.pdf",
                                   mime="application/pdf", type="primary", use_container_width=True, key="dl_final_wizard")
                c.kv({"SHA-256 digest": agreement.final_pdf_sha256 or "", "Executed at": agreement.executed_at.strftime("%d %b %Y %H:%M UTC") if agreement.executed_at else ""})
            st.write("")
            if st.button("Open my agreements", use_container_width=True):
                go("My agreements")
        else:
            parties_status = [{"name": p.full_name, "type": p.party_type, "status": p.signing_status,
                               "hash": next((s.signature_hash for s in agreement.signatures if s.party_id == p.id), "")}
                              for p in agreement.parties]
            c.deed_preview(agreements.load_payload(agreement),
                           get_default_clauses(agreement.get_clause_toggles(), agreement.agreement_type),
                           estamp={"certificate_number": agreement.estamp.certificate_number, "stamp_amount": agreement.estamp.stamp_amount} if agreement.estamp else None,
                           parties_status=parties_status, sealed=False)


def _esign_modal(session, esign: ESignService, workflow: WorkflowService, agreement, party: Party) -> None:
    st.write("")
    with st.container(border=True):
        st.markdown(f"##### Aadhaar eSign — {c.esc(party.full_name)}")
        st.markdown("""<div class="gl-notice info"><b>UIDAI consent.</b> I voluntarily authorise GoLegal and its licensed eSign Service
        Provider to authenticate my identity with UIDAI using Aadhaar OTP, solely to affix my electronic signature to this deed under
        Sections 4 and 5 of the Information Technology Act, 2000. My Aadhaar number is not stored.<br/>
        <span style="font-size:.85rem">मैं स्वेच्छा से इस अनुबंध पर हस्ताक्षर करने हेतु आधार OTP द्वारा पहचान सत्यापन की सहमति देता/देती हूँ।</span></div>""",
                    unsafe_allow_html=True)
        c.kv({"Signatory": party.full_name, "Role": party.party_type, "Aadhaar": party.aadhaar_masked or "—",
              "Mobile": party.phone, "Attempts remaining": esign.remaining_attempts(party.aadhaar_masked or party.id)})
        consent = st.checkbox("I agree to the UIDAI authentication terms above", key=f"consent_{party.id}")
        if not st.session_state.get(f"otp_sent_{party.id}"):
            if st.button("Send Aadhaar OTP", type="primary", key=f"otp_send_{party.id}"):
                try:
                    otp = esign.request_otp(party.aadhaar_masked or party.id)
                    st.session_state[f"otp_sent_{party.id}"] = True
                    if settings.mock_gateways:
                        st.info(f"Sandbox: OTP is **{otp}**")
                    st.rerun()
                except RateLimitLockoutError as exc:
                    st.error(str(exc))
        else:
            otp = st.text_input("6-digit Aadhaar OTP", max_chars=6, key=f"otp_{party.id}")
            b1, b2 = st.columns(2)
            if b1.button("Verify and affix signature", type="primary", key=f"otp_verify_{party.id}"):
                try:
                    esign.verify_otp_and_sign(agreement.id, party.id, party.aadhaar_masked or party.id, otp, consent)
                    st.session_state.pop(f"otp_sent_{party.id}", None)
                    st.session_state.pop("active_signing_party", None)
                    if workflow.check_and_complete_signing(agreement.id):
                        st.balloons()
                    st.rerun()
                except (AadhaarVerificationError, RateLimitLockoutError) as exc:
                    st.error(str(exc))
            if b2.button("Cancel", key=f"otp_cancel_{party.id}"):
                st.session_state.pop(f"otp_sent_{party.id}", None)
                st.session_state.pop("active_signing_party", None)
                st.rerun()


# ----------------------------------------------------------------------- entry
def render_wizard(session, user) -> None:
    wiz = wizard_state()
    head = st.columns([3, 1])
    with head[0]:
        st.markdown("### Create an agreement")
    with head[1]:
        if st.button("Start over", use_container_width=True):
            reset_wizard()
            st.rerun()
    c.stepper(wiz["step"], STEPS)

    step = wiz["step"]
    if step == 1:
        _step_jurisdiction(wiz)
    elif step == 2:
        _step_parties(wiz)
    elif step == 3:
        _step_clauses(wiz)
    elif step == 4:
        _step_checkout(wiz, session, user)
    else:
        _step_sign(wiz, session, user)
