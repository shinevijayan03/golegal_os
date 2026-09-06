"""
Tests for Document Assembly & Cryptographic Sealing Engine (TC-DOC)
"""
import pytest
from services.doc_assembly import DocumentAssemblyEngine


class TestDocumentAssemblyEngine:
    @pytest.fixture
    def doc_engine(self):
        return DocumentAssemblyEngine()

    @pytest.fixture
    def doc_fixtures(self):
        agr_data = {
            "property_address": "Flat 402, Sunrise Apts, Bellandur, Bangalore - 560103",
            "monthly_rent": 28000.0,
            "security_deposit": 120000.0,
            "lease_months": 11,
            "notice_days": 30,
            "clauses": [
                {"title": "Tenancy Grant", "text": "Lessor leases premises to Lessee for residential use."},
                {"title": "Rent Payment", "text": "Rent of ₹28,000 to be paid on or before 5th of each month."},
                {"title": "Termination", "text": "30 days prior written notice required by either party."}
            ]
        }
        parties = [
            {"name": "Ramakiran Reddy", "type": "Owner", "phone": "9876543210", "email": "ramakiran@example.com", "aadhaar_masked": "XXXXXXXX1111"},
            {"name": "Mayank Tripathi", "type": "Tenant", "phone": "9876543211", "email": "mayank@example.com", "aadhaar_masked": "XXXXXXXX2222"},
            {"name": "Suresh Kumar", "type": "Witness", "phone": "9876543212", "email": "suresh@example.com", "aadhaar_masked": "XXXXXXXX3333"}
        ]
        estamp = {
            "certificate_number": "IN-KA0100ABCD123456",
            "stamp_amount": 100.0,
            "state_code": "KA",
            "purchased_by": "Ramakiran Reddy",
            "issued_at": "06-Sep-2026"
        }
        signatures = [
            {"party_name": "Ramakiran Reddy", "party_type": "Owner", "signed_at": "06-Sep-2026 10:00:00", "signature_hash": "a1b2c3d4e5f6..."},
            {"party_name": "Mayank Tripathi", "party_type": "Tenant", "signed_at": "06-Sep-2026 10:05:00", "signature_hash": "b2c3d4e5f6a1..."},
            {"party_name": "Suresh Kumar", "party_type": "Witness", "signed_at": "06-Sep-2026 10:10:00", "signature_hash": "c3d4e5f6a1b2..."}
        ]
        return {"agr_data": agr_data, "parties": parties, "estamp": estamp, "signatures": signatures}

    # -------------------------------------------------------------
    # PDF Assembly Generation (TC-DOC-01, 02)
    # -------------------------------------------------------------
    def test_pdf_assembly_generation(self, doc_engine, doc_fixtures):
        pdf_bytes = doc_engine.generate_pdf_agreement(
            agreement_data=doc_fixtures["agr_data"],
            parties=doc_fixtures["parties"],
            estamp=doc_fixtures["estamp"],
            signatures=doc_fixtures["signatures"],
            is_draft=False
        )

        assert pdf_bytes is not None
        assert len(pdf_bytes) > 2000
        # Valid PDF header magic bytes
        assert pdf_bytes.startswith(b"%PDF-")

    # -------------------------------------------------------------
    # SHA-256 Digest & Tamper Evidence (TC-DOC-04)
    # -------------------------------------------------------------
    def test_sha256_digest_and_tamper_evidence(self, doc_engine, doc_fixtures):
        pdf_bytes = doc_engine.generate_pdf_agreement(
            agreement_data=doc_fixtures["agr_data"],
            parties=doc_fixtures["parties"],
            estamp=doc_fixtures["estamp"],
            signatures=doc_fixtures["signatures"]
        )

        digest = doc_engine.compute_sha256(pdf_bytes)
        assert len(digest) == 64
        assert int(digest, 16) > 0 # Valid hex

        # Valid untampered document verification
        assert doc_engine.verify_tamper_evidence(pdf_bytes, digest) is True

        # Tamper 1 byte of the document
        tampered_bytes = bytearray(pdf_bytes)
        tampered_bytes[100] = (tampered_bytes[100] + 1) % 256
        tampered_bytes = bytes(tampered_bytes)

        # Verification must detect tampering
        assert doc_engine.verify_tamper_evidence(tampered_bytes, digest) is False

    # -------------------------------------------------------------
    # Draft Watermark Testing
    # -------------------------------------------------------------
    def test_draft_watermark_rendering(self, doc_engine, doc_fixtures):
        draft_pdf = doc_engine.generate_pdf_agreement(
            agreement_data=doc_fixtures["agr_data"],
            parties=doc_fixtures["parties"],
            estamp=None,
            signatures=None,
            is_draft=True
        )
        assert draft_pdf.startswith(b"%PDF-")
        assert len(draft_pdf) > 2000
