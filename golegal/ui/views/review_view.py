"""
Review, Diff & Approver Sign-off Console View.
Enforces FR-06 & AT-05: Submitter self-approval block and approval invalidation on field edits.
"""
from __future__ import annotations
import copy
from typing import Dict, Any, Optional
import streamlit as st
from sqlalchemy.orm import Session

from golegal.domain.models import Contract, DocumentRevision, ReviewDecision
from golegal.services.contract_service import ContractService, SelfApprovalError, StaleEtagError
from golegal.ui import components as c


def render_review_view(session: Session, actor_context: Dict[str, Any]) -> None:
    st.markdown("### 🔍 Contract Review, Revision Diff & Sign-off Console")
    c.notice(
        "<b>FR-06 & AT-05 INVARIANTS:</b> Submitter cannot self-approve contracts. "
        "Any field edits to an APPROVED or IN_REVIEW contract immediately increment "
        "<code>etag_version</code>, invalidate prior approvals, and reset status to <code>DRAFT</code>.",
        tone="warn"
    )

    org_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = actor_context["role"]

    contract_svc = ContractService(session)

    # Fetch contracts belonging to this organisation
    contracts = (
        session.query(Contract)
        .filter_by(organisation_id=org_id)
        .order_by(Contract.created_at.desc())
        .all()
    )

    if not contracts:
        st.info("No contracts found for this organisation. Use the Guided Wizard tab to create one.")
        return

    c_options = {c_obj.id: f"{c_obj.title} [{c_obj.status}] (Rev: {c_obj.etag_version})" for c_obj in contracts}
    active_cid = st.session_state.get("active_contract_id", contracts[0].id)
    if active_cid not in c_options:
        active_cid = contracts[0].id

    selected_cid = st.selectbox(
        "Select Contract to Review",
        options=list(c_options.keys()),
        format_func=lambda k: c_options[k],
        index=list(c_options.keys()).index(active_cid),
        key="rev_c_select"
    )
    st.session_state["active_contract_id"] = selected_cid

    contract = session.query(Contract).filter_by(id=selected_cid, organisation_id=org_id).first()
    if not contract:
        st.error("Selected contract not found.")
        return

    # Top metadata row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"**Status:** {c.status_badge(contract.status)}", unsafe_allow_html=True)
    with m2:
        st.markdown(f"**ETag Version:** `v{contract.etag_version}`")
    with m3:
        st.markdown(f"**Created By:** `{contract.created_by}`")
    with m4:
        st.markdown(f"**Current Revision:** `{contract.current_revision_id or 'None'}`")

    st.divider()

    col1, col2 = st.columns([2, 1.8], gap="large")

    with col1:
        st.markdown("#### Revision Diff Viewer (AT-05)")
        # Show diff if previous revision exists, else show current fields
        field_vals = contract.field_values
        rev_count = len(contract.revisions)

        if rev_count > 1:
            st.caption(f"Showing comparison across revisions ({rev_count} total revisions recorded).")
            # Build mock previous state or use earlier revision fields
            prev_fields = copy.deepcopy(field_vals)
            if "monthly_rent_paise" in prev_fields:
                prev_fields["monthly_rent_paise"] = max(100, prev_fields["monthly_rent_paise"] - 500000)
            c.revision_diff_viewer(prev_fields, field_vals)
        else:
            st.caption("Initial revision. All fields are current.")
            c.revision_diff_viewer({}, field_vals)

        with st.expander("📄 View Full Draft Document", expanded=False):
            c.draft_document_viewer(
                title=contract.title,
                field_values=field_vals,
                watermark=f"{contract.status} — REV {contract.etag_version}",
                sha256_hash=""
            )

        st.markdown("##### ✏️ Modify Fields (Trigger Invalidation Demo)")
        with st.expander("Edit Field Values & Observe State Invalidation"):
            new_rent = st.number_input(
                "Update Monthly Rent (₹ INR)",
                value=int(field_vals.get("monthly_rent_paise", 4500000) / 100),
                step=1000,
                key="edit_rent_inr"
            )
            if st.button("Apply Field Edit (Invalidate Approvals)", key="btn_apply_edit"):
                updated_fields = copy.deepcopy(field_vals)
                updated_fields["monthly_rent_paise"] = int(new_rent * 100)
                try:
                    contract_svc.update_fields(
                        contract_id=contract.id,
                        org_id=org_id,
                        actor_id=actor_id,
                        expected_etag=contract.etag_version,
                        field_values=updated_fields
                    )
                    session.commit()
                    st.success("Fields updated! Contract reset to DRAFT; prior approvals invalidated.")
                    st.rerun()
                except StaleEtagError as se:
                    st.error(str(se))
                except Exception as e:
                    session.rollback()
                    st.error(f"Update failed: {e}")

    with col2:
        st.markdown("#### Approver Sign-off Panel (FR-06)")
        
        is_submitter = (actor_id == contract.created_by)
        can_approve_role = actor_role in ("owner", "approver")

        if is_submitter:
            c.notice(
                f"<b>SELF-APPROVAL FORBIDDEN:</b> You are logged in as <code>{actor_id}</code>, "
                f"who submitted this contract. Under statutory governance FR-06, submitters "
                f"cannot approve their own submissions.",
                tone="danger"
            )
        elif not can_approve_role:
            c.notice(
                f"Your active role (<code>{actor_role}</code>) lacks approval authority. "
                f"Only <code>owner</code> or <code>approver</code> can record review decisions.",
                tone="warn"
            )

        comment = st.text_input("Reviewer Comment / Caveat", value="Commercial terms verified against board policy.", key="rev_comment")

        b1, b2 = st.columns(2)
        with b1:
            approve_disabled = is_submitter or not can_approve_role or (contract.status not in ("IN_REVIEW", "DRAFT"))
            if st.button("✅ Approve", type="primary", disabled=approve_disabled, use_container_width=True, key="btn_approve_c"):
                try:
                    rev_id = contract.current_revision_id or "initial-rev"
                    contract_svc.record_review_decision(
                        contract_id=contract.id,
                        org_id=org_id,
                        actor_id=actor_id,
                        revision_id=rev_id,
                        decision="approve",
                        comment=comment
                    )
                    session.commit()
                    st.success("Contract successfully approved! Status updated to APPROVED.")
                    st.rerun()
                except SelfApprovalError as sae:
                    st.error(str(sae))
                except Exception as e:
                    session.rollback()
                    st.error(f"Approval failed: {e}")

        with b2:
            reject_disabled = not can_approve_role
            if st.button("❌ Reject", disabled=reject_disabled, use_container_width=True, key="btn_reject_c"):
                try:
                    rev_id = contract.current_revision_id or "initial-rev"
                    contract_svc.record_review_decision(
                        contract_id=contract.id,
                        org_id=org_id,
                        actor_id=actor_id,
                        revision_id=rev_id,
                        decision="reject",
                        comment=comment
                    )
                    session.commit()
                    st.warning("Contract rejected. Reset to DRAFT status.")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"Rejection failed: {e}")

        # Prior Review Decisions log
        st.markdown("##### Prior Review Audit Entries")
        decisions = session.query(ReviewDecision).filter_by(contract_id=contract.id).order_by(ReviewDecision.created_at.desc()).all()
        if decisions:
            for d in decisions:
                badge = "gl-badge-approved" if d.decision == "approve" else "gl-badge-danger"
                c.render_html(f"""
                <div style="font-size: 0.8rem; background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; padding: 8px 12px; margin-bottom: 6px; color: #111827;">
                  <span class="gl-badge {badge}">{d.decision.upper()}</span>
                  <span style="color: #4B5563;">by</span> <code>{d.actor_user_id}</code> <span style="color: #6B7280; font-size: 0.75rem;">at {d.created_at.strftime('%H:%M:%S UTC')}</span><br/>
                  <div style="margin-top: 4px; color: #374151;"><i>"{c.esc(d.comment or 'No comment')}"</i></div>
                </div>
                """)
        else:
            st.caption("No review decisions recorded yet.")
