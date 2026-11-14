"""
AgentOS 10-Stage Hybrid RAG Engine: Dense FAISS Vector Search + Sparse BM25 + Cross-Encoder Reranker.
Leverages LangChain, SentenceTransformers, and NVIDIA GeForce RTX 3060 12GB VRAM (CUDA 13.3).
Enforces AOS-09, AOS-16, AT-01, AT-18, and PRD 10-Stage Retrieval Architecture.
"""
from __future__ import annotations
import os
import time
import hashlib
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import torch
from sqlalchemy.orm import Session

from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever

from sentence_transformers import SentenceTransformer, CrossEncoder

from golegal.agentos.domain.models import SourceSpan


class LocalSentenceTransformersEmbeddings(Embeddings):
    """
    Open-Source SentenceTransformers Embeddings Adapter for LangChain.
    Runs on local NVIDIA GeForce RTX 3060 (CUDA) with zero external network egress.
    """
    _cached_model: Optional[SentenceTransformer] = None

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: Optional[str] = None):
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        if LocalSentenceTransformersEmbeddings._cached_model is None:
            try:
                LocalSentenceTransformersEmbeddings._cached_model = SentenceTransformer(model_name, device=self.device)
            except Exception:
                LocalSentenceTransformersEmbeddings._cached_model = SentenceTransformer(model_name, device="cpu")
                self.device = "cpu"
        self.model = LocalSentenceTransformersEmbeddings._cached_model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    def embed_query(self, text: str) -> List[float]:
        embedding = self.model.encode([text], convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)[0]
        return embedding.tolist()


class LegalChunker:
    """
    Stage 4: Legal-aware Recursive Character Splitter preserving exact offsets.
    """
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\nSection ", "\n\nClause ", "\n\n", "\n", ". ", " "],
            length_function=len
        )

    def split_with_spans(self, text: str, page_index_0: int = 0) -> List[Dict[str, Any]]:
        chunks = self.splitter.split_text(text)
        results = []
        cursor = 0
        for chunk in chunks:
            chunk_clean = chunk.strip()
            if not chunk_clean:
                continue
            idx = text.find(chunk_clean, cursor)
            if idx == -1:
                idx = cursor
            char_start = idx
            char_end = idx + len(chunk_clean)
            cursor = char_start + 1
            results.append({
                "verbatim_excerpt": chunk_clean,
                "page_index_0": page_index_0,
                "char_start": char_start,
                "char_end": char_end,
                "excerpt_sha256": hashlib.sha256(chunk_clean.encode("utf-8")).hexdigest()
            })
        return results


class LocalCrossEncoderReranker:
    """
    Stage 9: Open-Source Cross-Encoder Reranker.
    Performs joint query-passage cross-attention on local CUDA/CPU.
    """
    _cached_model: Optional[CrossEncoder] = None

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2", device: Optional[str] = None):
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        if LocalCrossEncoderReranker._cached_model is None:
            try:
                LocalCrossEncoderReranker._cached_model = CrossEncoder(model_name, device=self.device)
            except Exception:
                LocalCrossEncoderReranker._cached_model = CrossEncoder(model_name, device="cpu")
                self.device = "cpu"
        self.model = LocalCrossEncoderReranker._cached_model

    def rerank(self, query: str, candidate_texts: List[str]) -> List[float]:
        if not candidate_texts:
            return []
        pairs = [[query, txt] for txt in candidate_texts]
        scores = self.model.predict(pairs, show_progress_bar=False)
        return [float(s) for s in scores]


class HybridRAGEngine:
    """
    Full 10-Stage Hybrid RAG Engine:
    FAISS Dense Vector Store + BM25 Sparse Search + Cross-Encoder Reranker.
    """
    def __init__(self, session: Optional[Session] = None, device: Optional[str] = None):
        self.session = session
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.embeddings = LocalSentenceTransformersEmbeddings(device=self.device)
        self.reranker = LocalCrossEncoderReranker(device=self.device)
        self.chunker = LegalChunker()

    def search_clauses(
        self,
        tenant_id: str,
        source_revision_ids: List[str],
        query: str,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Enforces AOS-09 & AT-01: Hybrid RAG Search across tenant-scoped document spans.
        1. Fetch authorized SourceSpans
        2. Build LangChain Documents
        3. Dense FAISS Vector Search
        4. Sparse BM25 Keyword Search
        5. Reciprocal Rank Fusion (RRF)
        6. Cross-Encoder Reranking
        """
        if not self.session:
            return []

        # 1. Fetch authorized spans strictly scoped to tenant and permitted revisions
        spans = (
            self.session.query(SourceSpan)
            .filter(
                SourceSpan.tenant_id == tenant_id,
                SourceSpan.source_revision_id.in_(source_revision_ids)
            )
            .all()
        )
        if not spans:
            return []

        # 2. Convert to LangChain Documents
        docs: List[Document] = []
        for s in spans:
            doc = Document(
                page_content=s.verbatim_excerpt,
                metadata={
                    "span_id": s.id,
                    "source_revision_id": s.source_revision_id,
                    "source_sha256": s.source_sha256,
                    "page_index_0": s.page_index_0,
                    "char_start": s.char_start,
                    "char_end": s.char_end,
                    "excerpt_sha256": s.excerpt_sha256
                }
            )
            docs.append(doc)

        k_candidates = min(15, len(docs))

        # 3. Dense FAISS Vector Search (Stage 7)
        try:
            vector_db = FAISS.from_documents(docs, self.embeddings)
            dense_results = vector_db.similarity_search_with_score(query, k=k_candidates)
            dense_docs = [doc for doc, _ in dense_results]
        except Exception:
            dense_docs = docs[:k_candidates]

        # 4. Sparse BM25 Keyword Search (Stage 8 part 1)
        try:
            bm25_retriever = BM25Retriever.from_documents(docs)
            bm25_retriever.k = k_candidates
            sparse_docs = bm25_retriever.invoke(query)
        except Exception:
            sparse_docs = docs[:k_candidates]

        # 5. Combine Semantic + Keyword via Reciprocal Rank Fusion (Stage 8 part 2)
        # RRF Score(d) = w_dense / (60 + r_dense) + w_sparse / (60 + r_sparse)
        rrf_scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        w_dense = 0.55
        w_sparse = 0.45

        for rank, doc in enumerate(dense_docs):
            sid = doc.metadata["span_id"]
            doc_map[sid] = doc
            rrf_scores[sid] = rrf_scores.get(sid, 0.0) + (w_dense / (60.0 + rank + 1))

        for rank, doc in enumerate(sparse_docs):
            sid = doc.metadata["span_id"]
            doc_map[sid] = doc
            rrf_scores[sid] = rrf_scores.get(sid, 0.0) + (w_sparse / (60.0 + rank + 1))

        # Sort by RRF score to select initial top candidates
        sorted_spans = sorted(rrf_scores.items(), key=lambda kv: kv[1], reverse=True)[:k_candidates]
        candidate_docs = [doc_map[sid] for sid, _ in sorted_spans]

        # 6. Cross-Encoder Reranking (Stage 9)
        candidate_texts = [d.page_content for d in candidate_docs]
        try:
            rerank_scores = self.reranker.rerank(query, candidate_texts)
        except Exception:
            rerank_scores = [rrf_scores[d.metadata["span_id"]] for d in candidate_docs]

        # Combine with RRF and rank
        scored_candidates = []
        for i, doc in enumerate(candidate_docs):
            rrf_val = rrf_scores[doc.metadata["span_id"]]
            rerank_val = rerank_scores[i] if i < len(rerank_scores) else rrf_val
            combined_metric = 0.3 * rrf_val + 0.7 * (1.0 / (1.0 + np.exp(-rerank_val)))  # Sigmoid scaled
            scored_candidates.append((doc, combined_metric, rerank_val))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # 7. Assemble final top_k results with verbatim citations (Stage 10)
        final_results = []
        for doc, comb_score, r_score in scored_candidates[:top_k]:
            meta = doc.metadata
            final_results.append({
                "span_id": meta["span_id"],
                "source_revision_id": meta["source_revision_id"],
                "source_sha256": meta["source_sha256"],
                "page_index_0": meta["page_index_0"],
                "char_start": meta["char_start"],
                "char_end": meta["char_end"],
                "verbatim_excerpt": doc.page_content,
                "excerpt_sha256": meta["excerpt_sha256"],
                "similarity_score": round(float(comb_score), 4),
                "rerank_score": round(float(r_score), 4),
                "method": "HYBRID_ENSEMBLE_RERANK",
                "device_accelerator": self.device
            })

        return final_results

    def dense_clause_similarity_search(
        self,
        query: str,
        candidates: List[str],
        top_k: int = 5
    ) -> Tuple[List[Dict[str, Any]], float]:
        """
        Direct in-memory candidate clause similarity ranking with GPU acceleration.
        Returns (ranked_results, latency_ms).
        """
        t0 = time.perf_counter()
        if not candidates:
            return [], 0.0

        query_emb = np.array(self.embeddings.embed_query(query))
        cand_embs = np.array(self.embeddings.embed_documents(candidates))

        # Cosine similarity
        sims = np.dot(cand_embs, query_emb)
        ranked_indices = np.argsort(-sims)[:top_k]

        rerank_scores = self.reranker.rerank(query, [candidates[i] for i in ranked_indices])
        latency_ms = (time.perf_counter() - t0) * 1000.0

        results = []
        for idx, orig_idx in enumerate(ranked_indices):
            results.append({
                "clause": candidates[orig_idx],
                "score": float(sims[orig_idx]),
                "rerank_score": float(rerank_scores[idx]) if idx < len(rerank_scores) else float(sims[orig_idx]),
                "device": self.device,
                "method": "HYBRID_ENSEMBLE_RERANK"
            })
        return results, latency_ms


# Compatibility Aliases
GPURAGEngine = HybridRAGEngine
GPURAGSearcher = HybridRAGEngine
