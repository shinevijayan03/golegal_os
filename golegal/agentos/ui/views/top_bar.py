"""
AgentOS Top Bar: Multi-Tenant Switcher, AgentOS Role Personas & Hardware GPU Telemetry.
Enforces AOS-01, AOS-16, AT-01.
"""
from __future__ import annotations
from typing import Dict, Any
import streamlit as st
from golegal.ui import components as c

ORGANISATIONS = {
    "org-alpha-101": {
        "name": "Acme Logistics Pvt. Ltd.",
        "users": {
            "tenant_admin": {"id": "usr-admin-01", "name": "Alice Sharma (Tenant Admin)"},
            "agent_builder": {"id": "usr-builder-01", "name": "Edward D'Souza (Agent Builder)"},
            "mission_operator": {"id": "usr-op-01", "name": "Deepak Verma (Mission Operator)"},
            "legal_reviewer": {"id": "usr-legal-01", "name": "Advocate Mehra (Legal Reviewer)"},
            "read_only_auditor": {"id": "usr-audit-01", "name": "Arthur Pendelton (Auditor)"},
        }
    },
    "org-beta-202": {
        "name": "Starlight Retail Ventures",
        "users": {
            "tenant_admin": {"id": "usr-admin-02", "name": "Bob Henderson (Tenant Admin)"},
            "agent_builder": {"id": "usr-builder-02", "name": "Elena Rostova (Agent Builder)"},
            "mission_operator": {"id": "usr-op-02", "name": "DevOps Engineer (Mission Operator)"},
            "legal_reviewer": {"id": "usr-legal-02", "name": "Counsel Nair (Legal Reviewer)"},
            "read_only_auditor": {"id": "usr-audit-02", "name": "Beverly Marsh (Auditor)"},
        }
    }
}


def render_agentos_top_bar() -> Dict[str, Any]:
    if "active_org_id" not in st.session_state:
        st.session_state["active_org_id"] = "org-alpha-101"
    if "active_role" not in st.session_state:
        st.session_state["active_role"] = "tenant_admin"

    current_org = ORGANISATIONS[st.session_state["active_org_id"]]
    c.brand_header(current_org["name"], st.session_state["active_role"])

    col1, col2, col3 = st.columns([2.5, 2.5, 3.5], gap="medium")
    with col1:
        chosen_org = st.selectbox(
            "Tenant Organisation",
            options=list(ORGANISATIONS.keys()),
            format_func=lambda k: ORGANISATIONS[k]["name"],
            index=list(ORGANISATIONS.keys()).index(st.session_state["active_org_id"]),
            key="sb_org_picker"
        )
        if chosen_org != st.session_state["active_org_id"]:
            st.session_state["active_org_id"] = chosen_org
            st.session_state["active_mission_id"] = None
            st.rerun()

    with col2:
        roles = list(current_org["users"].keys())
        chosen_role = st.selectbox(
            "Active Role Persona",
            options=roles,
            format_func=lambda r: f"{current_org['users'][r]['name']}",
            index=roles.index(st.session_state["active_role"]) if st.session_state["active_role"] in roles else 0,
            key="sb_role_picker"
        )
        if chosen_role != st.session_state["active_role"]:
            st.session_state["active_role"] = chosen_role
            st.rerun()

    with col3:
        c.render_html("""
        <div style="font-size: 0.8rem; background: #FFF7ED; border: 1px solid #FED7AA; border-radius: 6px; padding: 6px 12px; margin-top: 24px; color: #1E1E1E;">
          <span style="color: #EA580C; font-weight: bold;">⚡ GPU AI &amp; RAG TELEMETRY:</span>
          <span style="color: #431407; font-weight: 500;">RTX 3060 12GB · CUDA 13.3 · Local Dense Indexing Active</span>
        </div>
        """)

    actor_info = current_org["users"][st.session_state["active_role"]]
    return {
        "org_id": st.session_state["active_org_id"],
        "org_name": current_org["name"],
        "role": st.session_state["active_role"],
        "actor_id": actor_info["id"],
        "actor_name": actor_info["name"],
    }
