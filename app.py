"""
GoLegal AgentOS v1.0 — Pure Python 3.12+ & Streamlit Modular Monolith.
Supervised Legal Contract Operations, Durable Agent Runtime & Local GPU Acceleration.
Executive Crimson Red (#D32F2F) & Vibrant Orange (#FF5722) Light Design System (WCAG 2.2 AA).
"""
from __future__ import annotations
import streamlit as st

st.set_page_config(
    page_title="GoLegal AgentOS v1.0 · Supervised Legal Contract Operations",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

from golegal.db.session import init_db, SessionLocal
from golegal.db.seed import seed_demo_tenants_and_templates
from golegal.ui.theme import inject_theme
from golegal.ui import components as c
from golegal.agentos.ui.views.top_bar import render_agentos_top_bar
from golegal.agentos.ui.views.studio_view import render_studio_view
from golegal.agentos.ui.views.mission_view import render_mission_view
from golegal.agentos.ui.views.approvals_view import render_approvals_view
from golegal.agentos.ui.views.evidence_view import render_evidence_view
from golegal.agentos.ui.views.rag_lab_view import render_rag_lab_view
from golegal.agentos.ui.views.report_view import render_report_view

# GoLegal Platform Bridge Views
from golegal.ui.views.catalog_view import render_catalog_view
from golegal.ui.views.wizard_view import render_wizard_view
from golegal.ui.views.review_view import render_review_view
from golegal.ui.views.execution_view import render_execution_view
from golegal.ui.views.camera_lab_view import render_camera_lab_view
from golegal.ui.views.audit_vault_view import render_audit_vault_view


@st.cache_resource
def _bootstrap_database() -> bool:
    init_db()
    session = SessionLocal()
    try:
        seed_demo_tenants_and_templates(session)
    finally:
        session.close()
    return True


NAV_MODULES = [
    "🤖 Agent Studio",
    "🚀 Mission Console",
    "📥 Approvals Inbox",
    "🛡️ Evidence Explorer",
    "⚡ 10-Stage Hybrid RAG Lab",
    "📊 Report Center",
    "📜 Contract Platform Bridge"
]


def main() -> None:
    _bootstrap_database()
    inject_theme()

    session = SessionLocal()
    try:
        # 1. Executive Top Bar with Multi-Tenant & AgentOS Role Switcher + GPU Telemetry
        actor_context = render_agentos_top_bar()

        # 2. Main Navigation Tabs
        tab_studio, tab_mission, tab_approvals, tab_evidence, tab_rag, tab_report, tab_bridge = st.tabs(NAV_MODULES)

        with tab_studio:
            render_studio_view(session, actor_context)

        with tab_mission:
            render_mission_view(session, actor_context)

        with tab_approvals:
            render_approvals_view(session, actor_context)

        with tab_evidence:
            render_evidence_view(session, actor_context)

        with tab_rag:
            render_rag_lab_view(session, actor_context)

        with tab_report:
            render_report_view(session, actor_context)

        with tab_bridge:
            st.markdown("### 📜 GoLegal Contract Platform Bridge (System of Record)")
            c.notice(
                "<b>SYSTEM-OF-RECORD BOUNDARY:</b> AgentOS creates proposed findings and review tasks, "
                "bridged via <code>ContractGateway</code>. Official contracts, e-Stamping, and mock eSign records "
                "remain strictly governed by the underlying Contract Platform.",
                tone="warn"
            )
            b_cat, b_wiz, b_rev, b_exec, b_cam, b_aud = st.tabs([
                "Legal Catalog", "Guided Contract Wizard", "Review & Diff", "Stamping & eSign", "GPU Camera Lab", "Audit & BSA §63 Vault"
            ])
            with b_cat:
                render_catalog_view(session, actor_context)
            with b_wiz:
                render_wizard_view(session, actor_context)
            with b_rev:
                render_review_view(session, actor_context)
            with b_exec:
                render_execution_view(session, actor_context)
            with b_cam:
                render_camera_lab_view(session, actor_context)
            with b_aud:
                render_audit_vault_view(session, actor_context)

        # 3. Enterprise Footer
        st.write("")
        from golegal.ui.components import render_html
        render_html("""
        <div style="border-top: 1px solid #E5E7EB; margin-top: 2rem; padding-top: 1rem; color: #6B7280; font-size: 0.8rem; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <b style="color: #111827;">GoLegal AgentOS v1.0</b> &middot; Supervised Legal Contract Operations &middot; Section 65B &amp; BSA 2023 &sect;63 Evidence Architecture.
          </div>
          <div style="color: #C2410C; font-weight: 600;">
            NVIDIA RTX 3060 12GB &middot; CUDA 13.3 Local RAG Acceleration &middot; Offline Simulation Mode
          </div>
        </div>
        """)

    finally:
        session.close()


if __name__ == "__main__":
    main()
