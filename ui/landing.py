"""
GoLegal UI - Public Landing Page
"""
import streamlit as st
from services.rule_engine import calculate_stamp_duty, STATE_STAMP_RULES


def render_landing_page():
    # Hero Section
    st.markdown("""
    <div style="text-align: center; padding: 2rem 1rem; background: linear-gradient(135deg, #1E3A8A 0%, #0F172A 100%); border-radius: 12px; color: white; margin-bottom: 2rem;">
        <h1 style="color: #FFFFFF; font-size: 2.4rem; font-weight: 800; margin-bottom: 0.5rem;">
            ⚖️ GoLegal Digital Contracting
        </h1>
        <p style="font-size: 1.2rem; color: #93C5FD; max-width: 750px; margin: 0 auto 1.5rem auto;">
            Borderless, Contactless Contracting — 100% Legally Valid in Indian Courts in Under 10 Minutes.
        </p>
        <div style="display: flex; justify-content: center; gap: 1rem; flex-wrap: wrap;">
            <span style="background: rgba(255,255,255,0.15); padding: 0.4rem 0.8rem; border-radius: 20px; font-size: 0.85rem; border: 1px solid rgba(255,255,255,0.2);">
                🛡️ IT Act 2000 (§§ 4, 5, 10A)
            </span>
            <span style="background: rgba(255,255,255,0.15); padding: 0.4rem 0.8rem; border-radius: 20px; font-size: 0.85rem; border: 1px solid rgba(255,255,255,0.2);">
                📜 Section 65B Evidentiary Certificate
            </span>
            <span style="background: rgba(255,255,255,0.15); padding: 0.4rem 0.8rem; border-radius: 20px; font-size: 0.85rem; border: 1px solid rgba(255,255,255,0.2);">
                🏛️ StockHolding e-Stamp Partner
            </span>
            <span style="background: rgba(255,255,255,0.15); padding: 0.4rem 0.8rem; border-radius: 20px; font-size: 0.85rem; border: 1px solid rgba(255,255,255,0.2);">
                🔑 UIDAI Aadhaar eSign
            </span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader("🚀 3-Click Frictionless Execution")
        st.markdown("""
        1. **1. Choose & Customize**: Select state jurisdiction (e.g. Karnataka ₹100 e-Stamp) and fill structured landlord, tenant, and property details.
        2. **2. Instant e-Stamping**: Automated integration with StockHolding Corporation of India (SHCIL) generates genuine government stamp certificates.
        3. **3. Multi-Party Aadhaar eSign**: Counterparties sign asynchronously via secure OTP links sent to WhatsApp and Email. Instant tamper-proof sealed PDF download.
        """)

        st.info("💡 **HRA & Address Proof Ready**: Downloaded contracts include an automated Section 65B Electronic Evidentiary Certificate accepted by corporates and authorities.")

        if st.button("📝 Start Rental Agreement Now", type="primary", use_container_width=True):
            st.session_state["active_tab"] = "Create Agreement"
            st.rerun()

    with col2:
        st.subheader("🧮 Dynamic Stamp Duty Estimator")
        with st.container(border=True):
            state_options = {k: v["name"] for k, v in STATE_STAMP_RULES.items()}
            selected_state = st.selectbox(
                "Select Property State / Jurisdiction:",
                options=list(state_options.keys()),
                format_func=lambda x: f"{state_options[x]} ({x})"
            )

            rent = st.number_input("Monthly Rent (INR):", min_value=1000, max_value=1000000, value=25000, step=1000)
            deposit = st.number_input("Refundable Security Deposit (INR):", min_value=0, max_value=5000000, value=100000, step=5000)

            duty_calc = calculate_stamp_duty(selected_state, rent, deposit, months=11)

            st.divider()
            c_a, c_b = st.columns(2)
            c_a.metric("Statutory Stamp Duty", f"₹ {duty_calc['stamp_duty_amount']:.2f}")
            c_b.metric("GoLegal Platform Fee", f"₹ {duty_calc['platform_fee']:.2f}")
            
            st.markdown(f"""
            - **GST (18%)**: ₹ {duty_calc['gst_amount']:.2f}
            - **Total Estimated Cost**: <span style="color:#059669; font-weight:bold; font-size:1.1rem;">₹ {duty_calc['total_payable']:.2f}</span>
            """, unsafe_allow_html=True)

    st.divider()

    # Value Pillars
    st.subheader("💎 Why Choose GoLegal?")
    vp1, vp2, vp3, vp4 = st.columns(4)
    with vp1:
        st.markdown("""
        <div style="background:#F8FAFC; padding:1rem; border-radius:8px; border:1px solid #E2E8F0; text-align:center;">
            <h4>⚡ Under 10 Mins</h4>
            <p style="font-size:0.85rem; color:#475569;">Eliminate 14-day broker and sub-registrar delays with instant digital processing.</p>
        </div>
        """, unsafe_allow_html=True)
    with vp2:
        st.markdown("""
        <div style="background:#F8FAFC; padding:1rem; border-radius:8px; border:1px solid #E2E8F0; text-align:center;">
            <h4>💰 50%+ Savings</h4>
            <p style="font-size:0.85rem; color:#475569;">No arbitrary broker stamp markups or hidden notary charges. Transparent flat pricing.</p>
        </div>
        """, unsafe_allow_html=True)
    with vp3:
        st.markdown("""
        <div style="background:#F8FAFC; padding:1rem; border-radius:8px; border:1px solid #E2E8F0; text-align:center;">
            <h4>📱 Remote Signing</h4>
            <p style="font-size:0.85rem; color:#475569;">Landlord in Delhi, Tenant in Bangalore, Witnesses in Mumbai. Sign asynchronously anywhere.</p>
        </div>
        """, unsafe_allow_html=True)
    with vp4:
        st.markdown("""
        <div style="background:#F8FAFC; padding:1rem; border-radius:8px; border:1px solid #E2E8F0; text-align:center;">
            <h4>🔒 Zero Hoarding</h4>
            <p style="font-size:0.85rem; color:#475569;">Aadhaar masked as XXXXXXXX1234. Consent-based storage with 27-day automated draft purge.</p>
        </div>
        """, unsafe_allow_html=True)
