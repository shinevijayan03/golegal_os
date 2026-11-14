"""
Pre-Execution Gate, e-Stamping & Mock eSign Ceremony Console.
Enforces FR-07, FR-08, AT-02, AT-06, AT-07, AT-17.
"""
from __future__ import annotations
import uuid
from typing import Dict, Any, Optional
import streamlit as st
from sqlalchemy.orm import Session

from golegal.domain.models import Contract, StampRecord, ExecutionRequest
from golegal.services.contract_service import ContractService
from golegal.services.catalog_service import CatalogService, LegalEligibilityError
from golegal.services.stamping_service import StampingService, StampGateError
from golegal.services.provider_service import ProviderService
from golegal.ui import components as c


def render_execution_view(session: Session, actor_context: Dict[str, Any]) -> None:
    st.markdown("### ⚖️ Pre-Execution Verification, e-Stamping & Mock eSign Ceremony")
    c.notice(
        "<b>STATUTORY EXECUTION GATES:</b> Execution is blocked if template eligibility is unverified "
        "(AT-02) or mandatory state stamp duty is unverified (AT-06). "
        "Mock provider executions strictly display the <code>MOCK_COMPLETED</code> badge (AT-07).",
        tone="warn"
    )

    org_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = actor_context["role"]

    contract_svc = ContractService(session)
    catalog_svc = CatalogService(session)
    stamping_svc = StampingService(session)
    provider_svc = ProviderService(session)

    contracts = (
        session.query(Contract)
        .filter_by(organisation_id=org_id)
        .order_by(Contract.created_at.desc())
        .all()
    )

    if not contracts:
        st.info("No contracts found for this organisation. Create one via Guided Wizard first.")
        return

    c_options = {c_obj.id: f"{c_obj.title} [{c_obj.status}] (Rev: {c_obj.etag_version})" for c_obj in contracts}
    active_cid = st.session_state.get("active_contract_id", contracts[0].id)
    if active_cid not in c_options:
        active_cid = contracts[0].id

    selected_cid = st.selectbox(
        "Select Contract for Pre-Execution Verification",
        options=list(c_options.keys()),
        format_func=lambda k: c_options[k],
        index=list(c_options.keys()).index(active_cid),
        key="exec_c_select"
    )
    st.session_state["active_contract_id"] = selected_cid

    contract = session.query(Contract).filter_by(id=selected_cid, organisation_id=org_id).first()
    if not contract:
        st.error("Contract not found.")
        return

    # Check eligibility rule
    tpl = catalog_svc.get_template(contract.template_version_id)
    rule = tpl.eligibility_rules[0] if tpl.eligibility_rules else None
    stamp_rec = stamping_svc.get_stamp_record(contract.id)

    col1, col2 = st.columns([2, 1.8], gap="large")

    with col1:
        st.markdown("#### Pre-Execution Quality & Statutory Gates")
        
        # Gate 1: Template Eligibility (AT-02)
        is_mode_allowed = rule and rule.execution_mode == "provider_allowed"
        if is_mode_allowed:
            st.markdown("✅ **Statutory Template Eligibility:** `provider_allowed` (Authorized for Execution)")
        else:
            mode_str = rule.execution_mode if rule else "unknown"
            c.notice(
                f"<b>GATE 1 BLOCKED (AT-02):</b> Template <code>{tpl.id}</code> is currently "
                f"<code>{mode_str.upper()}</code>. Indian statutory compliance prohibits signing unapproved templates.",
                tone="danger"
            )
            if actor_role in ("owner", "legal_admin"):
                if st.button("Authorize Template Execution (Legal Admin Override)", key="btn_auth_tpl"):
                    if rule:
                        rule.execution_mode = "provider_allowed"
                        session.commit()
                        st.success("Template execution authorized!")
                        st.rerun()

        # Gate 2: Stamping Gate (AT-06)
        is_stamp_verified = stamp_rec and stamp_rec.status == "verified"
        if is_stamp_verified:
            st.markdown(f"✅ **State Stamp Duty:** `VERIFIED` (Amount: ₹{stamp_rec.amount_paise / 100:.2f} · Cert: `{stamp_rec.receipt_object_key}`)")
        else:
            c.notice(
                f"<b>GATE 2 BLOCKED (AT-06):</b> Karnataka State Stamp Duty is "
                f"<code>{stamp_rec.status.upper() if stamp_rec else 'UNVERIFIED'}</code>. "
                "System requires verified stamp certificate before advancing to execution.",
                tone="danger"
            )

        # Gate 3: Contract Approval Status
        is_approved = contract.status in ("APPROVED", "READY_FOR_EXECUTION", "MOCK_COMPLETED")
        if is_approved:
            st.markdown(f"✅ **Internal Approval Status:** `{contract.status}`")
        else:
            c.notice(
                f"<b>GATE 3 BLOCKED:</b> Contract status is <code>{contract.status}</code>. "
                "Approver must approve contract in the Review Console before execution.",
                tone="danger"
            )

        st.divider()
        st.markdown("##### 🏛️ Record Karnataka e-Stamp Certificate")
        with st.form("stamp_duty_form"):
            s_cert = st.text_input("e-Stamp Certificate Number", value="IN-KA991203948123A", key="stamp_cert")
            s_amt = st.number_input("Statutory Duty Paid (₹ INR)", min_value=100, value=500, step=100, key="stamp_amt")
            s_jur = st.selectbox("State Jurisdiction", ["KA", "MH", "DL", "TN"], key="stamp_jur")
            submit_stamp = st.form_submit_button("Verify & Attach e-Stamp Certificate")
            if submit_stamp:
                stamping_svc.record_verified_stamp(
                    contract_id=contract.id,
                    amount_paise=int(s_amt * 100),
                    cert_num=s_cert,
                    verified_by=actor_id,
                    jurisdiction=s_jur
                )
                session.commit()
                st.success("Stamp certificate verified and attached to contract record!")
                st.rerun()

    with col2:
        st.markdown("#### Execution Ceremony & Provider Outbox")
        st.markdown(f"**Contract Status:** {c.status_badge(contract.status)}", unsafe_allow_html=True)

        can_advance_to_ready = is_mode_allowed and is_stamp_verified and contract.status == "APPROVED"
        if st.button("🚀 Advance to READY_FOR_EXECUTION", disabled=not can_advance_to_ready, use_container_width=True, key="btn_ready_exec"):
            try:
                contract_svc.prepare_execution(contract.id, org_id, actor_id)
                session.commit()
                st.success("Contract advanced to READY_FOR_EXECUTION!")
                st.rerun()
            except (LegalEligibilityError, StampGateError) as ge:
                st.error(str(ge))
            except Exception as e:
                session.rollback()
                st.error(f"Failed to advance: {e}")

        st.divider()
        st.markdown("##### ✍️ Multi-Party Mock eSign Ceremony (AT-07)")
        st.caption("Executes simulated Aadhaar / IT Act compliant digital signature with HMAC webhook verification.")

        can_mock_esign = contract.status in ("READY_FOR_EXECUTION", "APPROVED") and is_mode_allowed and is_stamp_verified
        idemp_key = f"idemp-{contract.id}-{contract.etag_version}"

        if st.button("🔏 Sign with Mock eSign Provider", type="primary", disabled=not can_mock_esign, use_container_width=True, key="btn_mock_esign"):
            try:
                req = provider_svc.request_mock_esign(
                    contract_id=contract.id,
                    org_id=org_id,
                    actor_id=actor_id,
                    revision_id=contract.current_revision_id or "rev-1",
                    idempotency_key=idemp_key
                )
                contract.status = "MOCK_COMPLETED"
                session.commit()
                st.success("Mock eSign ceremony completed successfully!")
                st.rerun()
            except Exception as e:
                session.rollback()
                st.error(f"Mock execution failed: {e}")

        # Display execution records
        exec_reqs = session.query(ExecutionRequest).filter_by(contract_id=contract.id).all()
        if exec_reqs:
            st.markdown("##### Execution Records (AT-07 & AT-17)")
            for r in exec_reqs:
                c.render_html(f"""
                <div style="background: #FFFFFF; border: 1px solid #FECACA; border-left: 4px solid #D32F2F; border-radius: 8px; padding: 12px; margin-bottom: 8px; font-size: 0.85rem; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                  <span class="gl-badge gl-badge-mock">{r.status}</span>
                  <span style="color: #C2410C; margin-left: 8px; font-weight: 600;">Mode: <b>{r.mode.upper()}</b></span><br/>
                  <span style="font-size: 0.78rem; color: #4B5563;">Provider Request ID: <code>{r.provider_request_id}</code></span><br/>
                  <span style="font-size: 0.78rem; color: #4B5563;">Idempotency Key: <code>{r.idempotency_key}</code></span><br/>
                  <span style="font-size: 0.78rem; color: #047857; font-weight: 500;">Signed Digest: <code>{r.signed_sha256[:24]}...</code></span>
                </div>
                """)
        else:
            st.caption("No mock execution requests logged for this contract.")
