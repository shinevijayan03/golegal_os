"""
GoLegal UI - Public landing page
"""
from __future__ import annotations

import streamlit as st

from ai.rent_benchmark import benchmark
from services.agreement_service import demo_payload
from services.rule_engine import STATE_STAMP_RULES, calculate_stamp_duty, get_default_clauses
from ui import components as c
from ui.state import go, reset_wizard


def render_landing_page(user=None) -> None:
    c.eyebrow("GoLegal OS · The agentic operating system for legal work.")
    c.display("A stamped, signed rental deed.<br/><em>Ten minutes.</em> No broker, no queue.",
              "Draft on lawyer-vetted clauses, pay stamp duty online, and let everyone sign from their phone. "
              "Valid in Indian courts under the IT Act 2000, with a Section 65B certificate attached.")
    col_a, col_b, col_c = st.columns([1.2, 1.2, 3])
    with col_a:
        if st.button("Create agreement", type="primary", use_container_width=True):
            go("Create agreement")
    with col_b:
        if st.button("Try the demo deed", use_container_width=True):
            reset_wizard(demo_payload(), step=3)
            go("Create agreement")
    st.write("")
    c.trust_strip()
    st.write("")

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("#### How it works")
        c.how_it_works()
        st.write("")
        st.markdown("#### Why people switch")
        r1, r2 = st.columns(2)
        with r1:
            c.card("Under 10 minutes, end to end", "Traditional execution takes 3 to 14 days across drafting, courier, stamp vendor and wet signatures.")
            st.write("")
            c.card("Parties anywhere in India", "Landlord in Delhi, tenant in Bangalore, witness in Mumbai. Tokenized links, Aadhaar OTP, any order.")
        with r2:
            c.card("Half the cost, no markups", "Flat platform fee plus the actual state duty. No broker margin, no notary run-around.")
            st.write("")
            c.card("Evidence that holds up", "Every sealed deed carries signer IPs, timestamps, PKCS#7 hashes and a SHA-256 digest on its Section 65B page.")

    with right:
        st.markdown("#### What will it cost?")
        with st.container(border=True):
            state_options = {k: v["name"] for k, v in STATE_STAMP_RULES.items()}
            state = st.selectbox("Property state", options=list(state_options), format_func=lambda x: f"{state_options[x]} ({x})", key="lp_state")
            rent = st.number_input("Monthly rent (₹)", min_value=1000, max_value=1_000_000, value=25000, step=1000, key="lp_rent")
            deposit = st.number_input("Security deposit (₹)", min_value=0, max_value=5_000_000, value=100000, step=5000, key="lp_dep")
            q = calculate_stamp_duty(state, rent, deposit, months=11)
            m1, m2 = st.columns(2)
            with m1:
                c.stat("State stamp duty", c.money(q["stamp_duty_amount"]), q["article"])
            with m2:
                c.stat("Total payable", c.money(q["total_payable"]), f"incl. ₹{q['platform_fee']:.0f} fee + 18% GST", tone="ok")
            city = {"KA": "Bangalore", "DL": "Delhi", "MH": "Mumbai", "TN": "Chennai", "TS": "Hyderabad", "HR": "Gurgaon"}.get(state)
            if city:
                b = benchmark(city, "", "2BHK", rent, deposit)
                if b.get("supported") and b.get("insights"):
                    c.notice("<b>Market check.</b> " + c.esc(b["insights"][0]), "info")
        st.write("")
        st.markdown("#### What the deed contains")
        with st.container(border=True):
            for cl in get_default_clauses()[:6]:
                lock = "🔒 " if not cl["derogable"] else ""
                st.markdown(f"**{lock}{cl['title']}** — <span style='color:#64748B;font-size:.85rem'>{cl['text'][:110]}…</span>", unsafe_allow_html=True)
            st.caption("🔒 statutory clauses cannot be edited; every other covenant is yours to customise.")

    st.write("")
    st.markdown("#### Questions people ask")
    faq = [
        ("Is an e-signed rental agreement valid in court?", "Yes. Sections 4, 5 and 10A of the IT Act 2000 recognise electronic records and Aadhaar-based electronic signatures. GoLegal OS appends a Section 65B certificate so the deed is admissible as evidence."),
        ("Do we still need to register it?", "11-month residential agreements only need stamp duty, which GoLegal OS pays through StockHolding. Leases of 12 months or more must additionally be registered with the Sub-Registrar."),
        ("What if my landlord is not tech-savvy?", "They receive a WhatsApp/SMS link, tap it, read the deed in plain language (Hindi and Kannada summaries are available) and enter the OTP sent to their Aadhaar-linked mobile. Nothing to install."),
        ("What happens to my Aadhaar number?", "It is used once for OTP verification and immediately masked to XXXXXXXX1234. GoLegal OS never stores the full number."),
    ]
    for q_, a_ in faq:
        with st.expander(q_):
            st.write(a_)
