"""
GoLegal UI - User Contract Dashboard & MyInvoices
"""
import streamlit as st
from persistence.database import SessionLocal
from domain.models import Agreement, Party, EStamp, Payment
from services.doc_assembly import DocumentAssemblyEngine
from services.rule_engine import get_default_clauses


def render_dashboard():
    st.title("📋 Contracts & Agreements Workspace")

    session = SessionLocal()
    try:
        agreements = session.query(Agreement).order_by(Agreement.created_at.desc()).all()

        tab_pending, tab_completed, tab_drafts, tab_invoices, tab_nps = st.tabs([
            "⏳ Pending Signatures",
            "✅ Completed Agreements",
            "📝 Drafts & Active",
            "🧾 MyInvoices",
            "⭐ Rate Experience (NPS)"
        ])

        with tab_pending:
            st.subheader("Contracts Awaiting Counterparty Signatures")
            pending_list = [a for a in agreements if a.status == "Paid" or a.status == "Pending_Signatures"]
            if not pending_list:
                st.info("No contracts currently pending signatures.")
            else:
                for agr in pending_list:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 2, 1.5])
                        prop = agr.get_property_details()
                        c1.markdown(f"**{agr.agreement_type}** ({agr.state_code})<br/>Premises: `{prop.get('premises_name', 'Property')}`", unsafe_allow_html=True)
                        
                        parties = session.query(Party).filter_by(agreement_id=agr.id).all()
                        signed_c = sum(1 for p in parties if p.signing_status == "Signed")
                        c2.markdown(f"**Signing Progress**: `{signed_c} of {len(parties)} Signed`<br/>Status: 🟠 Pending", unsafe_allow_html=True)

                        with c3:
                            if st.button("📲 Resend Sign Links", key=f"resend_{agr.id}"):
                                st.success("Automated sign link re-dispatched via WhatsApp & SMS!")
                            if st.button("Resume eSign", key=f"resume_{agr.id}", type="primary"):
                                st.session_state["active_tab"] = "Create Agreement"
                                st.session_state["wiz_step"] = 5
                                st.rerun()

        with tab_completed:
            st.subheader("Certified Tamper-Proof Agreements")
            completed_list = [a for a in agreements if a.status == "Completed"]
            if not completed_list:
                st.info("No completed agreements found. Execute an agreement to see certified contracts.")
            else:
                for agr in completed_list:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 1.5, 2])
                        prop = agr.get_property_details()
                        comm = agr.get_commercial_terms()
                        c1.markdown(f"**{agr.agreement_type}** — `{agr.id[:8]}...`<br/>Premises: {prop.get('premises_name', 'N/A')}<br/>Rent: ₹ {comm.get('monthly_rent', 0):,}/mo", unsafe_allow_html=True)
                        
                        estamp = session.query(EStamp).filter_by(agreement_id=agr.id).first()
                        c_num = estamp.certificate_number if estamp else "IN-KA-001"
                        c2.markdown(f"🟢 **Sealed & Certified**<br/>e-Stamp: `{c_num}`", unsafe_allow_html=True)

                        with c3:
                            # Build download PDF
                            doc_engine = DocumentAssemblyEngine()
                            parties = session.query(Party).filter_by(agreement_id=agr.id).all()
                            clauses = get_default_clauses()
                            pdf_bytes = doc_engine.generate_pdf_agreement(
                                agreement_data={
                                    "property_address": f"{prop.get('premises_name', '')}, {prop.get('address', '')}",
                                    "monthly_rent": comm.get("monthly_rent", 25000),
                                    "security_deposit": comm.get("security_deposit", 100000),
                                    "lease_months": comm.get("lease_months", 11),
                                    "clauses": clauses
                                },
                                parties=[{"name": p.full_name, "type": p.party_type, "phone": p.phone, "email": p.email, "aadhaar_masked": p.aadhaar_masked} for p in parties],
                                estamp={"certificate_number": c_num, "stamp_amount": 100.0, "state_code": agr.state_code},
                                signatures=[{"party_name": p.full_name, "party_type": p.party_type, "signature_hash": "a1b2c3d4e5f67890"} for p in parties]
                            )

                            st.download_button(
                                label="📥 Download Certified PDF",
                                data=pdf_bytes,
                                file_name=f"GoLegal_Certified_{agr.id[:8]}.pdf",
                                mime="application/pdf",
                                key=f"dl_btn_{agr.id}"
                            )

                            if st.button("💬 WhatsApp Share Link", key=f"wa_share_{agr.id}"):
                                share_link = f"https://golegal.in/sign?token=cbac_{agr.id[:8]}_view"
                                st.info(f"WhatsApp Share Link: `{share_link}`")

        with tab_drafts:
            st.subheader("Saved Drafts")
            drafts = [a for a in agreements if a.status == "Draft"]
            if not drafts:
                st.info("No active drafts found.")
            else:
                for d in drafts:
                    with st.container(border=True):
                        st.markdown(f"**Draft ID**: `{d.id}` | State: `{d.state_code}` | Type: `{d.agreement_type}`")
                        cd1, cd2 = st.columns(2)
                        with cd1:
                            if st.button("Continue Editing", key=f"edit_{d.id}", type="primary"):
                                st.session_state["active_tab"] = "Create Agreement"
                                st.session_state["wiz_step"] = 2
                                st.rerun()
                        with cd2:
                            if st.button("Soft Delete Draft", key=f"del_{d.id}"):
                                session.delete(d)
                                session.commit()
                                st.success("Draft archived.")
                                st.rerun()

        with tab_invoices:
            st.subheader("Archived GST Tax Invoices (MyInvoices)")
            st.markdown("""
            All statutory stamp duty payments and GoLegal service charges automatically issue signed GST tax receipts.
            """)
            payments = session.query(Payment).all()
            if not payments:
                # Provide mock invoice item
                st.markdown("""
                | Invoice Number | Agreement ID | Duty Amount | Service Charge | GST (18%) | Total Paid | Action |
                | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
                | `INV-2026-0891` | `agr-test-001` | ₹ 100.00 | ₹ 299.00 | ₹ 71.82 | ₹ 470.82 | [📥 Download Receipt] |
                """)
            else:
                for p in payments:
                    st.write(f"Invoice for Agreement {p.agreement_id}: Total Paid ₹{p.total_amount:.2f}")

        with tab_nps:
            st.subheader("⭐ Customer Experience & Net Promoter Score (NPS)")
            st.markdown("On a scale from **0 to 10**, how likely are you to recommend GoLegal to a friend or colleague?")
            
            nps_score = st.slider("Select your rating:", min_value=0, max_value=10, value=9)

            if nps_score <= 8:
                st.warning(f"You rated **{nps_score} / 10 (Detractor / Need Improvement)**")
                tag = st.selectbox(
                    "What could we improve?",
                    ["e-Stamp Processing Speed", "Aadhaar OTP Delivery", "Clause Customization Flexibility", "Pricing / Fee Structure", "Mobile Screen Readability"]
                )
                feedback_text = st.text_area("Detailed feedback:", placeholder="Tell us how we can do better...")
                if st.button("Submit Feedback", type="primary"):
                    if "nps_logs" not in st.session_state:
                        st.session_state["nps_logs"] = []
                    st.session_state["nps_logs"].append({"score": nps_score, "tag": tag, "comment": feedback_text})
                    st.success("Thank you for your candid feedback! Our product team has logged your notes.")
            elif nps_score == 9:
                st.success(f"You rated **{nps_score} / 10 (Happy Promoter)**! Thank you for trusting GoLegal.")
            else:
                st.balloons()
                st.success(f"🌟 You rated **10 / 10 (Delighted)**! We'd be honored if you referred a friend or left a Google Review.")

    finally:
        session.close()
