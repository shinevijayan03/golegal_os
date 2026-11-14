"""
AgentOS UploadedSourceGateway: PDF Intake, PyMuPDF Parsing & Span Extraction.
Enforces AOS-08, AT-17, AT-20, and NFR-AOS-02 limits.
"""
from __future__ import annotations
import io
import json
import hashlib
import fitz  # PyMuPDF
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import (
    DocumentSource, SourceRevision, SourceSpan, generate_uuid, utc_now
)
from golegal.agentos.services.rbac_service import RBACService


class FileValidationError(ValueError):
    """Raised when uploaded file violates format, size, or page constraints (AT-20)."""
    pass


SecurityQuarantineError = FileValidationError


class UploadedSourceGateway:
    MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MiB limit
    MAX_PAGES = 1000  # 1000 aggregate page limit

    def __init__(self, session: Session):
        self.session = session

    def intake_pdf(
        self,
        tenant_id: str,
        collection_id: str,
        filename: str,
        file_bytes: bytes,
        actor_id: str
    ) -> SourceRevision:
        """
        Enforces AOS-08, AT-17, AT-20: Scoped document intake with PyMuPDF parsing.
        """
        # 1. Size Check
        size = len(file_bytes)
        if size == 0:
            raise FileValidationError("422 UNPROCESSABLE: Uploaded PDF is empty (0 bytes).")
        if size > self.MAX_FILE_BYTES:
            raise FileValidationError(f"413 FILE_TOO_LARGE: File size ({size / (1024*1024):.2f} MiB) exceeds 10 MiB limit.")

        # 2. PDF Magic Header Check
        if not file_bytes.startswith(b"%PDF-"):
            raise FileValidationError("415 UNSUPPORTED_MEDIA_TYPE: File does not have valid PDF magic signature (%PDF-).")

        # 3. PyMuPDF Parsing & Page Limit Check
        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            page_count = len(doc)
            if page_count > self.MAX_PAGES:
                raise FileValidationError(f"422 TOO_MANY_PAGES: PDF has {page_count} pages, exceeding 1000 page limit.")
        except Exception as exc:
            if "TOO_MANY_PAGES" in str(exc) or "FILE_TOO_LARGE" in str(exc):
                raise
            raise FileValidationError(f"422 CORRUPT_OR_ENCRYPTED_PDF: Failed to parse PDF: {exc}")

        # Compute SHA-256
        sha256_hash = hashlib.sha256(file_bytes).hexdigest()

        # Extract text page by page
        extracted_pages: List[str] = []
        spans_to_create: List[Dict[str, Any]] = []

        total_extracted_chars = 0
        for page_idx in range(page_count):
            page = doc[page_idx]
            page_text = page.get_text("text") or ""
            extracted_pages.append(page_text)
            total_extracted_chars += len(page_text.strip())

            # Break into paragraphs/spans with char offsets
            paragraphs = page_text.split("\n\n")
            current_offset = 0
            for para in paragraphs:
                p_clean = para.strip()
                if len(p_clean) >= 15:
                    p_start = page_text.find(para, current_offset)
                    p_end = p_start + len(para) if p_start >= 0 else current_offset + len(para)
                    current_offset = p_end

                    spans_to_create.append({
                        "page_index_0": page_idx,
                        "char_start": max(0, p_start),
                        "char_end": max(0, p_end),
                        "verbatim_excerpt": p_clean,
                        "excerpt_sha256": hashlib.sha256(p_clean.encode("utf-8")).hexdigest()
                    })

        doc.close()

        # Text quality check: If selectable text < 30 chars, mark INCOMPLETE_TEXT (AT-20)
        extraction_status = "SUCCESS" if total_extracted_chars >= 30 else "INCOMPLETE_TEXT"

        # Check existing source
        doc_source = (
            self.session.query(DocumentSource)
            .filter_by(tenant_id=tenant_id, collection_id=collection_id, name=filename)
            .first()
        )
        if not doc_source:
            doc_source = DocumentSource(
                tenant_id=tenant_id,
                collection_id=collection_id,
                name=filename,
                created_by=actor_id,
                status="ACTIVE"
            )
            self.session.add(doc_source)
            self.session.flush()

        # Create immutable SourceRevision
        rev_count = len(doc_source.revisions) if doc_source.revisions else 0
        warnings_list = [{"code": "INCOMPLETE_TEXT", "message": "Scanned document with non-selectable text"}] if extraction_status == "INCOMPLETE_TEXT" else []
        s_rev = SourceRevision(
            tenant_id=tenant_id,
            document_source_id=doc_source.id,
            revision_no=rev_count + 1,
            object_key=f"sources/{tenant_id}/{doc_source.id}/rev_{rev_count + 1}.pdf",
            sha256=sha256_hash,
            mime_type="application/pdf",
            bytes=size,
            page_count=page_count,
            text_extraction_status=extraction_status,
            warnings_json=json.dumps(warnings_list),
            extracted_text="\n\n--- PAGE BREAK ---\n\n".join(extracted_pages)
        )
        self.session.add(s_rev)
        self.session.flush()

        # Persist exact SourceSpans
        for span_data in spans_to_create:
            span = SourceSpan(
                tenant_id=tenant_id,
                source_revision_id=s_rev.id,
                source_sha256=sha256_hash,
                page_index_0=span_data["page_index_0"],
                char_start=span_data["char_start"],
                char_end=span_data["char_end"],
                verbatim_excerpt=span_data["verbatim_excerpt"],
                excerpt_sha256=span_data["excerpt_sha256"],
                extraction_method="PYMUPDF_EXACT"
            )
            self.session.add(span)

        self.session.commit()
        return s_rev

    def ingest_uploaded_pdf(
        self,
        tenant_id: str,
        collection_id: str,
        filename: str,
        file_bytes: bytes,
        actor_id: str
    ) -> Tuple[DocumentSource, SourceRevision, List[SourceSpan]]:
        """Convenience method returning (doc_source, revision, spans)."""
        s_rev = self.intake_pdf(tenant_id, collection_id, filename, file_bytes, actor_id)
        doc = self.session.query(DocumentSource).filter_by(id=s_rev.document_source_id).first()
        spans = self.session.query(SourceSpan).filter_by(source_revision_id=s_rev.id).all()
        return doc, s_rev, spans
