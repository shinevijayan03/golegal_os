"""
AgentOS Studio View: Pack Catalog, Draft Agent Config & Admin Deployments.
Enforces AOS-01, AOS-02, AOS-03, AT-01..AT-03.
"""
from __future__ import annotations
import json
import streamlit as st
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import AgentPack, AgentDefinition, AgentDeployment, ToolGrant
from golegal.agentos.services.studio_service import StudioService, ConfigurationValidationError
from golegal.agentos.services.rbac_service import (
    ROLE_TENANT_ADMIN, ROLE_AGENT_BUILDER, normalize_role
)
from golegal.ui import components as c


def render_studio_view(session: Session, actor_context: dict) -> None:
    st.markdown("### 🤖 Agent Studio: Catalog, Configuration & Immutable Deployments")
    c.notice(
        "<b>GOVERNED AGENT PACKS:</b> In accordance with Section 1.1 of the PRD, AgentOS prohibits "
        "arbitrary code execution or unreviewed shared agents. Agents must be created from an approved "
        "pack and deployed immutably under Tenant Admin sign-off.",
        tone="warn"
    )

    tenant_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = normalize_role(actor_context["role"])

    studio_svc = StudioService(session)
    pack = studio_svc.seed_default_pack_if_missing()

    tab_create, tab_definitions, tab_deployments = st.tabs([
        "➕ Configure Draft Agent",
        "📋 Agent Definitions & Version Diff",
        "🚀 Active Deployments & Tool Grants"
    ])

    with tab_create:
        col1, col2 = st.columns([1.8, 2.2], gap="large")
        with col1:
            st.markdown("#### 1. Select Published Pack")
            with st.container(border=True):
                st.markdown(f"**Pack Name:** `{pack.name}`")
                st.markdown(f"**Key & Version:** `{pack.key}` (v{pack.pack_version})")
                st.markdown(f"**Policy Version:** `{pack.system_policy_version}`")
                st.caption(pack.description)
                capabilities = json.loads(pack.capabilities)
                st.markdown("**Allowed Skills:** " + " · ".join(f"`{sk}`" for sk in capabilities))

            agent_name = st.text_input("Agent Display Name", value="Contract Intelligence Agent - Vendor NDAs", key="st_agent_name")
            goal_template = st.text_area(
                "Primary Goal Template",
                value="Examine supplier non-disclosure agreements against Playbook 2026-11; identify deviations in confidentiality duration, governing law, and uncapped indemnities.",
                height=100,
                key="st_goal_template"
            )

        with col2:
            st.markdown("#### 2. Skill Constraints & Budget Ceiling")
            skills_selected = st.multiselect(
                "Authorized Skills",
                options=capabilities,
                default=["search", "extract", "compare", "verify", "draft"],
                key="st_skills_multiselect"
            )

            c1, c2 = st.columns(2)
            with c1:
                max_files = st.number_input("Max Documents / Mission", min_value=1, max_value=50, value=30, key="st_max_files")
                max_steps = st.number_input("Max Planner Steps", min_value=5, max_value=30, value=25, key="st_max_steps")
            with c2:
                max_tools = st.number_input("Max Tool Invocations", min_value=10, max_value=200, value=150, key="st_max_tools")
                budget_ceiling_inr = st.number_input("Budget Ceiling (₹ INR)", min_value=1, max_value=5000, value=250, key="st_budget_ceiling")

            target_categories = st.multiselect(
                "Target Playbook Deviation Categories",
                options=["confidentiality_duration", "governing_law", "indemnity", "non_solicitation", "termination"],
                default=["confidentiality_duration", "governing_law", "indemnity"],
                key="st_target_categories"
            )

            can_build = actor_role in (ROLE_AGENT_BUILDER, ROLE_TENANT_ADMIN)
            if not can_build:
                st.caption("🔒 Active role lacks Agent Builder authority. Only Builder or Admin can create drafts.")

            if st.button("💾 Save Draft Agent Definition", type="primary", disabled=not can_build, key="btn_save_agent_draft"):
                config = {
                    "allowed_skills": skills_selected,
                    "max_files": int(max_files),
                    "max_tool_calls": int(max_tools),
                    "max_steps": int(max_steps),
                    "budget_ceiling_minor": int(budget_ceiling_inr * 100),  # In paise
                    "allowed_playbooks": ["playbook_nda_2026_11"],
                    "target_clause_categories": target_categories
                }
                try:
                    definition = studio_svc.create_agent_definition(
                        tenant_id=tenant_id,
                        name=agent_name,
                        goal_template=goal_template,
                        config=config,
                        actor_id=actor_id,
                        actor_role=actor_role
                    )
                    st.success(f"Draft definition created! ID: `{definition.id[:12]}...` (Version {definition.version})")
                    st.rerun()
                except ConfigurationValidationError as ve:
                    st.error(str(ve))
                except Exception as e:
                    session.rollback()
                    st.error(f"Failed to create definition: {e}")

    with tab_definitions:
        st.markdown("#### Versioned Agent Definitions")
        definitions = (
            session.query(AgentDefinition)
            .filter_by(tenant_id=tenant_id)
            .order_by(AgentDefinition.version.desc())
            .all()
        )
        if not definitions:
            st.info("No agent definitions created yet. Use the Configure tab above.")
        else:
            for d in definitions:
                with st.container(border=True):
                    dc1, dc2, dc3 = st.columns([2.5, 1.5, 1.5])
                    with dc1:
                        st.markdown(f"**{d.name}** `[v{d.version}]`")
                        st.caption(f"ID: `{d.id}` · Family: `{d.family_id[:8]}...` · Created by: `{d.created_by}`")
                        st.markdown(f"<span style='font-size:0.8rem; color:#4B5563;'>Goal: {d.goal_template[:90]}...</span>", unsafe_allow_html=True)
                    with dc2:
                        badge_cls = "gl-badge-approved" if d.status == "APPROVED" else "gl-badge-draft"
                        st.markdown(f"Status: <span class='gl-badge {badge_cls}'>{d.status}</span>", unsafe_allow_html=True)
                        st.markdown(f"<span style='font-size:0.75rem; color:#6B7280;'>SHA-256: <code>{d.content_sha256[:16]}...</code></span>", unsafe_allow_html=True)
                    with dc3:
                        is_admin = (actor_role == ROLE_TENANT_ADMIN)
                        if d.status == "DRAFT":
                            if st.button(f"🚀 Deploy v{d.version}", key=f"btn_deploy_{d.id}", disabled=not is_admin, type="primary"):
                                try:
                                    dep = studio_svc.approve_deployment(
                                        tenant_id=tenant_id,
                                        definition_id=d.id,
                                        playbook_version_id="playbook_nda_2026_11",
                                        allowed_collection_ids=["col_supplier_ndas", "col_default"],
                                        actor_id=actor_id,
                                        actor_role=actor_role
                                    )
                                    st.success(f"Deployment approved! ID: `{dep.id[:12]}...` (ACTIVE)")
                                    st.rerun()
                                except Exception as e:
                                    session.rollback()
                                    st.error(f"Deployment failed: {e}")
                        else:
                            st.markdown("✅ Deployed")

    with tab_deployments:
        st.markdown("#### Active Deployments & Authorized Tool Grants")
        deployments = (
            session.query(AgentDeployment)
            .filter_by(tenant_id=tenant_id)
            .order_by(AgentDeployment.approved_at.desc())
            .all()
        )
        if not deployments:
            st.info("No active deployments. Deploy an approved agent definition to enable mission launching.")
        else:
            for dep in deployments:
                with st.container(border=True):
                    st.markdown(f"**Deployment ID:** `{dep.id}` · **State:** <span class='gl-badge gl-badge-approved'>{dep.state}</span>", unsafe_allow_html=True)
                    st.caption(f"Definition: `{dep.definition.name}` (v{dep.definition_version}) · Approved by: `{dep.approved_by}` at {dep.approved_at.strftime('%Y-%m-%d %H:%M UTC')}")
                    
                    grants = session.query(ToolGrant).filter_by(deployment_id=dep.id).all()
                    g_names = [f"`{g.tool_name}` ({g.side_effect_class})" for g in grants if g.enabled]
                    st.markdown(f"**Tool Grants ({len(g_names)}):** " + " · ".join(g_names))
