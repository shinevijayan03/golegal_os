"""
GoLegal UI - 5-Step Rental Agreement Wizard & Split-Pane Clause Editor
"""
import streamlit as st
import uuid
from services.validation import (
    validate_pan, validate_pincode, validate_email, validate_phone, mask_aadhaar, validate_commercial_terms
)
from services.rule_engine import calculate_stamp_duty, get_default_clauses, STATE_STAMP_RULES
from services.stamping_service import StampingService
from services.esign_service import ESignService
from services.doc_assembly import DocumentAssemblyEngine
from persistence.database import SessionLocal
from domain.models import Agreement, Party, User


def render_wizard():
    st.title("📝 5-Step Digital Agreement Wizard")

    # Initialize wizard state defaults if not present
    if "wiz_step" not in st.session_state:
        st.session_state["wiz_step"] = 1

    if "wiz_data" not in st.session_state:
        st.session_state["wiz_data"] = {
            "state_code": "KA",
            "agreement_type": "Rental_Residential",
            "owner": {
                "name": "Ramakiran Reddy",
                "phone": "9876543210",
                "email": "ramakiran.reddy@example.com",
                "pan": "ABCDE1234F",
                "aadhaar": "123456789012"
            },
            "tenant": {
                "name": "Mayank Tripathi",
                "phone": "9876543211",
                "email": "mayank.tripathi@example.com",
                "pan": "XYZAB5678C",
                "aadhaar": "987654321098"
            },
            "co_tenants": [],
            "witnesses": [
                {"name": "Suresh Kumar", "phone": "9876543212", "email": "suresh@example.com", "aadhaar": "111122223333"}
            ],
            "property": {
                "premises_name": "Sunrise Apts Flat 402",
                "address": "Outer Ring Road, Bellandur",
                "city": "Bangalore",
                "pincode": "560103"
            },
            "commercials": {
                "monthly_rent": 28000,
                "security_deposit": 120000,
                "lease_months": 11,
                "notice_days": 30,
                "rent_due_day": 5
            },
            "clauses_toggles": {
                "pets_allowed": False,
                "painting_deduction": True
            },
            "custom_clauses_text": "",
            "cloud_storage_consent": True,
            "payment_completed": False,
            "signed_parties": set(),
            "agreement_id": str(uuid.uuid4())
        }

    wiz_data = st.session_state["wiz_data"]
    step = st.session_state["wiz_step"]

    # Step Progress Indicator
    steps = [
        "1. Jurisdiction",
        "2. Parties & Property",
        "3. Clauses & Preview",
        "4. Stamping & Pay",
        "5. Aadhaar eSign"
    ]
    st.progress(step / 5.0)
    cols = st.columns(5)
    for idx, (c, s_name) in enumerate(zip(cols, steps), start=1):
        if idx == step:
            c.markdown(f"<span style='color:#1E3A8A; font-weight:bold;'>🔵 {s_name}</span>", unsafe_allow_html=True)
        elif idx < step:
            c.markdown(f"<span style='color:#059669;'>🟢 {s_name}</span>", unsafe_allow_html=True)
        else:
            c.markdown(f"<span style='color:#94A3B8;'>⚪ {s_name}</span>", unsafe_allow_html=True)

    st.divider()

    # -------------------------------------------------------------
    # STEP 1: Agreement Type & Jurisdiction
    # -------------------------------------------------------------
    if step == 1:
        st.subheader("Step 1: Agreement Type & State Jurisdiction")
        with st.container(border=True):
            wiz_data["agreement_type"] = st.selectbox(
                "Select Agreement Category:",
                ["Rental_Residential", "Rental_Commercial", "Mutual_NDA", "Custom_Contract"],
                index=0
            )

            state_map = {k: v["name"] for k, v in STATE_STAMP_RULES.items()}
            wiz_data["state_code"] = st.selectbox(
                "Select Property State (Statutory Stamp Jurisdiction):",
                list(state_map.keys()),
                format_func=lambda x: f"{state_map[x]} ({x})"
            )

            st.info(f"🏛️ Selected Jurisdiction: **{state_map[wiz_data['state_code']]}**. Statutory e-Stamp paper will be procured from StockHolding Corporation of India Limited (SHCIL).")

            c1, c2 = st.columns([4, 1])
            with c2:
                if st.button("Next: Parties ➡️", type="primary", use_container_width=True):
                    st.session_state["wiz_step"] = 2
                    st.rerun()

    # -------------------------------------------------------------
    # STEP 2: Structured Metadata Ingestion
    # -------------------------------------------------------------
    elif step == 2:
        st.subheader("Step 2: Parties, Property & Commercial Terms")

        with st.expander("👤 First Party (Owner / Landlord)", expanded=True):
            o = wiz_data["owner"]
            c1, c2 = st.columns(2)
            o["name"] = c1.text_input("Owner Full Legal Name:", o["name"])
            o["phone"] = c2.text_input("Owner Contact Mobile:", o["phone"])
            o["email"] = c1.text_input("Owner Email:", o["email"])
            o["pan"] = c2.text_input("Owner PAN Card (ABCDE1234F):", o["pan"])
            o["aadhaar"] = c1.text_input("Owner 12-Digit Aadhaar (Stored Masked):", o["aadhaar"], type="password")

        with st.expander("👥 Second Party (Tenant / Co-Tenants)", expanded=True):
            t = wiz_data["tenant"]
            c1, c2 = st.columns(2)
            t["name"] = c1.text_input("Tenant Full Legal Name:", t["name"])
            t["phone"] = c2.text_input("Tenant Contact Mobile:", t["phone"])
            t["email"] = c1.text_input("Tenant Email:", t["email"])
            t["pan"] = c2.text_input("Tenant PAN Card:", t["pan"])
            t["aadhaar"] = c1.text_input("Tenant 12-Digit Aadhaar:", t["aadhaar"], type="password")

            # Co-tenant add toggle
            has_co = st.checkbox("Add Co-Tenant / Roommate?", value=len(wiz_data["co_tenants"]) > 0)
            if has_co and len(wiz_data["co_tenants"]) == 0:
                wiz_data["co_tenants"].append({"name": "Anushka Verma", "phone": "9876543215", "email": "anushka@example.com", "aadhaar": "222233334444"})

            if has_co:
                for idx, ct in enumerate(wiz_data["co_tenants"]):
                    st.markdown(f"**Co-Tenant #{idx+1}**")
                    cc1, cc2 = st.columns(2)
                    ct["name"] = cc1.text_input(f"Co-Tenant Name #{idx+1}:", ct["name"], key=f"ct_name_{idx}")
                    ct["phone"] = cc2.text_input(f"Co-Tenant Mobile #{idx+1}:", ct["phone"], key=f"ct_phone_{idx}")

        with st.expander("🏢 Property Schedule & Commercial Terms", expanded=True):
            p = wiz_data["property"]
            c = wiz_data["commercials"]
            p1, p2 = st.columns(2)
            p["premises_name"] = p1.text_input("Premises / Building Name:", p["premises_name"])
            p["address"] = p2.text_input("Full Property Address:", p["address"])
            p["city"] = p1.text_input("City:", p["city"])
            p["pincode"] = p2.text_input("Postal PIN Code (6-Digit):", p["pincode"])

            c1, c2, c3 = st.columns(3)
            c["monthly_rent"] = c1.number_input("Monthly Rent (INR):", min_value=500, value=c["monthly_rent"], step=1000)
            c["security_deposit"] = c2.number_input("Security Deposit (INR):", min_value=0, value=c["security_deposit"], step=5000)
            c["lease_months"] = c3.number_input("Lease Duration (Months):", min_value=1, max_value=60, value=c["lease_months"])

        with st.expander("👁️ Witnesses", expanded=False):
            w = wiz_data["witnesses"][0]
            w1, w2 = st.columns(2)
            w["name"] = w1.text_input("Witness 1 Full Name:", w["name"])
            w["phone"] = w2.text_input("Witness 1 Phone:", w["phone"])
            w["email"] = w1.text_input("Witness 1 Email:", w["email"])
            w["aadhaar"] = w2.text_input("Witness 1 Aadhaar:", w["aadhaar"], type="password")

        wiz_data["cloud_storage_consent"] = st.checkbox(
            "🔒 I grant explicit consent for GoLegal to archive the signed contract indefinitely with AES-256 encryption. (If unchecked, draft files are automatically purged after 27 days).",
            value=wiz_data["cloud_storage_consent"]
        )

        b1, b2 = st.columns([1, 1])
        with b1:
            if st.button("⬅️ Previous: Jurisdiction"):
                st.session_state["wiz_step"] = 1
                st.rerun()
        with b2:
            if st.button("Next: Clause Editor & Preview ➡️", type="primary"):
                # Validate inputs
                errors = []
                if not validate_pan(wiz_data["owner"]["pan"]):
                    errors.append("Invalid Owner PAN format.")
                if not validate_pincode(wiz_data["property"]["pincode"]):
                    errors.append("Invalid 6-digit Property PIN code.")
                if not validate_email(wiz_data["tenant"]["email"]):
                    errors.append("Invalid Tenant Email.")
                
                comm_errors = validate_commercial_terms(c["monthly_rent"], c["security_deposit"], c["lease_months"])
                errors.extend(comm_errors)

                if errors:
                    for err in errors:
                        st.error(f"❌ {err}")
                else:
                    st.session_state["wiz_step"] = 3
                    st.rerun()

    # -------------------------------------------------------------
    # STEP 3: Split-Pane Clause Editor & Watermarked Live Preview
    # -------------------------------------------------------------
    elif step == 3:
        st.subheader("Step 3: Split-Pane Clause Customization & Live Draft Preview")

        col_left, col_right = st.columns([1, 1.2], gap="medium")

        with col_left:
            st.markdown("#### ⚙️ Clause Customization Panel")
            toggles = wiz_data["clauses_toggles"]
            toggles["pets_allowed"] = st.toggle("🐾 Pets Allowed on Premises", value=toggles["pets_allowed"])
            toggles["painting_deduction"] = st.toggle("🎨 Standard Painting Deduction upon Vacation", value=toggles["painting_deduction"])

            st.markdown("##### 📝 Additional Custom Legal Covenants:")
            wiz_data["custom_clauses_text"] = st.text_area(
                "Add bespoke terms or house rules:",
                value=wiz_data["custom_clauses_text"],
                placeholder="e.g. Parking space allocated for 1 four-wheeler; quiet hours observed after 11 PM.",
                height=120
            )

            st.markdown("##### 🏛️ Non-Derogable Statutory Clauses:")
            clauses = get_default_clauses(toggles)
            for cl in clauses:
                if not cl["derogable"]:
                    st.caption(f"🔒 **{cl['title']}**: {cl['text']}")

            b_back, b_next = st.columns(2)
            with b_back:
                if st.button("⬅️ Back to Metadata"):
                    st.session_state["wiz_step"] = 2
                    st.rerun()
            with b_next:
                if st.button("Proceed to Payment & Stamping ➡️", type="primary"):
                    st.session_state["wiz_step"] = 4
                    st.rerun()

        with col_right:
            st.markdown("#### 📄 Synchronized Real-Time Preview")
            with st.container(border=True, height=550):
                st.markdown("""
                <div style="border: 2px dashed #DC2626; padding: 0.5rem; border-radius: 6px; text-align: center; margin-bottom: 1rem;">
                    <span style="color: #DC2626; font-weight: 800; font-size: 0.85rem;">
                        *** UNEXECUTED DRAFT — FOR PREVIEW ONLY ***
                    </span>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                <div style="background: #D1FAE5; padding: 0.6rem; border-radius: 6px; border: 1px solid #059669; margin-bottom: 1rem;">
                    <h5 style="color: #065F46; margin: 0; text-align:center;">GOVERNMENT OF {wiz_data['state_code']} — SAMPLE e-STAMP</h5>
                    <p style="margin: 0; font-size: 0.8rem; color: #065F46; text-align:center;">
                        Certificate No: DRAFT-PREVIEW-001 | Duty: ₹ 100.00
                    </p>
                </div>
                """, unsafe_allow_html=True)

                st.markdown(f"""
                ### RESIDENTIAL RENTAL AGREEMENT
                This deed is executed between:
                - **Lessor / Owner**: {wiz_data['owner']['name']} (Aadhaar: {mask_aadhaar(wiz_data['owner']['aadhaar'])})
                - **Lessee / Tenant**: {wiz_data['tenant']['name']} (Aadhaar: {mask_aadhaar(wiz_data['tenant']['aadhaar'])})
                
                **Premises**: {wiz_data['property']['premises_name']}, {wiz_data['property']['address']}, {wiz_data['property']['city']} - {wiz_data['property']['pincode']}  
                **Monthly Rent**: ₹ {wiz_data['commercials']['monthly_rent']:,} | **Security Deposit**: ₹ {wiz_data['commercials']['security_deposit']:,}  
                **Lease Period**: {wiz_data['commercials']['lease_months']} Months  
                
                #### Covenants:
                """)
                for idx, c_item in enumerate(clauses, 1):
                    st.markdown(f"**{idx}. {c_item['title']}**: {c_item['text']}")

                if wiz_data["custom_clauses_text"].strip():
                    st.markdown(f"**Custom Covenants**: {wiz_data['custom_clauses_text'].strip()}")

    # -------------------------------------------------------------
    # STEP 4: Fee Breakdown & Payment Simulation
    # -------------------------------------------------------------
    elif step == 4:
        st.subheader("Step 4: Statutory e-Stamp Procurement & Platform Checkout")
        duty_calc = calculate_stamp_duty(
            wiz_data["state_code"],
            wiz_data["commercials"]["monthly_rent"],
            wiz_data["commercials"]["security_deposit"]
        )

        col_pay1, col_pay2 = st.columns([1.2, 1], gap="large")

        with col_pay1:
            st.markdown("#### 🧾 Itemized Tax Invoice & Duty Summary")
            with st.container(border=True):
                st.markdown(f"""
                | Item Description | Amount (INR) |
                | :--- | :--- |
                | **State e-Stamp Duty ({duty_calc['state_name']})** | ₹ {duty_calc['stamp_duty_amount']:.2f} |
                | **GoLegal Platform Service Charge** | ₹ {duty_calc['platform_fee']:.2f} |
                | **GST (18% on fees)** | ₹ {duty_calc['gst_amount']:.2f} |
                | **Total Amount Payable** | **₹ {duty_calc['total_payable']:.2f}** |
                """)

            st.markdown("#### 💳 Simulated Payment Gateway")
            mode = st.radio("Payment Mode:", ["UPI QR / VPA", "Debit / Credit Card", "NetBanking"], horizontal=True)
            if mode == "UPI QR / VPA":
                st.info("📱 Scan with GooglePay / PhonePe / Paytm to complete checkout")
            elif mode == "Debit / Credit Card":
                c_num = st.text_input("Card Number:", "4111 2222 3333 4444")
                c_exp = st.text_input("Expiry (MM/YY):", "12/28")

        with col_pay2:
            st.markdown("#### 🏛️ StockHolding e-Stamp Procurement")
            session = SessionLocal()
            try:
                stamping_svc = StampingService(session)
                shcil_balance = stamping_svc.get_prepaid_balance()
                st.metric("StockHolding Prepaid Pool Balance", f"₹ {shcil_balance:,.2f}")
                if shcil_balance < 10000:
                    st.warning("⚠️ Warning: Corporate Stamping pool is below ₹10,000 threshold.")
            finally:
                session.close()

            st.divider()
            if not wiz_data.get("payment_completed"):
                if st.button("💳 Pay & Procure e-Stamp Certificate", type="primary", use_container_width=True):
                    # Execute stamping procurement in DB
                    db = SessionLocal()
                    try:
                        # Ensure owner user exists
                        user = db.query(User).filter_by(email=wiz_data["owner"]["email"]).first()
                        if not user:
                            user = User(
                                id=str(uuid.uuid4()),
                                full_name=wiz_data["owner"]["name"],
                                email=wiz_data["owner"]["email"],
                                phone=wiz_data["owner"]["phone"],
                                address=wiz_data["property"]["address"]
                            )
                            db.add(user)
                            db.commit()

                        # Ensure agreement exists
                        agr = db.query(Agreement).filter_by(id=wiz_data["agreement_id"]).first()
                        if not agr:
                            agr = Agreement(
                                id=wiz_data["agreement_id"],
                                initiator_id=user.id,
                                agreement_type=wiz_data["agreement_type"],
                                state_code=wiz_data["state_code"],
                                status="Paid",
                                cloud_storage_consent=wiz_data["cloud_storage_consent"]
                            )
                            agr.set_property_details(wiz_data["property"])
                            agr.set_commercial_terms(wiz_data["commercials"])
                            db.add(agr)
                            db.commit()

                            # Add Parties
                            p_owner = Party(
                                agreement_id=agr.id,
                                party_type="Owner",
                                full_name=wiz_data["owner"]["name"],
                                email=wiz_data["owner"]["email"],
                                phone=wiz_data["owner"]["phone"],
                                aadhaar_masked=mask_aadhaar(wiz_data["owner"]["aadhaar"])
                            )
                            p_tenant = Party(
                                agreement_id=agr.id,
                                party_type="Tenant",
                                full_name=wiz_data["tenant"]["name"],
                                email=wiz_data["tenant"]["email"],
                                phone=wiz_data["tenant"]["phone"],
                                aadhaar_masked=mask_aadhaar(wiz_data["tenant"]["aadhaar"])
                            )
                            p_witness = Party(
                                agreement_id=agr.id,
                                party_type="Witness",
                                full_name=wiz_data["witnesses"][0]["name"],
                                email=wiz_data["witnesses"][0]["email"],
                                phone=wiz_data["witnesses"][0]["phone"],
                                aadhaar_masked=mask_aadhaar(wiz_data["witnesses"][0]["aadhaar"])
                            )
                            db.add_all([p_owner, p_tenant, p_witness])
                            db.commit()

                        # Procure e-Stamp
                        stamping = StampingService(db)
                        estamp = stamping.procure_estamp(
                            agreement_id=agr.id,
                            state_code=wiz_data["state_code"],
                            stamp_amount=duty_calc["stamp_duty_amount"],
                            purchased_by=wiz_data["owner"]["name"]
                        )
                        wiz_data["payment_completed"] = True
                        wiz_data["estamp_cert_number"] = estamp.certificate_number
                        st.success(f"✅ Payment captured! e-Stamp certificate generated: `{estamp.certificate_number}`")
                    finally:
                        db.close()
                    st.rerun()
            else:
                st.success(f"✅ Payment complete! Certificate: `{wiz_data.get('estamp_cert_number')}`")
                if st.button("Proceed to Aadhaar eSign ➡️", type="primary", use_container_width=True):
                    st.session_state["wiz_step"] = 5
                    st.rerun()

    # -------------------------------------------------------------
    # STEP 5: Aadhaar eSign Modal Simulation
    # -------------------------------------------------------------
    elif step == 5:
        st.subheader("Step 5: Multi-Party Aadhaar eSign OTP Verification")

        st.markdown("""
        <div style="background: #F8FAFC; border-left: 4px solid #1E3A8A; padding: 1rem; margin-bottom: 1.5rem;">
            <b>UIDAI STATUTORY CONSENT NOTICE:</b><br/>
            <i>I hereby provide voluntary consent to authenticate my electronic identity via Aadhaar OTP through an accredited 
            eSign Service Provider (ESP) for the sole purpose of digitally executing this legal rental deed in compliance with 
            Sections 4 & 5 of the Information Technology Act 2000.</i>
        </div>
        """, unsafe_allow_html=True)

        session = SessionLocal()
        try:
            parties = session.query(Party).filter_by(agreement_id=wiz_data["agreement_id"]).all()
            if not parties:
                st.warning("Please finalize Step 4 checkout to initialize signatory records.")
                if st.button("⬅️ Return to Step 4"):
                    st.session_state["wiz_step"] = 4
                    st.rerun()
                return

            st.markdown("#### ✍️ Signatory Execution Matrix")
            for p in parties:
                col_p1, col_p2, col_p3 = st.columns([1.5, 1, 1.2])
                col_p1.markdown(f"**{p.full_name}** ({p.party_type})<br/>`{p.aadhaar_masked}`", unsafe_allow_html=True)
                if p.signing_status == "Signed":
                    col_p2.markdown("🟢 **Signed & Stamped**")
                    col_p3.caption("PKCS#7 Hash Verified")
                else:
                    col_p2.markdown("🟠 **Pending Signature**")
                    if col_p3.button(f"Sign as {p.party_type}", key=f"sign_btn_{p.id}"):
                        st.session_state["active_signing_party"] = p.id
                        st.rerun()

            # Signing Modal if party clicked
            active_p_id = st.session_state.get("active_signing_party")
            if active_p_id:
                active_party = next((p for p in parties if p.id == active_p_id), None)
                if active_party:
                    st.divider()
                    st.subheader(f"🔐 Executing Aadhaar eSign for: {active_party.full_name}")
                    with st.container(border=True):
                        st.markdown(f"- **Signatory**: `{active_party.full_name}`")
                        st.markdown(f"- **Masked Aadhaar**: `{active_party.aadhaar_masked}`")
                        consent = st.checkbox("I agree to the UIDAI authentication terms", value=True)
                        otp_in = st.text_input("Enter 6-Digit Aadhaar OTP:", value="123456")
                        
                        b_exec, b_cancel = st.columns(2)
                        with b_exec:
                            if st.button("Verify OTP & Affix Digital Seal", type="primary"):
                                esign_svc = ESignService(session)
                                try:
                                    sig = esign_svc.verify_otp_and_sign(
                                        agreement_id=wiz_data["agreement_id"],
                                        party_id=active_party.id,
                                        aadhaar_masked=active_party.aadhaar_masked,
                                        submitted_otp=otp_in,
                                        consent_accepted=consent
                                    )
                                    # Check if all completed
                                    all_signed = all(p.signing_status == "Signed" for p in parties)
                                    if all_signed:
                                        agr = session.query(Agreement).filter_by(id=wiz_data["agreement_id"]).first()
                                        agr.status = "Completed"
                                        session.commit()

                                    st.success("Digital signature successfully verified and embedded!")
                                    st.session_state["active_signing_party"] = None
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"eSign failed: {str(e)}")
                        with b_cancel:
                            if st.button("Cancel"):
                                st.session_state["active_signing_party"] = None
                                st.rerun()

            # If all parties signed
            all_signed = all(p.signing_status == "Signed" for p in parties)
            if all_signed:
                st.balloons()
                st.success("🎉 **ALL PARTIES HAVE SIGNED! Agreement has been cryptographically sealed.**")
                
                # Build PDF
                doc_engine = DocumentAssemblyEngine()
                clauses = get_default_clauses(wiz_data["clauses_toggles"])
                pdf_bytes = doc_engine.generate_pdf_agreement(
                    agreement_data={
                        "property_address": f"{wiz_data['property']['premises_name']}, {wiz_data['property']['address']}",
                        "monthly_rent": wiz_data["commercials"]["monthly_rent"],
                        "security_deposit": wiz_data["commercials"]["security_deposit"],
                        "lease_months": wiz_data["commercials"]["lease_months"],
                        "clauses": clauses
                    },
                    parties=[{"name": p.full_name, "type": p.party_type, "phone": p.phone, "email": p.email, "aadhaar_masked": p.aadhaar_masked} for p in parties],
                    estamp={"certificate_number": wiz_data.get("estamp_cert_number", "IN-KA-001"), "stamp_amount": 100.0, "state_code": wiz_data["state_code"]},
                    signatures=[{"party_name": p.full_name, "party_type": p.party_type, "signature_hash": "a1b2c3d4e5f67890"} for p in parties]
                )

                st.download_button(
                    label="📥 Download Certified Stamped PDF with Section 65B Certificate",
                    data=pdf_bytes,
                    file_name=f"GoLegal_Contract_{wiz_data['agreement_id'][:8]}.pdf",
                    mime="application/pdf",
                    type="primary"
                )

                if st.button("Go to User Dashboard ➡️"):
                    st.session_state["active_tab"] = "Dashboard"
                    st.rerun()

        finally:
            session.close()
