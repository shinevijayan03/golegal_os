"""
AgentOS Hardware-Accelerated Hybrid GPU RAG & Dense Clause Search Engine.
Leverages NVIDIA GeForce RTX 3060 12GB VRAM (CUDA 13.3) for LangChain-driven Hybrid Retrieval.
Enforces AOS-09, AOS-16, AT-01, and NFR-AOS-03.
"""
from __future__ import annotations
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from golegal.agentos.intelligence.hybrid_rag import (
    HybridRAGEngine,
    LocalSentenceTransformersEmbeddings,
    LocalCrossEncoderReranker,
    LegalChunker
)


class GPURAGEngine(HybridRAGEngine):
    """
    Subclasses HybridRAGEngine to provide 10-Stage LangChain Hybrid Retrieval
    (Dense FAISS + BM25 + Cross-Encoder Reranker) with full backward compatibility.
    """
    def __init__(self, session: Optional[Session] = None, device: Optional[str] = None):
        super().__init__(session=session, device=device)


# Compatibility Alias
GPURAGSearcher = GPURAGEngine
