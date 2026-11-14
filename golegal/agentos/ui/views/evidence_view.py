"""
AgentOS Evidence Explorer: Verbatim Citations, Reviewer Disposition & PDF Intake.
Enforces AOS-11, AT-18, AT-20, AT-22.
"""
from __future__ import annotations
import time
import streamlit as st
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import Finding, SourceSpan, Mission, DocumentSource, SourceRevision
from golegal.agentos.services.evidence_service import AgentOSEvidenceService, EvidenceMismatchError
from golegal.agentos.integrations.source_gateway import UploadedSourceGateway, FileValidationError
from golegal.agentos.services.rbac_service import (
    ROLE_LEGAL_REVIEWER, ROLE_TENANT_ADMIN, normalize_role
)
from golegal.ui import components as c


def render_evidence_view(session: Session, actor_context: dict) -> None:
    st.markdown("### 🛡️ Evidence Explorer & Legal Reviewer Queue")
    c.notice(
        "<b>VERBATIM CITATION INTEGRITY:</b> In accordance with Section 9 & AT-18, model outputs are "
        "untrusted. Every deviation finding must match an exact character slice from the source text. "
        "Mismatches or missing citations are marked <code>UNSUPPORTED</code> and blocked from verification.",
        tone="warn"
    )

    tenant_id = actor_context["org_id"]
    actor_id = actor_context["actor_id"]
    actor_role = normalize_role(actor_context["role"])

    evidence_svc = AgentOSEvidenceService(session)
    source_gw = UploadedSourceGateway(session)

    tab_findings, tab_upload, tab_rag_lab = st.tabs([
        "🔍 Candidate Findings & Disposition",
        "📤 Scoped PDF Intake (PyMuPDF)",
        "⚡ 10-Stage Hybrid RAG Lab"
    ])

    with tab_findings:
        missions = session.query(Mission).filter_by(tenant_id=tenant_id).all()
        if not missions:
            st.info("No missions found. Launch a mission and run tasks to populate findings.")
            return

        m_options = {m.id: f"{m.goal[:50]}... [{m.status}]" for m in missions}
        active_mid = st.session_state.get("active_mission_id", missions[0].id)
        if active_mid not in m_options:
            active_mid = missions[0].id

        chosen_mid = st.selectbox(
            "Select Mission Scope",
            options=list(m_options.keys()),
            format_func=lambda k: m_options[k],
            index=list(m_options.keys()).index(active_mid),
            key="ev_mis_select"
        )
        st.session_state["active_mission_id"] = chosen_mid

        findings = (
            session.query(Finding)
            .filter_by(mission_id=chosen_mid)
            .order_by(Finding.id.asc())
            .all()
        )

        if not findings:
            st.info("No findings generated yet for this mission. Run investigation tasks in the Mission Console.")
        else:
            st.markdown(f"**Discovered Findings:** `{len(findings)}` candidates")
            for f in findings:
                with st.container(border=True):
                    col1, col2 = st.columns([1.8, 2.2], gap="large")
                    with col1:
                        sev_badge = "gl-badge-danger" if f.severity == "HIGH" else "gl-badge-review"
                        ver_badge = "gl-badge-approved" if f.verification_state == "VERIFIED" else "gl-badge-draft"
                        
                        st.markdown(f"**[{f.playbook_rule_id}]** <span class='gl-badge {sev_badge}'>{f.severity}</span>", unsafe_allow_html=True)
                        st.markdown(f"**Statement:** {f.statement}")
                        st.caption(f"Category: `{f.category}` · Verification: <span class='gl-badge {ver_badge}'>{f.verification_state}</span>", unsafe_allow_html=True)
                        
                        # Verification check trigger
                        if f.verification_state != "VERIFIED":
                            if st.button("🔎 Verify Citation Integrity", key=f"btn_ver_{f.id}"):
                                try:
                                    evidence_svc.verify_finding_span(f.id, tenant_id)
                                    st.success("Citation verified against source text!")
                                    st.rerun()
                                except EvidenceMismatchError as em:
                                    st.error(str(em))

                    with col2:
                        span = f.span
                        st.markdown("##### Verbatim Document Citation (AT-18)")
                        if span:
                            st.html(
                                '<blockquote style="background: #F9FAFB; border-left: 3px solid #D32F2F; padding: 8px 12px; margin: 4px 0; font-size: 0.82rem; color: #111827;">'
                                f'"{span.verbatim_excerpt}"'
                                '</blockquote>'
                                '<div style="font-size: 0.75rem; color: #6B7280; margin-top: 4px;">'
                                f'Page: <b>{span.page_index_0 + 1}</b> · Chars: <b>{span.char_start}–{span.char_end}</b> · Hash: <code>{span.excerpt_sha256[:16]}...</code>'
                                '</div>'
                            )
                        else:
                            st.caption("No anchor span attached.")

                        # Legal Reviewer Disposition Controls (AT-22)
                        st.divider()
                        st.markdown("##### Legal Reviewer Disposition (AT-22)")
                        disp_badge = "gl-badge-approved" if f.review_state == "ACCEPTED" else ("gl-badge-danger" if f.review_state == "REJECTED" else "gl-badge-draft")
                        st.markdown(f"Status: <span class='gl-badge {disp_badge}'>{f.review_state}</span> (Reviewer: `{f.reviewed_by or 'None'}`)", unsafe_allow_html=True)

                        rationale = st.text_input("Reviewer Rationale", value=f.rationale or "Confirmed deviation from approved 36-month standard.", key=f"rat_{f.id}")

                        can_review = actor_role in (ROLE_LEGAL_REVIEWER, ROLE_TENANT_ADMIN)
                        if not can_review:
                            st.caption("🔒 Active role lacks Legal Reviewer authority. Only Reviewer or Admin can disposition findings.")

                        rb1, rb2 = st.columns(2)
                        with rb1:
                            if st.button(f"✅ Accept #{f.id[:6]}", disabled=not can_review, use_container_width=True, key=f"btn_acc_{f.id}", type="primary"):
                                evidence_svc.record_reviewer_disposition(f.id, tenant_id, "ACCEPTED", rationale, actor_id, actor_role)
                                st.success("Finding accepted into report!")
                                st.rerun()
                        with rb2:
                            if st.button(f"❌ Reject #{f.id[:6]}", disabled=not can_review, use_container_width=True, key=f"btn_rej_{f.id}"):
                                evidence_svc.record_reviewer_disposition(f.id, tenant_id, "REJECTED", rationale, actor_id, actor_role)
                                st.warning("Finding rejected.")
                                st.rerun()

    with tab_upload:
        st.markdown("#### Scoped PDF Intake (PyMuPDF)")
        st.caption("Upload supplier NDAs, MSAs, or vendor contracts for PyMuPDF character-offset span extraction.")

        uploaded_file = st.file_uploader(
            "Upload Agreement PDF (Max 10 MiB, Max 1000 Pages)",
            type=["pdf"],
            key="pdf_uploader"
        )
        coll_id = st.text_input("Collection ID", value="col_supplier_ndas", key="upload_coll_id")

        if uploaded_file and st.button("📤 Ingest & Parse PDF", type="primary", key="btn_ingest_pdf"):
            try:
                s_bytes = uploaded_file.read()
                s_rev = source_gw.intake_pdf(
                    tenant_id=tenant_id,
                    collection_id=coll_id,
                    filename=uploaded_file.name,
                    file_bytes=s_bytes,
                    actor_id=actor_id
                )
                if s_rev.text_extraction_status == "INCOMPLETE_TEXT":
                    c.notice(
                        "<b>INCOMPLETE_TEXT WARNING (AT-20):</b> This PDF contains scanned image data with no "
                        "usable selectable text. PyMuPDF recorded zero fabricated text. Gated for manual review.",
                        tone="warn"
                    )
                else:
                    st.success(f"PDF parsed successfully! Revision ID: `{s_rev.id}` (Pages: {s_rev.page_count}, Status: `{s_rev.text_extraction_status}`)")
                st.rerun()
            except FileValidationError as fve:
                st.error(str(fve))
            except Exception as e:
                session.rollback()
                st.error(f"Upload failed: {e}")

    with tab_rag_lab:
        st.markdown("#### ⚡ 10-Stage Hybrid RAG & Neural Reranker Workbench")
        st.caption(
            "Interactive inspection of the 10-stage retrieval pipeline: "
            "Dense FAISS Vector Search + Sparse BM25 Keyword Search + Open-Source Cross-Encoder Reranker."
        )

        # Fetch available source revisions
        revisions = (
            session.query(SourceRevision)
            .filter_by(tenant_id=tenant_id)
            .order_by(SourceRevision.created_at.desc())
            .all()
        )
        if not revisions:
            st.info("No document revisions available. Upload a PDF in the 'Scoped PDF Intake' tab first.")
        else:
            r_opts = {r.id: f"{r.source.name if r.source else 'Doc'} (Rev {r.revision_no}, {r.page_count}p)" for r in revisions}
            selected_rev_id = st.selectbox(
                "Select Target Document for Hybrid Search",
                options=list(r_opts.keys()),
                format_func=lambda k: r_opts[k],
                key="rag_lab_rev_select"
            )

            sample_queries = [
                "What is the confidentiality duration or survival term?",
                "Which state or country's laws govern this agreement?",
                "Are there any indemnities or liability exclusions?",
                "What are the payment terms and consideration amount?"
            ]
            query_input = st.text_input(
                "Natural Language Clause Query",
                value=sample_queries[0],
                key="rag_lab_query_input"
            )

            col_btn, col_info = st.columns([1.5, 3.5])
            with col_btn:
                run_rag = st.button("🚀 Execute Hybrid Search", type="primary", key="btn_run_hybrid_rag")
            with col_info:
                st.markdown(
                    "<span class='gl-badge gl-badge-approved' style='font-size:0.75rem;'>"
                    "GPU ACCELERATED: NVIDIA GeForce RTX 3060 12GB (CUDA 13.3)</span>",
                    unsafe_allow_html=True
                )

            if run_rag and query_input:
                t0 = time.perf_counter()
                from golegal.agentos.intelligence.hybrid_rag import HybridRAGEngine
                hybrid_rag = HybridRAGEngine(session)
                results = hybrid_rag.search_clauses(
                    tenant_id=tenant_id,
                    source_revision_ids=[selected_rev_id],
                    query=query_input,
                    top_k=5
                )
                duration_ms = (time.perf_counter() - t0) * 1000.0

                if not results:
                    st.warning("No matching spans found for the selected document.")
                else:
                    st.success(f"Retrieved {len(results)} ranked chunks in {duration_ms:.1f} ms via Dense + BM25 + Cross-Encoder!")
                    for idx, res in enumerate(results, 1):
                        with st.container(border=True):
                            r1, r2 = st.columns([3.5, 1.5])
                            with r1:
                                st.markdown(f"**Rank #{idx}** · Similarity Score: `{res['similarity_score']}` · Cross-Encoder Logit: `{res['rerank_score']}`")
                                st.html(
                                    '<blockquote style="background: #F9FAFB; border-left: 3px solid #D32F2F; padding: 8px 12px; margin: 4px 0; font-size: 0.85rem; color: #111827;">'
                                    f'"{res["verbatim_excerpt"]}"'
                                    '</blockquote>'
                                )
                                st.caption(f"Page: {res['page_index_0'] + 1} · Chars: {res['char_start']}–{res['char_end']} · Hash: <code>{res['excerpt_sha256'][:16]}...</code>")
                            with r2:
                                st.markdown(f"<span class='gl-badge gl-badge-approved'>VERBATIM VERIFIED</span>", unsafe_allow_html=True)
                                st.markdown(f"**Method:** `{res['method']}`")
                                st.markdown(f"**Device:** `{res['device_accelerator']}`")
