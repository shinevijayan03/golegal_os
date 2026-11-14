"""
Guided Contract Wizard & Live Document Assembly View.
Enforces FR-03, FR-04, FR-05, AT-03, AT-04.
"""
from __future__ import annotations
import base64
from datetime import date, timedelta
from typing import Dict, Any, Optional
import streamlit as st
from sqlalchemy.orm import Session

from golegal.domain.models import Contract
from golegal.services.catalog_service import CatalogService
from golegal.services.contract_service import ContractService, ContractValidationError
from golegal.services.document_service import DocumentService
from golegal.ui import components as c


def render_wizard_view(session: Session, actor_context: Dict[str, Any]) -> None:
    st.markdown("### 📝 Guided Contract Wizard & Live Document Assembly")
    c.notice(
        "<b>NATIVE TYPED DATA BYPASS:</b> As mandated by Section 1 & AT-03, structured fields entered "
        "here bypass OCR and LLM extraction entirely. Real-time validation executes on every field change.",
        tone="warn"
    )

    org_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]

    catalog_svc = CatalogService(session)
    catalog_svc.seed_demo_templates_if_missing()
    templates = catalog_svc.list_templates()

    contract_svc = ContractService(session)
    doc_svc = DocumentService()

    col_left, col_right = st.columns([1.8, 2.2], gap="large")

    with col_left:
        st.markdown("#### Contract Configuration")
        tpl_options = {t.id: f"{t.agreement_type} ({t.jurisdiction_code}) - v{t.version}" for t in templates}
        selected_tpl_id = st.selectbox(
            "Select Legal Template",
            options=list(tpl_options.keys()),
            format_func=lambda k: tpl_options[k],
            key="wiz_tpl_select"
        )

        title = st.text_input(
            "Contract Title",
            value="Residential Lease Agreement - Koramangala Bangalore",
            key="wiz_title"
        )

        c1, c2 = st.columns(2)
        with c1:
            party_a = st.text_input("First Party (Landlord / Disclosing)", value="Bengaluru Heights Properties", key="wiz_pa")
        with c2:
            party_b = st.text_input("Second Party (Tenant / Receiving)", value="Acme Logistics Pvt. Ltd.", key="wiz_pb")

        d1, d2 = st.columns(2)
        with d1:
            start_dt = st.date_input("Commencement Date", value=date.today(), key="wiz_start_dt")
        with d2:
            end_dt = st.date_input("Expiration Date", value=date.today() + timedelta(days=364), key="wiz_end_dt")

        m1, m2 = st.columns(2)
        with m1:
            rent_inr = st.number_input("Monthly Rent (₹ INR)", min_value=1, value=45000, step=1000, key="wiz_rent")
        with m2:
            deposit_inr = st.number_input("Security Deposit (₹ INR)", min_value=0, value=200000, step=5000, key="wiz_deposit")

        custom_covenants = st.text_area(
            "Custom Covenants / Special Conditions",
            value="Standard residential lease rules apply. Tenant shall maintain peaceful possession.",
            help="Test PII detection: Type an unmasked 12-digit Aadhaar number like 4912 3456 7890 to trigger RULE-PII-01.",
            key="wiz_covenants"
        )

        field_values = {
            "title": title,
            "lessor": party_a,
            "lessee": party_b,
            "start_date": str(start_dt),
            "end_date": str(end_dt),
            "monthly_rent_paise": int(rent_inr * 100),
            "security_deposit_paise": int(deposit_inr * 100),
            "custom_covenants": custom_covenants,
        }

        # Real-time deterministic validation feedback
        validation_error: Optional[str] = None
        try:
            contract_svc.validate_fields(selected_tpl_id, field_values)
            st.success("✅ Field values conform strictly to statutory schema.")
        except ContractValidationError as cve:
            validation_error = str(cve)
            st.error(f"❌ Validation Error: {validation_error}")

        b1, b2 = st.columns(2)
        with b1:
            save_clicked = st.button("💾 Save as Draft", type="primary", use_container_width=True, key="btn_save_draft")
        with b2:
            submit_clicked = st.button("📤 Submit for Review", use_container_width=True, key="btn_submit_review")

        if save_clicked:
            if validation_error:
                st.error("Cannot save invalid contract. Please fix validation errors above.")
            else:
                try:
                    c_record = contract_svc.create_contract(
                        org_id=org_id,
                        actor_id=actor_id,
                        template_version_id=selected_tpl_id,
                        title=title,
                        field_values=field_values
                    )
                    session.commit()
                    st.session_state["active_contract_id"] = c_record.id
                    st.success(f"Draft contract created successfully! ID: `{c_record.id}`")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"Failed to create contract: {e}")

        if submit_clicked:
            if validation_error:
                st.error("Cannot submit invalid contract. Please fix validation errors above.")
            else:
                try:
                    c_record = contract_svc.create_contract(
                        org_id=org_id,
                        actor_id=actor_id,
                        template_version_id=selected_tpl_id,
                        title=title,
                        field_values=field_values
                    )
                    session.commit()
                    rev = contract_svc.submit_for_review(c_record.id, org_id, actor_id)
                    session.commit()
                    st.session_state["active_contract_id"] = c_record.id
                    st.success(f"Submitted for review! Revision {rev.revision_no} created (Status: IN_REVIEW).")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"Submission failed: {e}")

    with col_right:
        st.markdown("#### Live Document Assembly & Watermarked Preview")
        
        # Render PDF buffer with watermark
        pdf_bytes = doc_svc.render_pdf(
            contract_id=st.session_state.get("active_contract_id", "DRAFT-PREVIEW"),
            org_id=org_id,
            field_values=field_values,
            watermark="DRAFT — NOT EXECUTED"
        )
        pdf_sha256 = doc_svc.compute_sha256(pdf_bytes)

        c.draft_document_viewer(
            title=title,
            field_values=field_values,
            watermark="DRAFT — NOT EXECUTED",
            sha256_hash=pdf_sha256,
            pdf_bytes=pdf_bytes
        )

        # Download button
        st.download_button(
            label="📥 Download Watermarked Draft PDF",
            data=pdf_bytes,
            file_name="draft_contract_preview.pdf",
            mime="application/pdf",
            use_container_width=True
        )

        # Deterministic Checklist Findings Preview
        st.markdown("##### 🔍 Deterministic Lawyer-Authored Checklist (FR-05)")
        active_cid = st.session_state.get("active_contract_id")
        if active_cid:
            try:
                findings = contract_svc.evaluate_checklist(active_cid, org_id)
                if findings:
                    for f in findings:
                        tone = "danger" if f.severity == "critical" else "warn"
                        c.notice(f"<b>[{f.rule_id}] {f.severity.upper()}:</b> {f.message} (Location: <code>{f.location}</code>)", tone=tone)
                else:
                    st.markdown("<span style='color: #047857; font-weight: 500;'>✅ All deterministic statutory rules passed. Zero open findings.</span>", unsafe_allow_html=True)
            except Exception:
                st.session_state["active_contract_id"] = None
                st.info("Save draft or submit to evaluate live deterministic checklist against the repository.")
        else:
            st.info("Save draft or submit to evaluate live deterministic checklist against the repository.")
