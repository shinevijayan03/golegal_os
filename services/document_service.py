"""
GoLegal Document Store
Content-addressed persistence for every PDF artifact so a sealed contract is
generated exactly once and its SHA-256 digest is stable and verifiable.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy.orm import Session

from domain.models import Document


class DocumentService:
    def __init__(self, session: Session):
        self.session = session

    def store(self, agreement_id: str, doc_type: str, file_name: str, content: bytes,
              mime_type: str = "application/pdf", replace: bool = True) -> Document:
        """Persist a document. With replace=True an existing document of the same
        type is superseded (version incremented); otherwise a new version is appended."""
        sha = hashlib.sha256(content).hexdigest()
        existing = (
            self.session.query(Document)
            .filter_by(agreement_id=agreement_id, doc_type=doc_type)
            .order_by(Document.version.desc())
            .first()
        )
        version = 1
        if existing:
            if existing.sha256 == sha:
                return existing
            version = existing.version + 1
            if replace:
                self.session.delete(existing)
                self.session.flush()
        doc = Document(
            agreement_id=agreement_id,
            doc_type=doc_type,
            file_name=file_name,
            mime_type=mime_type,
            content=content,
            sha256=sha,
            size_bytes=len(content),
            version=version,
        )
        self.session.add(doc)
        self.session.commit()
        return doc

    def latest(self, agreement_id: str, doc_type: str) -> Optional[Document]:
        return (
            self.session.query(Document)
            .filter_by(agreement_id=agreement_id, doc_type=doc_type)
            .order_by(Document.version.desc())
            .first()
        )

    def verify(self, document: Document) -> bool:
        """Re-hash stored bytes and compare with the recorded digest (tamper evidence)."""
        return hashlib.sha256(document.content).hexdigest() == document.sha256
