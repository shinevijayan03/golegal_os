"""
AgentOS Mission Console & Durable Runtime View.
Enforces AOS-04, AOS-05, AOS-06, AOS-12, AOS-13, AT-04..AT-15.
"""
from __future__ import annotations
import json
import streamlit as st
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import (
    Mission, AgentDeployment, DocumentSource, SourceRevision, MissionTask
)
from golegal.agentos.runtime.engine import (
    MissionEngine, CollectionScopeDeniedError, PlanValidationError,
    STATE_AWAITING_SCOPE_APPROVAL, STATE_RUNNING, STATE_PAUSED, STATE_CANCELLED, STATE_DELIVERED
)
from golegal.agentos.runtime.budget import BudgetService, BudgetExceededError
from golegal.agentos.intelligence.brain import FixtureAgentBrain
from golegal.agentos.services.rbac_service import (
    ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN, normalize_role
)
from golegal.ui import components as c


def render_mission_view(session: Session, actor_context: dict) -> None:
    st.markdown("### 🚀 Mission Console & Durable Agent Runtime")
    c.notice(
        "<b>DURABLE ORCHESTRATION:</b> Long-running missions persist tasks, timers, and state across "
        "worker restarts. All actions are scoped to permitted source collections and bound by an atomic "
        "INR paise budget ledger.",
        tone="warn"
    )

    tenant_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = normalize_role(actor_context["role"])

    engine = MissionEngine(session)
    budget_svc = BudgetService(session)
    brain = FixtureAgentBrain(session)

    col_launch, col_runtime = st.columns([1.8, 2.2], gap="large")

    with col_launch:
        st.markdown("#### 1. Launch Constrained Mission")
        deployments = (
            session.query(AgentDeployment)
            .filter_by(tenant_id=tenant_id, state="ACTIVE")
            .all()
        )
        if not deployments:
            st.warning("No active deployments found. Please deploy an agent in the Agent Studio first.")
            return

        dep_options = {d.id: f"{d.definition.name} (v{d.definition_version})" for d in deployments}
        selected_dep_id = st.selectbox(
            "Select Active Deployment",
            options=list(dep_options.keys()),
            format_func=lambda k: dep_options[k],
            key="mis_dep_select"
        )
        selected_dep = next(d for d in deployments if d.id == selected_dep_id)

        goal = st.text_input(
            "Mission Goal",
            value="Examine 30 supplier NDAs for deviations from Playbook 2026-11; find confidentiality term, governing law, and indemnity issues.",
            key="mis_goal_input"
        )

        # Source Selection (PDFs & Synthetic GoLegal Contracts)
        sources = session.query(DocumentSource).filter_by(tenant_id=tenant_id).all()
        src_options = {f"src-{s.id}": f"{s.name} (Uploaded PDF)" for s in sources}
        # Add synthetic contract sources
        src_options["rev-ka-nda-001"] = "Acme Logistics vs Zenith Cloud (GoLegal Native NDA - Standard)"
        src_options["rev-ka-nda-deviated-002"] = "Acme Logistics vs Global Conglomerate (GoLegal Native NDA - Deviated)"

        selected_sources = st.multiselect(
            "Select Permitted Source Documents",
            options=list(src_options.keys()),
            default=["rev-ka-nda-001", "rev-ka-nda-deviated-002"],
            format_func=lambda k: src_options[k],
            key="mis_sources_select"
        )

        c1, c2 = st.columns(2)
        with c1:
            budget_inr = st.number_input("Budget Ceiling (₹ INR)", min_value=10, max_value=2000, value=250, key="mis_budget_inr")
        with c2:
            idemp_key = st.text_input("Idempotency Key", value="supplier-nda-batch-001", key="mis_idemp_key")

        can_launch = actor_role in (ROLE_MISSION_OPERATOR, ROLE_TENANT_ADMIN)
        if st.button("🚀 Launch Mission", type="primary", disabled=not can_launch, key="btn_launch_mission"):
            try:
                mission = engine.launch_mission(
                    tenant_id=tenant_id,
                    deployment_id=selected_dep.id,
                    goal=goal,
                    source_revision_ids=selected_sources,
                    budget_limit_minor=int(budget_inr * 100),
                    idempotency_key=idemp_key,
                    actor_id=actor_id,
                    actor_role=actor_role
                )
                st.session_state["active_mission_id"] = mission.id
                st.success(f"Mission launched successfully! ID: `{mission.id[:12]}...` (Status: `{mission.status}`)")
                st.rerun()
            except CollectionScopeDeniedError as cse:
                st.error(str(cse))
            except Exception as e:
                session.rollback()
                st.error(f"Launch failed: {e}")

    with col_runtime:
        st.markdown("#### 2. Durable Runtime & Task Board")
        missions = (
            session.query(Mission)
            .filter_by(tenant_id=tenant_id)
            .order_by(Mission.created_at.desc())
            .all()
        )
        if not missions:
            st.info("No missions launched yet. Launch one from the panel on the left.")
            return

        m_options = {m.id: f"{m.goal[:45]}... [{m.status}]" for m in missions}
        active_mid = st.session_state.get("active_mission_id", missions[0].id)
        if active_mid not in m_options:
            active_mid = missions[0].id

        chosen_mid = st.selectbox(
            "Select Mission to Inspect",
            options=list(m_options.keys()),
            format_func=lambda k: m_options[k],
            index=list(m_options.keys()).index(active_mid),
            key="mis_select"
        )
        st.session_state["active_mission_id"] = chosen_mid
        mission = next(m for m in missions if m.id == chosen_mid)

        # Budget Spending Summary
        budget_summary = budget_svc.get_mission_spending_summary(mission.id)
        spent_inr = budget_summary["settled_paise"] / 100
        reserved_inr = budget_summary["reserved_paise"] / 100
        limit_inr = budget_summary["budget_limit_paise"] / 100

        # Mission Header Box
        with st.container(border=True):
            h1, h2, h3 = st.columns(3)
            with h1:
                st.markdown(f"**Status:** {c.status_badge(mission.status)}", unsafe_allow_html=True)
                st.caption(f"ID: `{mission.id}`")
            with h2:
                st.markdown(f"**Budget Ceiling:** ₹{limit_inr:.2f}")
                st.caption(f"Settled: ₹{spent_inr:.2f} · Reserved: ₹{reserved_inr:.2f}")
            with h3:
                st.markdown(f"**Workflow ID:** `{mission.workflow_id[:16]}...`")
                st.caption(f"Sources: `{len(mission.inputs)}` documents")

        # Lifecycle Command Controls
        c_p, c_r, c_c, c_exec = st.columns(4)
        with c_p:
            if st.button("⏸️ Pause", disabled=(mission.status != STATE_RUNNING), key="btn_pause_m"):
                engine.pause_mission(mission.id, tenant_id, actor_id, actor_role)
                st.rerun()
        with c_r:
            if st.button("▶️ Resume", disabled=(mission.status != STATE_PAUSED), key="btn_resume_m"):
                engine.resume_mission(mission.id, tenant_id, actor_id, actor_role)
                st.rerun()
        with c_c:
            if st.button("🛑 Cancel", disabled=(mission.status in (STATE_CANCELLED, STATE_DELIVERED)), key="btn_cancel_m"):
                engine.cancel_mission(mission.id, tenant_id, actor_id, actor_role)
                st.rerun()
        with c_exec:
            can_investigate = (mission.status == STATE_RUNNING)
            if st.button("⚡ Run Tasks", type="primary", disabled=not can_investigate, key="btn_run_tasks"):
                try:
                    # Reserve budget before dispatch (AOS-13, AT-15)
                    res = budget_svc.reserve_budget(mission.id, estimated_cost_minor=3500)
                    
                    # Execute Investigation via Brain & GPU RAG
                    src_rev_ids = [inp.source_revision_id for inp in mission.inputs]
                    findings = brain.analyze_source_spans(
                        mission_id=mission.id,
                        tenant_id=tenant_id,
                        source_revision_ids=src_rev_ids,
                        playbook_version_id=mission.deployment.playbook_version_id
                    )
                    
                    # Mark tasks completed
                    for t in mission.tasks:
                        t.state = "COMPLETED"
                        t.attempt_count += 1

                    # Settle reservation
                    budget_svc.settle_reservation(res.reservation_id, actual_cost_minor=2800, tokens_in=1200, tokens_out=450)
                    mission.status = "AWAITING_REVIEW"
                    session.commit()
                    st.success(f"Investigation complete! {len(findings)} candidate findings generated. Transitioned to AWAITING_REVIEW.")
                    st.rerun()
                except BudgetExceededError as be:
                    st.error(str(be))
                except Exception as e:
                    session.rollback()
                    st.error(f"Task run failed: {e}")

        # Task Board
        st.markdown("##### Durable Activity Tasks")
        if not mission.tasks:
            if mission.status == STATE_AWAITING_SCOPE_APPROVAL:
                c.notice(
                    "<b>AWAITING SCOPE APPROVAL:</b> Tasks are pending human authorization. "
                    "Please navigate to the <b>Approvals Inbox</b> to review and approve the plan.",
                    tone="warn"
                )
            else:
                st.caption("No tasks scheduled yet.")
        else:
            for t in mission.tasks:
                badge_t = "gl-badge-approved" if t.state == "COMPLETED" else "gl-badge-review"
                with st.container(border=True):
                    tc1, tc2 = st.columns([3, 1])
                    with tc1:
                        st.markdown(f"**`{t.task_key}`** (`{t.skill_name}`)")
                        deps = json.loads(t.deps_json or "[]")
                        st.caption(f"Dependencies: {deps if deps else 'None'} · Attempts: `{t.attempt_count}`")
                    with tc2:
                        st.markdown(f"<span class='gl-badge {badge_t}'>{t.state}</span>", unsafe_allow_html=True)
