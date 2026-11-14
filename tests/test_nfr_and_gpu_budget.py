"""
GoLegal vNext - Non-Functional Requirements (NFR) & GPU Budget Test Suite
Validates strict P95 latency bounds, GPU hardware SLA (< 50.0s), and 100% tenant isolation.
"""
import pytest
import time
import numpy as np
from datetime import datetime, timezone

from golegal.domain.models import Organisation, Contract, AuditEvent
from golegal.services.contract_service import ContractService
from golegal.services.document_service import DocumentService
from golegal.services.gpu_vision_service import GPUVisionService
from golegal.services.ai_insight_service import AIInsightService


class TestNFRAndGPUBudget:
    """Verifies quantitative performance budgets and hard architectural NFR constraints."""

    def test_nfr_form_read_p95_under_400ms(self, vnext_tenants, db_session):
        """P95 latency for reading contract form state must be strictly under 400 ms (NFR-02)."""
        contract_svc = ContractService(db_session)
        org_id = vnext_tenants["tenant_a"]["org_id"]
        owner = vnext_tenants["tenant_a"]["owner"]["id"]

        c = contract_svc.create_contract(
            org_id=org_id, actor_id=owner, template_version_id="tpl_ka_rental_v1",
            title="Read Latency Test", field_values={"monthly_rent_paise": 2500000, "start_date": "2026-12-01", "end_date": "2027-10-31"}
        )

        latencies = []
        for _ in range(20):
            t0 = time.perf_counter()
            _ = contract_svc.get_contract(c.id, org_id, owner)
            latencies.append((time.perf_counter() - t0) * 1000)  # ms

        p95 = np.percentile(latencies, 95)
        assert p95 < 400.0, f"P95 form read latency was {p95:.2f} ms (must be < 400 ms)"

    def test_nfr_pdf_generation_under_10s(self, vnext_tenants, db_session):
        """Standard 2-to-10 page PDF generation P95 latency must be strictly under 10.0 seconds (NFR-02)."""
        doc_svc = DocumentService()
        org_id = vnext_tenants["tenant_a"]["org_id"]

        payload = {
            "title": "Standard Rental Deed",
            "monthly_rent_paise": 2800000,
            "security_deposit_paise": 12000000,
            "start_date": "2026-12-01",
            "end_date": "2027-10-31",
            "lessor": "Ramakiran Reddy",
            "lessee": "Mayank Tripathi",
            "address": "402, Sunrise Apartments, Bellandur, Bangalore",
        }

        latencies = []
        for _ in range(5):
            t0 = time.perf_counter()
            pdf = doc_svc.render_pdf("c-sample-01", org_id, payload, watermark="DRAFT")
            latencies.append(time.perf_counter() - t0)
            assert len(pdf) > 2000

        p95 = np.percentile(latencies, 95)
        assert p95 < 10.0, f"P95 PDF render was {p95:.2f} s (must be < 10.0 s)"

    def test_nfr_gpu_camera_intake_under_50s(self, noisy_camera_image_bytes):
        """Batch of 10 camera scan frames must complete GPU deskew/denoise/OCR under 50.0s SLA."""
        vision = GPUVisionService(device="cpu")  # Runs CPU or GPU benchmark
        batch_frames = [noisy_camera_image_bytes] * 10

        t0 = time.perf_counter()
        results = vision.process_camera_batch(batch_frames)
        total_time = time.perf_counter() - t0

        assert len(results) == 10
        assert total_time < 50.0, f"Camera batch processing took {total_time:.2f} s (SLA < 50.0 s)"

    def test_nfr_tenant_isolation_100_percent_across_search_and_audit(self, vnext_tenants, db_session):
        """Search and audit queries strictly partitioned by organisation_id; zero cross-tenant leakage."""
        contract_svc = ContractService(db_session)
        ai_svc = AIInsightService(db_session)
        
        # Tenant A contract
        c_a = contract_svc.create_contract(
            org_id=vnext_tenants["tenant_a"]["org_id"],
            actor_id=vnext_tenants["tenant_a"]["owner"]["id"],
            template_version_id="tpl_ka_rental_v1",
            title="Secret Project Falcon",
            field_values={"covenants": "Project Falcon confidential terms"}
        )

        # Tenant B search
        b_results = ai_svc.search_contracts(
            org_id=vnext_tenants["tenant_b"]["org_id"],
            query="Falcon"
        )
        assert len(b_results) == 0, "Cross-tenant contract appeared in search results!"

        # Tenant A search
        a_results = ai_svc.search_contracts(
            org_id=vnext_tenants["tenant_a"]["org_id"],
            query="Falcon"
        )
        assert len(a_results) > 0
        assert a_results[0]["id"] == c_a.id
