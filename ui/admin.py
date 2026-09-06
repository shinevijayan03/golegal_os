"""
GoLegal UI - Platform Operations & Admin Stamping Ledger Console
"""
import streamlit as st
from persistence.database import SessionLocal
from domain.models import SysConfig, SysConfigJn, Agreement, EStamp
from services.stamping_service import StampingService


def render_admin():
    st.title("⚙️ Platform Operations & Stamping Console")

    session = SessionLocal()
    try:
        stamping_svc = StampingService(session)
        balance = stamping_svc.get_prepaid_balance()
        is_low = stamping_svc.is_low_balance()

        # -------------------------------------------------------------
        # Section 1: StockHolding Prepaid Account Monitor
        # -------------------------------------------------------------
        st.subheader("🏛️ StockHolding Corporation of India (SHCIL) Prepaid Stamping Account")

        col_bal1, col_bal2 = st.columns([1.5, 1], gap="medium")

        with col_bal1:
            if is_low:
                st.error(f"""
                🚨 **CRITICAL WARNING: LOW PREPAID BALANCE!**  
                Available Balance: **₹ {balance:,.2f}** (Threshold: < ₹10,000.00)  
                Transactions may fail if deposit is depleted. Recharge immediately.
                """)
            else:
                st.success(f"🟢 **Healthy Reserve**: Available Balance: **₹ {balance:,.2f}**")

            with st.container(border=True):
                st.metric(
                    label="Current SHCIL Prepaid Balance",
                    value=f"₹ {balance:,.2f}",
                    delta=f"{'- Critical' if is_low else '+ Available'}"
                )

        with col_bal2:
            with st.container(border=True):
                st.markdown("##### 💳 Account Recharge / Top-Up")
                top_amt = st.number_input("Top-Up Amount (INR):", min_value=1000, value=25000, step=5000)
                if st.button("Replenish Stamping Deposit", type="primary", use_container_width=True):
                    new_bal = stamping_svc.top_up_balance(top_amt, admin_user="ADMIN_CONSOLE_USER")
                    st.success(f"Deposit replenished! New balance: ₹ {new_bal:,.2f}")
                    st.rerun()

                st.markdown("---")
                if st.button("Simulate Low Balance (< ₹10,000)", type="secondary", use_container_width=True):
                    cfg = session.query(SysConfig).filter_by(id="GLOBAL_CONFIG").first()
                    cfg.stockholding_prepaid_balance = 8500.0
                    session.commit()
                    st.warning("Prepaid balance set to ₹8,500.00 for alert verification.")
                    st.rerun()

        st.divider()

        # -------------------------------------------------------------
        # Section 2: Sales GMV & Operational Velocity Metrics
        # -------------------------------------------------------------
        st.subheader("📊 Sales GMV & Transaction Telemetry")
        agreements = session.query(Agreement).all()
        completed_agreements = [a for a in agreements if a.status == "Completed"]

        m1, m2, m3, m4 = st.columns(4)
        total_gmv = sum(a.get_commercial_terms().get("monthly_rent", 0) * 11 for a in completed_agreements)
        total_fees = len(completed_agreements) * 299.0

        m1.metric("Total Contracts Initiated", len(agreements))
        m2.metric("Executed & Certified", len(completed_agreements))
        m3.metric("Platform Gross Revenue", f"₹ {total_fees:,.2f}")
        m4.metric("Contract GMV Under Lease", f"₹ {total_gmv:,.0f}")

        st.divider()

        # -------------------------------------------------------------
        # Section 3: Stamping Debit Ledger (sysconfigTlb$jn)
        # -------------------------------------------------------------
        st.subheader("📜 SHCIL Stamping Audit Journal (`sysconfigTlb$jn`)")
        journals = session.query(SysConfigJn).order_by(SysConfigJn.timestamp.desc()).limit(10).all()
        if not journals:
            st.info("No journal transactions recorded yet.")
        else:
            j_data = []
            for j in journals:
                j_data.append({
                    "Timestamp (UTC)": j.timestamp.strftime("%Y-%m-%d %H:%M:%S") if j.timestamp else "N/A",
                    "Operation": j.operation,
                    "Actor": j.updated_by_user,
                    "New State Payload": j.new_value
                })
            st.table(j_data)

        st.divider()

        # -------------------------------------------------------------
        # Section 4: Customer Feedback & NPS Detractor Logs
        # -------------------------------------------------------------
        st.subheader("⭐ Customer Feedback & NPS Detractor Logs")
        nps_logs = st.session_state.get("nps_logs", [])
        if not nps_logs:
            st.info("No customer feedback submitted yet. Users can submit ratings in the Dashboard tab.")
        else:
            for item in nps_logs:
                with st.container(border=True):
                    st.markdown(f"**Score**: `{item['score']}/10` | **Category**: `{item.get('tag', 'General')}`")
                    st.write(f"\"{item.get('comment', '')}\"")

    finally:
        session.close()
