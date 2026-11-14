"""
Synthetic Demonstration Data Seeder for Multi-Tenant Testing & UI Exploration.
"""
from __future__ import annotations
import hashlib
from sqlalchemy.orm import Session

from golegal.domain.models import Organisation, Membership, Contract, DocumentRevision
from golegal.services.catalog_service import CatalogService
from golegal.ui.views.top_bar import ORGANISATIONS


def seed_demo_tenants_and_templates(session: Session) -> None:
    """Idempotently seeds demo tenants, memberships, and catalog templates."""
    # 1. Seed Catalog Templates
    cat_svc = CatalogService(session)
    cat_svc.seed_demo_templates_if_missing()

    # 2. Seed Organisations & Memberships
    for org_id, org_info in ORGANISATIONS.items():
        org = session.query(Organisation).filter_by(id=org_id).first()
        if not org:
            org = Organisation(id=org_id, name=org_info["name"])
            session.add(org)
            session.flush()

        for role_name, user_data in org_info["users"].items():
            u_id = user_data["id"]
            m = session.query(Membership).filter_by(organisation_id=org_id, user_id=u_id).first()
            if not m:
                m = Membership(
                    organisation_id=org_id,
                    user_id=u_id,
                    role=role_name,
                    user_email=f"{u_id}@{org_id}.example.com"
                )
                session.add(m)

    # 3. Seed an initial demonstration contract in org-alpha-101 if none exists
    demo_contract = session.query(Contract).filter_by(organisation_id="org-alpha-101").first()
    if not demo_contract:
        c1 = Contract(
            id="ctr-demo-ka-rental-001",
            organisation_id="org-alpha-101",
            template_version_id="tpl_ka_rental_v1",
            title="Commercial Lease - Indiranagar Tech Park Unit 4B",
            created_by="usr-edward-01",  # Editor submitted it
            status="IN_REVIEW",
            etag_version=1
        )
        c1.field_values = {
            "title": "Commercial Lease - Indiranagar Tech Park Unit 4B",
            "lessor": "Bengaluru Properties Trust",
            "lessee": "Acme Logistics Pvt. Ltd.",
            "start_date": "2026-12-01",
            "end_date": "2027-11-30",
            "monthly_rent_paise": 6500000,
            "security_deposit_paise": 30000000,
            "custom_covenants": "Premises shall be used strictly for commercial IT operations."
        }
        session.add(c1)
        session.flush()

        # Add initial revision
        rev = DocumentRevision(
            id="rev-demo-001",
            contract_id=c1.id,
            revision_no=1,
            object_key=f"contracts/{c1.id}/revisions/rev_1.pdf",
            mime_type="application/pdf",
            size_bytes=2048,
            sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            render_status="completed"
        )
        session.add(rev)
        c1.current_revision_id = rev.id

    # 4. Seed AgentOS Default Pack, Policy & Deployments
    from golegal.agentos.services.studio_service import StudioService
    studio_svc = StudioService(session)
    studio_svc.seed_default_pack_if_missing()

    for org_id in ("org-alpha-101", "org-beta-202"):
        studio_svc.get_or_create_default_policy(org_id)

    # Seed an approved agent definition & deployment for org-alpha-101 if none exists
    from golegal.agentos.domain.models import AgentDefinition, AgentDeployment, DocumentSource, SourceRevision, SourceSpan
    def_alpha = session.query(AgentDefinition).filter_by(tenant_id="org-alpha-101").first()
    if not def_alpha:
        def_alpha = studio_svc.create_agent_definition(
            tenant_id="org-alpha-101",
            name="Contract Intelligence Agent - Supplier NDAs",
            goal_template="Examine supplier non-disclosure agreements against Playbook 2026-11; identify deviations in confidentiality duration, governing law, and uncapped indemnities.",
            config={
                "allowed_skills": ["search", "extract", "compare", "verify", "draft"],
                "max_files": 30,
                "max_tool_calls": 150,
                "max_steps": 25,
                "budget_ceiling_minor": 25000,
                "allowed_playbooks": ["playbook_nda_2026_11"],
                "target_clause_categories": ["confidentiality_duration", "governing_law", "indemnity"]
            },
            actor_id="usr-builder-01",
            actor_role="TENANT_ADMIN"
        )
        dep_alpha = studio_svc.approve_deployment(
            tenant_id="org-alpha-101",
            definition_id=def_alpha.id,
            playbook_version_id="playbook_nda_2026_11",
            allowed_collection_ids=["col_supplier_ndas", "col_default"],
            actor_id="usr-admin-01",
            actor_role="TENANT_ADMIN"
        )

    # Seed demo document source and spans for org-alpha-101 if none exists
    demo_doc = session.query(DocumentSource).filter_by(tenant_id="org-alpha-101").first()
    if not demo_doc:
        import hashlib
        demo_doc = DocumentSource(
            id="src-nda-alpha-001",
            tenant_id="org-alpha-101",
            collection_id="col_supplier_ndas",
            name="Supplier_NDA_Alpha_Logistics.pdf",
            created_by="usr-builder-01",
            status="ACTIVE"
        )
        session.add(demo_doc)
        session.flush()

        text_content = (
            "MUTUAL NON-DISCLOSURE AGREEMENT\n\n"
            "This Mutual Non-Disclosure Agreement is entered into by and between Acme Logistics Pvt. Ltd. "
            "and Global Supplier Tech Corp.\n\n"
            "Clause 4. Term and Duration.\n"
            "The receiving party shall hold and maintain all Confidential Information in strictest confidence "
            "for a period of 5 years (60 months) from the date of disclosure.\n\n"
            "Clause 8. Governing Law and Jurisdiction.\n"
            "This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware, "
            "United States, without regard to conflict of law principles.\n\n"
            "Clause 11. Indemnification.\n"
            "The receiving party agrees to indemnify and hold harmless the disclosing party without limitation for all damages, "
            "liabilities, and legal fees arising out of any breach."
        )
        doc_sha = hashlib.sha256(text_content.encode("utf-8")).hexdigest()

        s_rev = SourceRevision(
            id="rev-nda-alpha-001",
            tenant_id="org-alpha-101",
            document_source_id=demo_doc.id,
            revision_no=1,
            object_key=f"sources/org-alpha-101/{demo_doc.id}/rev_1.pdf",
            sha256=doc_sha,
            mime_type="application/pdf",
            bytes=len(text_content),
            page_count=2,
            text_extraction_status="SUCCESS",
            extracted_text=text_content
        )
        session.add(s_rev)
        session.flush()

        # Seed exact spans
        spans_data = [
            (
                "The receiving party shall hold and maintain all Confidential Information in strictest confidence for a period of 5 years (60 months) from the date of disclosure.",
                0, 150, 312
            ),
            (
                "This Agreement shall be governed by and construed in accordance with the laws of the State of Delaware, United States, without regard to conflict of law principles.",
                0, 345, 514
            ),
            (
                "The receiving party agrees to indemnify and hold harmless the disclosing party without limitation for all damages, liabilities, and legal fees arising out of any breach.",
                1, 540, 715
            )
        ]

        for exc, p_idx, c_st, c_en in spans_data:
            span = SourceSpan(
                tenant_id="org-alpha-101",
                source_revision_id=s_rev.id,
                source_sha256=doc_sha,
                page_index_0=p_idx,
                char_start=c_st,
                char_end=c_en,
                verbatim_excerpt=exc,
                excerpt_sha256=hashlib.sha256(exc.encode("utf-8")).hexdigest(),
                extraction_method="PYMUPDF_EXACT"
            )
            session.add(span)

    # Seed demo deployment and document source for org-beta-202 if missing
    dep_beta = session.query(AgentDeployment).filter_by(tenant_id="org-beta-202").first()
    if not dep_beta:
        def_beta = studio_svc.create_agent_definition(
            tenant_id="org-beta-202",
            name="Contract Intelligence Agent - Retail Supplier NDAs",
            goal_template="Audit retail supplier agreements against standard Playbook 2026-11.",
            config={
                "allowed_skills": ["search", "extract", "compare", "verify", "draft"],
                "max_files": 30,
                "max_tool_calls": 150,
                "max_steps": 25,
                "budget_ceiling_minor": 25000,
                "allowed_playbooks": ["playbook_nda_2026_11"],
                "target_clause_categories": ["confidentiality_duration", "governing_law"]
            },
            actor_id="usr-builder-02",
            actor_role="TENANT_ADMIN"
        )
        dep_beta = studio_svc.approve_deployment(
            tenant_id="org-beta-202",
            definition_id=def_beta.id,
            playbook_version_id="playbook_nda_2026_11",
            allowed_collection_ids=["col_supplier_ndas", "col_default"],
            actor_id="usr-admin-02",
            actor_role="TENANT_ADMIN"
        )

        doc_beta = DocumentSource(
            id="src-nda-beta-001",
            tenant_id="org-beta-202",
            collection_id="col_supplier_ndas",
            name="Supplier_NDA_Beta_Retail.pdf",
            created_by="usr-builder-02",
            status="ACTIVE"
        )
        session.add(doc_beta)
        session.flush()

        text_beta = "Retail Vendor NDA for Starlight Retail Ventures. Confidentiality shall last 3 years."
        s_rev_beta = SourceRevision(
            id="rev-nda-beta-001",
            tenant_id="org-beta-202",
            document_source_id=doc_beta.id,
            revision_no=1,
            object_key=f"sources/org-beta-202/{doc_beta.id}/rev_1.pdf",
            sha256=hashlib.sha256(text_beta.encode("utf-8")).hexdigest(),
            bytes=len(text_beta),
            page_count=1,
            text_extraction_status="SUCCESS",
            extracted_text=text_beta
        )
        session.add(s_rev_beta)

    session.commit()
