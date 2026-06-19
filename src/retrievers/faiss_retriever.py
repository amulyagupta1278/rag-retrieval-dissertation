"""
FAISS Dense Retriever — Retrieval Layer
=========================================
Research purpose
    Dense retrieval is the de-facto default in modern RAG pipelines.
    Including it as a controlled baseline allows the dissertation to answer
    H2: "Dense retrieval performs strongly on semantically paraphrased
    questions where lexical overlap is weak."

Design choice
    SentenceTransformer embeddings + FAISS IndexFlatIP (inner product after
    L2 normalization ≡ cosine similarity). IndexFlatIP is exact (not
    approximate) at dissertation scale (< 10k chunks), so ANN error is not
    a confound. The index and metadata are saved to disk so the expensive
    embedding pass runs once and retrieval experiments replay cheaply.

Alternative approaches
    HNSW (approximate) would scale to millions of chunks but introduces an
    ANN approximation bias; not needed at dissertation scale.
    Pyserini dense retrieval wraps the same FAISS but requires Java; pure
    Python is simpler for the mid-semester milestone.

Expected strengths
    Strong semantic matching on paraphrased and meaning-preserving queries.
    Embeddings pre-computed offline; query-time latency is milliseconds.

Expected weaknesses
    Requires embedding model download (~90 MB). Underperforms on queries
    requiring exact terminology or explicit relational structure (motivating
    the BM25 and GraphRAG baselines).
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import time
from pathlib import Path
from typing import Optional

import numpy as np

from .base_retriever import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)


class FAISSRetriever(BaseRetriever):
    """
    Dense retriever using SentenceTransformer embeddings and FAISS.

    Parameters
    ----------
    model_name : str
        HuggingFace model id for sentence-transformers.
    index_path : str | Path
        Where to persist/load the FAISS index binary.
    meta_path : str | Path
        Where to persist/load chunk metadata (JSONL, one dict per chunk).
    normalize : bool
        If True, L2-normalize embeddings (cosine similarity via inner product).
    """

    name = "faiss"

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        index_path: str | Path = "indexes/faiss/faiss.index",
        meta_path: str | Path = "indexes/faiss/faiss_meta.jsonl",
        normalize: bool = True,
        batch_size: int = 64,
    ) -> None:
        self.model_name = model_name
        self.index_path = Path(index_path)
        self.meta_path = Path(meta_path)
        self.normalize = normalize
        self.batch_size = batch_size
        self._index = None
        self._meta: list[dict] = []
        self._model = None

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def build_index(self, chunks: list[dict]) -> None:
        """Embed all chunks and build a FAISS index. Saves to disk."""
        import faiss
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s", self.model_name)
        self._model = SentenceTransformer(self.model_name)

        texts = [c["text"] for c in chunks]
        self._meta = [
            {"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "text": c["text"]}
            for c in chunks
        ]

        logger.info("Encoding %d chunks (batch_size=%d)…", len(texts), self.batch_size)
        t0 = time.perf_counter()
        embeddings = self._model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=True,
            convert_to_numpy=True,
        )

        if self.normalize:
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1.0, norms)
            embeddings = embeddings / norms

        dim = embeddings.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(embeddings.astype(np.float32))

        elapsed = time.perf_counter() - t0
        logger.info("Index built: %d vectors, dim=%d, %.1fs", index.ntotal, dim, elapsed)

        self._index = index
        self._save()

    def _save(self) -> None:
        import faiss

        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        with self.meta_path.open("w", encoding="utf-8") as fh:
            for m in self._meta:
                fh.write(json.dumps(m) + "\n")
        logger.info("FAISS index saved → %s", self.index_path)

    def load_index(self) -> None:
        """Load a previously built index from disk."""
        import faiss

        if not self.index_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {self.index_path}")
        self._index = faiss.read_index(str(self.index_path))
        self._meta = []
        with self.meta_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    self._meta.append(json.loads(line))
        logger.info("FAISS index loaded: %d vectors", self._index.ntotal)

    def _ensure_model(self) -> None:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        if self._index is None:
            self.load_index()
        self._ensure_model()

        q_emb = self._model.encode([query], convert_to_numpy=True)
        if self.normalize:
            norm = np.linalg.norm(q_emb, axis=1, keepdims=True)
            q_emb = q_emb / np.where(norm == 0, 1.0, norm)

        scores, indices = self._index.search(q_emb.astype(np.float32), top_k)
        results: list[RetrievalResult] = []
        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), start=1):
            if idx < 0 or idx >= len(self._meta):
                continue
            meta = self._meta[idx]
            results.append(
                RetrievalResult(
                    chunk_id=meta["chunk_id"],
                    doc_id=meta["doc_id"],
                    text=meta["text"],
                    score=float(score),
                    rank=rank,
                    latency_ms=0.0,   # filled by retrieve_timed
                    retriever=self.name,
                )
            )
        return results
