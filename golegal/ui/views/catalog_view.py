"""
Legal Catalog & Eligibility Studio View.
Enforces FR-02 & AT-02: Clear visual banners for unapproved legal templates.
"""
from __future__ import annotations
import json
import streamlit as st
from sqlalchemy.orm import Session

from golegal.services.catalog_service import CatalogService
from golegal.ui import components as c


def render_catalog_view(session: Session, actor_context: dict) -> None:
    st.markdown("### 📜 Versioned Legal Catalog & Statutory Eligibility")
    c.notice(
        "<b>LEGAL GUARDRAIL:</b> All seeded demonstration templates are marked "
        "<code>DRAFT_NOT_LEGAL_APPROVED</code>. In accordance with Section 1 of the PRD, "
        "unapproved templates permit draft-only generation; execution is strictly blocked.",
        tone="warn"
    )

    catalog_svc = CatalogService(session)
    catalog_svc.seed_demo_templates_if_missing()
    templates = catalog_svc.list_templates()

    col1, col2 = st.columns([1.5, 2], gap="large")

    with col1:
        st.markdown("#### Approved & Seeded Templates")
        for tpl in templates:
            with st.container(border=True):
                st.markdown(f"**{c.esc(tpl.id)}**")
                st.markdown(f"<span style='color: #C2410C; font-weight: 500; font-size: 0.85rem;'>{c.esc(tpl.agreement_type)} · State: {c.esc(tpl.jurisdiction_code)} · v{c.esc(tpl.version)}</span>", unsafe_allow_html=True)
                st.markdown(f"Status: <span class='gl-badge gl-badge-draft'>{c.esc(tpl.state.upper())}</span>", unsafe_allow_html=True)
                
                rule = tpl.eligibility_rules[0] if tpl.eligibility_rules else None
                if rule:
                    c.render_html(f"""
                    <div style='font-size: 0.8rem; color: #4B5563; margin-top: 0.5rem; line-height: 1.5;'>
                      • Execution Mode: <b>{c.esc(rule.execution_mode)}</b><br/>
                      • Requires e-Stamp: <b>{'Yes' if rule.requires_stamping else 'No'}</b><br/>
                      • Registration Review: <b>{'Mandatory' if rule.requires_registration_review else 'Exempt'}</b>
                    </div>
                    """)

    with col2:
        st.markdown("#### Schema & Eligibility Details")
        selected_id = st.selectbox(
            "Select Template to Inspect",
            options=[t.id for t in templates],
            key="cat_tpl_select"
        )
        selected_tpl = next((t for t in templates if t.id == selected_id), None)
        if selected_tpl:
            st.markdown(f"**Agreement Type:** `{selected_tpl.agreement_type}`")
            st.markdown(f"**Jurisdiction Code:** `{selected_tpl.jurisdiction_code}`")
            
            with st.expander("JSON Schema Contract Specification", expanded=True):
                st.json(selected_tpl.schema_json)

            if actor_context.get("role") in ("owner", "legal_admin"):
                st.divider()
                st.markdown("##### ⚖️ Legal Administrator Actions")
                st.caption("Publish new rule version or modify statutory eligibility.")
                rule = selected_tpl.eligibility_rules[0] if selected_tpl.eligibility_rules else None
                if rule:
                    new_mode = st.selectbox(
                        "Execution Mode Policy",
                        options=["draft_only", "provider_allowed", "blocked"],
                        index=["draft_only", "provider_allowed", "blocked"].index(rule.execution_mode),
                        key=f"mode_{rule.id}"
                    )
                    if st.button("Update Eligibility Rule", key=f"up_rule_{rule.id}"):
                        rule.execution_mode = new_mode
                        session.commit()
                        st.success(f"Rule updated to '{new_mode}'.")
                        st.rerun()
