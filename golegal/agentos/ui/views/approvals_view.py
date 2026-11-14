"""
AgentOS Approvals Inbox: Scope Approvals, Finding Reviews & Human Governance.
Enforces AOS-07, AT-07..AT-10, AT-25.
"""
from __future__ import annotations
import json
import streamlit as st
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import Approval, Mission, MissionPlan
from golegal.agentos.runtime.engine import (
    MissionEngine, ApprovalStaleError, ApprovalConflictError
)
from golegal.agentos.services.rbac_service import (
    ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, ROLE_LEGAL_REVIEWER, normalize_role
)
from golegal.ui import components as c


def render_approvals_view(session: Session, actor_context: dict) -> None:
    st.markdown("### 📥 Approvals Inbox & Human-in-the-Loop Governance")
    c.notice(
        "<b>MANDATORY SCOPE APPROVAL:</b> In accordance with Section 3 & AT-07, an agent cannot run any "
        "investigative tool calls until an authorized operator reviews and approves the exact proposed plan hash. "
        "Models are never approvers.",
        tone="warn"
    )

    tenant_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = normalize_role(actor_context["role"])

    engine = MissionEngine(session)

    # Fetch pending approvals for this tenant
    missions = session.query(Mission).filter_by(tenant_id=tenant_id).all()
    m_ids = [m.id for m in missions]

    pending_approvals = (
        session.query(Approval)
        .filter(Approval.mission_id.in_(m_ids), Approval.state == "PENDING")
        .order_by(Approval.created_at.asc())
        .all()
    )

    decided_approvals = (
        session.query(Approval)
        .filter(Approval.mission_id.in_(m_ids), Approval.state != "PENDING")
        .order_by(Approval.decided_at.desc())
        .all()
    )

    tab_pending, tab_history = st.tabs([
        f"⏳ Pending Approvals ({len(pending_approvals)})",
        f"📜 Decision History ({len(decided_approvals)})"
    ])

    with tab_pending:
        if not pending_approvals:
            st.info("Zero pending approvals in inbox. All proposed plans and gates have been reviewed.")
        else:
            for app in pending_approvals:
                mission = session.query(Mission).filter_by(id=app.mission_id).first()
                latest_plan = (
                    session.query(MissionPlan)
                    .filter_by(mission_id=app.mission_id)
                    .order_by(MissionPlan.version.desc())
                    .first()
                )

                with st.container(border=True):
                    st.markdown(f"**Approval Type:** `{app.kind}` · **Requested Role:** `{app.requested_role}`")
                    st.markdown(f"**Mission Goal:** {mission.goal if mission else 'Unknown'}")
                    st.caption(f"Approval ID: `{app.id}` · Created: {app.created_at.strftime('%Y-%m-%d %H:%M UTC')} · Expires: {app.expires_at.strftime('%Y-%m-%d %H:%M UTC')}")
                    
                    st.html(
                        '<div style="background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; padding: 10px; margin: 8px 0; font-size: 0.82rem;">'
                        '<span style="color: #D97706; font-weight: bold;">PROPOSED PLAN SHA-256 HASH:</span><br/>'
                        f'<code style="word-break: break-all; color: #047857;">{app.subject_sha256}</code>'
                        '</div>'
                    )

                    if latest_plan:
                        with st.expander("🔍 Inspect Proposed Tasks & Rationale", expanded=True):
                            tasks_data = json.loads(latest_plan.plan_json)
                            for idx, t in enumerate(tasks_data, 1):
                                st.markdown(f"**{idx}. `{t['task_key']}` [{t['skill'].upper()}]:** {t['objective']}")
                                st.caption(f"Dependencies: {t.get('depends_on', [])} · Rationale: _{t.get('rationale')}_")

                    reason = st.text_input("Approver Rationale / Notes", value="Plan verified against authorized supplier NDA scope.", key=f"reason_{app.id}")

                    can_approve = actor_role in (ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN)
                    if not can_approve:
                        st.caption("🔒 Active role lacks approval authority for this gate. Requires MISSION_OPERATOR or TENANT_ADMIN.")

                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("✅ Approve Plan Scope", type="primary", disabled=not can_approve, use_container_width=True, key=f"btn_app_{app.id}"):
                            try:
                                engine.decide_scope_approval(
                                    mission_id=app.mission_id,
                                    tenant_id=tenant_id,
                                    approval_id=app.id,
                                    decision="APPROVE",
                                    subject_sha256=app.subject_sha256,
                                    actor_id=actor_id,
                                    actor_role=actor_role,
                                    reason=reason
                                )
                                st.success("Plan scope approved! Mission transitioned to RUNNING and tasks scheduled.")
                                st.rerun()
                            except (ApprovalStaleError, ApprovalConflictError) as ae:
                                st.error(str(ae))
                            except Exception as e:
                                session.rollback()
                                st.error(f"Approval failed: {e}")

                    with b2:
                        if st.button("❌ Reject Plan", disabled=not can_approve, use_container_width=True, key=f"btn_rej_{app.id}"):
                            try:
                                engine.decide_scope_approval(
                                    mission_id=app.mission_id,
                                    tenant_id=tenant_id,
                                    approval_id=app.id,
                                    decision="REJECT",
                                    subject_sha256=app.subject_sha256,
                                    actor_id=actor_id,
                                    actor_role=actor_role,
                                    reason=reason
                                )
                                st.warning("Plan scope rejected. Mission cancelled.")
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Rejection failed: {e}")

                    with b3:
                        if st.button("🔄 Request Changes", disabled=not can_approve, use_container_width=True, key=f"btn_chg_{app.id}"):
                            try:
                                engine.decide_scope_approval(
                                    mission_id=app.mission_id,
                                    tenant_id=tenant_id,
                                    approval_id=app.id,
                                    decision="REQUEST_CHANGES",
                                    subject_sha256=app.subject_sha256,
                                    actor_id=actor_id,
                                    actor_role=actor_role,
                                    reason=reason
                                )
                                st.info("Changes requested. Reset to PLANNING.")
                                st.rerun()
                            except Exception as e:
                                session.rollback()
                                st.error(f"Action failed: {e}")

    with tab_history:
        st.markdown("#### Prior Human Decisions Log")
        if not decided_approvals:
            st.caption("No prior decisions recorded yet.")
        else:
            for dec in decided_approvals:
                badge_cls = "gl-badge-approved" if dec.state == "APPROVED" else ("gl-badge-danger" if dec.state == "REJECTED" else "gl-badge-draft")
                with st.container(border=True):
                    st.markdown(f"<span class='gl-badge {badge_cls}'>{dec.state}</span> · **`{dec.kind}`**", unsafe_allow_html=True)
                    st.caption(f"Decided by `{dec.actor_id}` at {dec.decided_at.strftime('%Y-%m-%d %H:%M UTC') if dec.decided_at else '—'}")
                    st.markdown(f"**Rationale:** _{dec.reason or 'No comment'}_")
                    st.caption(f"Plan Hash: `{(dec.subject_sha256 or '')[:24]}...`")
