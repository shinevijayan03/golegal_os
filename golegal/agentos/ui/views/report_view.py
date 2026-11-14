"""
AgentOS Report Center: Provenance Manifest, Integrity Verification & Artifact Export.
Enforces AOS-11, AOS-15, AT-24.
"""
from __future__ import annotations
import json
import streamlit as st
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import Mission, Artifact
from golegal.agentos.services.evidence_service import AgentOSEvidenceService, TamperDetectedError
from golegal.agentos.services.rbac_service import (
    ROLE_LEGAL_REVIEWER, ROLE_TENANT_ADMIN, normalize_role
)
from golegal.ui import components as c


def render_report_view(session: Session, actor_context: dict) -> None:
    st.markdown("### 📊 Report Center, Provenance Manifest & Integrity Verifier")
    c.notice(
        "<b>REPORT FROZEN STATE:</b> Exported reports include complete provenance manifests, input source hashes, "
        "and human approval logs. Modifying even 1 single byte of an exported report invalidates its cryptographic seal.",
        tone="warn"
    )

    tenant_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = normalize_role(actor_context["role"])

    evidence_svc = AgentOSEvidenceService(session)

    missions = session.query(Mission).filter_by(tenant_id=tenant_id).all()
    if not missions:
        st.info("No missions available. Launch and execute a mission to generate reports.")
        return

    m_options = {m.id: f"{m.goal[:50]}... [{m.status}]" for m in missions}
    active_mid = st.session_state.get("active_mission_id", missions[0].id)
    if active_mid not in m_options:
        active_mid = missions[0].id

    chosen_mid = st.selectbox(
        "Select Mission for Report Generation",
        options=list(m_options.keys()),
        format_func=lambda k: m_options[k],
        index=list(m_options.keys()).index(active_mid),
        key="rep_mis_select"
    )
    st.session_state["active_mission_id"] = chosen_mid
    mission = next(m for m in missions if m.id == chosen_mid)

    col1, col2 = st.columns([2.2, 1.8], gap="large")

    with col1:
        st.markdown("#### Contract Intelligence Report")
        
        # Check if already generated
        art_md = (
            session.query(Artifact)
            .filter_by(mission_id=chosen_mid, kind="REPORT_MARKDOWN")
            .first()
        )
        art_json = (
            session.query(Artifact)
            .filter_by(mission_id=chosen_mid, kind="REPORT_JSON")
            .first()
        )

        can_generate = actor_role in (ROLE_LEGAL_REVIEWER, ROLE_TENANT_ADMIN)
        if not art_md:
            if not can_generate:
                st.caption("🔒 Generating reports requires Legal Reviewer or Tenant Admin role.")
            if st.button("📑 Generate & Freeze Report", type="primary", disabled=not can_generate, key="btn_gen_report"):
                try:
                    res = evidence_svc.generate_frozen_report(mission.id, tenant_id, actor_id, actor_role)
                    st.success(f"Report frozen successfully! SHA-256: `{res['json_sha256'][:16]}...`")
                    st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"Report generation failed: {e}")
        else:
            with st.expander("📄 View Rendered Markdown Report", expanded=True):
                st.markdown(art_md.content)

            d1, d2 = st.columns(2)
            with d1:
                st.download_button(
                    label="📥 Download Report (.md)",
                    data=art_md.content,
                    file_name=f"report_{mission.id[:8]}.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="dl_report_md"
                )
            with d2:
                if art_json:
                    st.download_button(
                        label="📥 Download Manifest (.json)",
                        data=art_json.content,
                        file_name=f"manifest_{mission.id[:8]}.json",
                        mime="application/json",
                        use_container_width=True,
                        key="dl_report_json"
                    )

    with col2:
        st.markdown("#### Cryptographic Seal & Tamper Defense (AT-24)")
        if art_json:
            st.html(
                '<div style="background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 8px; padding: 12px; margin-bottom: 12px; font-size: 0.82rem;">'
                '<span style="color: #D97706; font-weight: bold;">CRYPTOGRAPHIC ARTIFACT SHA-256:</span><br/>'
                f'<code style="word-break: break-all; color: #047857;">{art_json.sha256}</code><br/>'
                '<span style="color: #6B7280; font-size: 0.75rem;">Status: <b>FROZEN &amp; IMMUTABLE</b> · Verified by SHA-256</span>'
                '</div>'
            )

            with st.expander("🔍 Provenance Manifest JSON", expanded=False):
                try:
                    p_data = json.loads(art_json.content)
                    st.json(p_data.get("provenance_manifest", {}))
                except Exception:
                    pass

            st.divider()
            st.markdown("##### 🧪 1-Byte Tamper Detection Demonstration")
            st.caption("Demonstrates immediate fail-closed detection when even 1 single byte of an exported artifact is modified.")

            if st.button("🚨 Simulate 1-Byte Report Mutation", type="primary", key="btn_tamper_artifact"):
                original_bytes = art_json.content.encode("utf-8")
                tampered = bytearray(original_bytes)
                tampered[len(tampered) // 2] ^= 0xFF
                tampered_bytes = bytes(tampered)

                try:
                    evidence_svc.verify_artifact_integrity(art_json.id, tampered_bytes)
                except TamperDetectedError as tde:
                    c.notice(
                        f"<b>TAMPER DEFENSE SUCCEEDED (AT-24):</b><br/>"
                        f"<code>{str(tde)}</code><br/>"
                        "Artifact verification failed closed immediately upon 1-byte alteration.",
                        tone="danger"
                    )
        else:
            st.info("Freeze a report on the left to inspect its cryptographic seal and provenance manifest.")
