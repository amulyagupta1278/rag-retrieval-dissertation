"""
BM25 Retriever — Retrieval Layer
===================================
Research purpose
    BM25 is the primary vector-free baseline. The dissertation tests H1:
    "BM25 will remain competitive on exact-match, terminology-heavy, and
    entity-specific questions because lexical signals preserve explicit term
    constraints."

Design choice
    rank-bm25 (pure Python) is chosen over Pyserini (Java dependency) for
    the mid-semester milestone. It implements BM25Okapi with tunable k1/b
    parameters and requires no Java runtime, making it easier to run in any
    Python environment. The index is serialised with pickle for offline
    reuse.

Alternative approaches
    Pyserini provides Lucene-backed BM25 with trec_eval compatibility; this
    is the stronger academic choice for the final submission but requires
    Java and heavier setup. ElasticSearch would scale to large corpora but
    adds infrastructure overhead not needed for this dissertation.

Expected strengths
    Exact term matching; interpretable; fast; no embedding computation;
    strong on terminology-heavy and acronym-heavy queries.

Expected weaknesses
    Vocabulary mismatch: queries and documents must share lexical tokens.
    Paraphrased queries degrade performance when synonyms are absent from
    the document.
"""

from __future__ import annotations

import json
import logging
import pickle
import re
import string
from pathlib import Path
from typing import Optional

from .base_retriever import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def _tokenize(text: str) -> list[str]:
    """Lowercase, remove punctuation, split on whitespace."""
    return text.lower().translate(_PUNCT_TABLE).split()


class BM25Retriever(BaseRetriever):
    """
    Sparse BM25 retriever backed by rank-bm25.

    Parameters
    ----------
    k1 : float
        BM25 term frequency saturation parameter.
    b : float
        BM25 document length normalisation parameter.
    index_path : str | Path
        Where to persist/load the pickled index.
    """

    name = "bm25"

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        index_path: str | Path = "indexes/bm25/bm25_index.pkl",
    ) -> None:
        self.k1 = k1
        self.b = b
        self.index_path = Path(index_path)
        self._bm25 = None
        self._meta: list[dict] = []   # parallel to BM25 corpus

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def build_index(self, chunks: list[dict]) -> None:
        """Tokenize all chunks and fit a BM25Okapi model."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise ImportError("Install rank-bm25: pip install rank-bm25") from exc

        self._meta = [
            {"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "text": c["text"]}
            for c in chunks
        ]
        tokenized = [_tokenize(c["text"]) for c in chunks]
        self._bm25 = BM25Okapi(tokenized, k1=self.k1, b=self.b)
        logger.info("BM25 index built: %d documents", len(tokenized))
        self._save()

    def _save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"bm25": self._bm25, "meta": self._meta}
        with self.index_path.open("wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        logger.info("BM25 index saved → %s", self.index_path)

    def load_index(self) -> None:
        if not self.index_path.exists():
            raise FileNotFoundError(f"BM25 index not found: {self.index_path}")
        with self.index_path.open("rb") as fh:
            payload = pickle.load(fh)
        self._bm25 = payload["bm25"]
        self._meta = payload["meta"]
        logger.info("BM25 index loaded: %d documents", len(self._meta))

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        if self._bm25 is None:
            self.load_index()

        tokens = _tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # Argsort descending, take top_k
        import numpy as np

        ranked = np.argsort(scores)[::-1][:top_k]
        results: list[RetrievalResult] = []
        for rank, idx in enumerate(ranked, start=1):
            if scores[idx] <= 0:
                continue
            meta = self._meta[idx]
            results.append(
                RetrievalResult(
                    chunk_id=meta["chunk_id"],
                    doc_id=meta["doc_id"],
                    text=meta["text"],
                    score=float(scores[idx]),
                    rank=rank,
                    latency_ms=0.0,
                    retriever=self.name,
                )
            )
        return results
