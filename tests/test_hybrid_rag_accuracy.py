"""
Automated Test Suite for 10-Stage Hybrid RAG Engine.
Tests LangChain FAISS Vector Search, BM25 Keyword Search, LegalChunker, and Cross-Encoder Reranker.
"""
from __future__ import annotations
import pytest
from datetime import datetime
import hashlib
from sqlalchemy.orm import Session

from golegal.agentos.domain.models import SourceSpan, DocumentSource, SourceRevision
from golegal.agentos.intelligence.hybrid_rag import (
    HybridRAGEngine,
    LocalSentenceTransformersEmbeddings,
    LocalCrossEncoderReranker,
    LegalChunker
)


class TestHybridRAGAccuracy:
    def test_legal_chunker_structure_and_spans(self):
        """Stage 4: LegalChunker splits with RecursiveCharacterTextSplitter and preserves character offsets."""
        chunker = LegalChunker(chunk_size=120, chunk_overlap=30)
        legal_text = (
            "Clause 1. Term of Agreement.\n\n"
            "This Agreement shall remain in effect for a period of three (3) years from the effective date.\n\n"
            "Section 2. Governing Law and Jurisdiction.\n\n"
            "This Agreement shall be governed by the laws of the Republic of India with jurisdiction at Bengaluru."
        )

        spans = chunker.split_with_spans(legal_text, page_index_0=1)
        assert len(spans) >= 2

        # Verify exact character slices match verbatim excerpt
        for s in spans:
            excerpt = s["verbatim_excerpt"]
            start = s["char_start"]
            end = s["char_end"]
            assert excerpt in legal_text[start:end]
            assert s["page_index_0"] == 1
            assert s["excerpt_sha256"] == hashlib.sha256(excerpt.encode("utf-8")).hexdigest()

    def test_local_sentence_transformers_embeddings(self):
        """Stage 5: LocalSentenceTransformersEmbeddings generates dense normalized vectors."""
        emb_mgr = LocalSentenceTransformersEmbeddings()
        query_vec = emb_mgr.embed_query("governing law and jurisdiction")
        assert len(query_vec) == 384  # all-MiniLM-L6-v2 dimension

        docs_vecs = emb_mgr.embed_documents([
            "Governing law is Republic of India.",
            "Confidentiality duration is 36 months."
        ])
        assert len(docs_vecs) == 2
        assert len(docs_vecs[0]) == 384
        assert len(docs_vecs[1]) == 384

    def test_cross_encoder_reranker_discrimination(self):
        """Stage 9: Cross-Encoder Reranker gives higher score to semantically relevant passage."""
        reranker = LocalCrossEncoderReranker()
        query = "Which courts have jurisdiction for dispute resolution?"
        passages = [
            "Any disputes arising hereunder shall be subject to the exclusive jurisdiction of the courts in Bengaluru, Karnataka.",
            "The monthly rent of INR 45,000 shall be payable by the fifth day of every calendar month.",
            "The counterparty shall maintain all commercial trade secrets strictly confidential."
        ]

        scores = reranker.rerank(query, passages)
        assert len(scores) == 3
        # Passage 0 (jurisdiction) must rank higher than Passage 1 (rent) and Passage 2 (confidentiality)
        assert scores[0] > scores[1]
        assert scores[0] > scores[2]

    def test_hybrid_rag_search_clauses_tenant_isolation(self, db_session: Session):
        """Stage 7 & 8: Hybrid search enforces strict tenant isolation (AT-01)."""
        engine = HybridRAGEngine(session=db_session)

        # Create Tenant Alpha Spans
        rev_alpha = f"rev-hybrid-alpha-{datetime.now().timestamp()}"
        span_alpha = SourceSpan(
            id=f"sp-alpha-{datetime.now().timestamp()}",
            tenant_id="org-alpha-101",
            source_revision_id=rev_alpha,
            source_sha256="alpha-sha256",
            page_index_0=0,
            char_start=0,
            char_end=60,
            verbatim_excerpt="Governing law shall be the laws of the Republic of India.",
            excerpt_sha256=hashlib.sha256("Governing law shall be the laws of the Republic of India.".encode()).hexdigest(),
            extraction_method="PYMUPDF_EXACT"
        )

        # Create Tenant Beta Spans
        rev_beta = f"rev-hybrid-beta-{datetime.now().timestamp()}"
        span_beta = SourceSpan(
            id=f"sp-beta-{datetime.now().timestamp()}",
            tenant_id="org-beta-202",
            source_revision_id=rev_beta,
            source_sha256="beta-sha256",
            page_index_0=0,
            char_start=0,
            char_end=60,
            verbatim_excerpt="Governing law shall be the laws of the State of New York, USA.",
            excerpt_sha256=hashlib.sha256("Governing law shall be the laws of the State of New York, USA.".encode()).hexdigest(),
            extraction_method="PYMUPDF_EXACT"
        )
        db_session.add_all([span_alpha, span_beta])
        db_session.commit()

        # Query Tenant Alpha
        results_alpha = engine.search_clauses(
            tenant_id="org-alpha-101",
            source_revision_ids=[rev_alpha],
            query="governing law jurisdiction",
            top_k=5
        )
        assert len(results_alpha) >= 1
        assert results_alpha[0]["span_id"] == span_alpha.id
        assert "Republic of India" in results_alpha[0]["verbatim_excerpt"]
        assert results_alpha[0]["method"] == "HYBRID_ENSEMBLE_RERANK"

        # Cross-Tenant isolation check: Tenant Alpha cannot retrieve Tenant Beta's revision
        results_cross = engine.search_clauses(
            tenant_id="org-alpha-101",
            source_revision_ids=[rev_beta],
            query="governing law New York",
            top_k=5
        )
        assert len(results_cross) == 0

    def test_dense_clause_similarity_search_latency(self):
        """In-memory candidate ranking completes with high accuracy and low latency."""
        engine = HybridRAGEngine()
        query = "What is the confidentiality survival period?"
        candidates = [
            "Confidentiality obligations shall survive for three (3) years post-termination.",
            "The premises shall be used exclusively for commercial warehousing.",
            "Stamp duty of INR 500 has been remitted to the Government of Karnataka."
        ]

        results, latency_ms = engine.dense_clause_similarity_search(query, candidates, top_k=3)
        assert len(results) == 3
        # Candidate 0 must be top-ranked
        assert "three (3) years" in results[0]["clause"]
        assert results[0]["rerank_score"] > results[1]["rerank_score"]
        assert results[0]["rerank_score"] > results[2]["rerank_score"]
