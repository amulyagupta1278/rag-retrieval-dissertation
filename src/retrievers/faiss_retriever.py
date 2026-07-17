"""
FAISS Dense Retriever — Retrieval Layer
=========================================
Research purpose
    Dense retrieval is the de-facto default in modern RAG pipelines.
    Including it as a controlled baseline allows the dissertation to answer
    H2: "Dense retrieval performs strongly on semantically paraphrased
    questions where lexical overlap is weak."

Design choice
    SentenceTransformer embeddings + configurable exact L2/cosine search.
    IndexFlatL2 is exact (not approximate) at dissertation scale, so ANN error
    is not a confound. The index and metadata are saved to disk so the
    expensive embedding pass runs once and retrieval experiments replay cheaply.

Alternative approaches
    HNSW (approximate) would scale to millions of chunks but introduces an ANN
    approximation bias; not needed at dissertation scale. IndexFlatIP (cosine)
    is also valid but L2 is more standard for evaluation comparisons.

Expected strengths
    Strong semantic matching on paraphrased queries. Embeddings pre-computed
    offline; query-time latency is milliseconds. Exact search (no approximation).

Expected weaknesses
    Requires embedding model download (~90 MB). Underperforms on queries
    requiring exact terminology or explicit relational structure (motivating
    the BM25 and entity-co-occurrence graph baselines).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from sentence_transformers import SentenceTransformer

from .base_retriever import BaseRetriever, RetrievalResult

logger = logging.getLogger(__name__)


class FAISSRetriever(BaseRetriever):
    """
    Dense retriever using FAISS IndexFlatL2 and SentenceTransformer embeddings.

    Parameters
    ----------
    index_dir : Path | str
        Directory where index, config, and chunk metadata are stored.
    chunks_path : Path | str
        Path to the explicit corpus chunks JSONL.
    model_name : str
        HuggingFace SentenceTransformer model identifier.
    """

    name = "faiss"

    def __init__(
        self,
        index_dir: Path | str = "indexes/faiss",
        chunks_path: Path | str = "data/chunks/chunks.jsonl",
        model_name: str = "all-MiniLM-L6-v2",
        similarity_metric: str = "l2",
        normalize_embeddings: bool = False,
        query_prefix: str = "",
        passage_prefix: str = "",
        model_revision: str | None = None,
    ) -> None:
        if faiss is None:
            raise ImportError("faiss-cpu not installed. Run: pip install faiss-cpu")

        self.index_dir = Path(index_dir)
        self.chunks_path = Path(chunks_path)
        self.model_name = model_name
        if similarity_metric not in {"l2", "cosine"}:
            raise ValueError("similarity_metric must be 'l2' or 'cosine'")
        if similarity_metric == "cosine" and not normalize_embeddings:
            raise ValueError("cosine similarity requires normalized embeddings")
        self.similarity_metric = similarity_metric
        self.normalize_embeddings = normalize_embeddings
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.model_revision = model_revision

        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.model: Optional[SentenceTransformer] = None
        self.index: Optional[object] = None
        self.chunk_ids: list[str] = []
        self.chunk_texts: dict[str, str] = {}
        self.chunk_docs: dict[str, str] = {}

    def build_index(self, chunks: list[dict]) -> None:
        """
        Build FAISS index from chunks.

        Parameters
        ----------
        chunks : list[dict]
            List of chunk dicts, each with at least 'chunk_id' and 'text'.
        """
        logger.info(f"Building FAISS index with {len(chunks)} chunks...")

        # Load embedding model
        logger.info(f"Loading SentenceTransformer model: {self.model_name}")
        model_kwargs = {"revision": self.model_revision} if self.model_revision else {}
        self.model = SentenceTransformer(self.model_name, **model_kwargs)
        embedding_dim = self.model.get_embedding_dimension()

        # Encode all chunks
        logger.info("Encoding chunk texts...")
        texts = [self.passage_prefix + chunk["text"] for chunk in chunks]
        embeddings = self.model.encode(
            texts, show_progress_bar=True, normalize_embeddings=self.normalize_embeddings,
        )
        embeddings = np.array(embeddings, dtype=np.float32)

        index_type = "IndexFlatIP" if self.similarity_metric == "cosine" else "IndexFlatL2"
        logger.info("Building %s (dim=%d)...", index_type, embedding_dim)
        self.index = faiss.IndexFlatIP(embedding_dim) if self.similarity_metric == "cosine" else faiss.IndexFlatL2(embedding_dim)
        self.index.add(embeddings)

        # Store chunk metadata
        self.chunk_ids = [chunk["chunk_id"] for chunk in chunks]
        self.chunk_texts = {chunk["chunk_id"]: chunk["text"] for chunk in chunks}
        self.chunk_docs = {chunk["chunk_id"]: chunk.get("doc_id", "") for chunk in chunks}

        # Save to disk
        logger.info("Saving index and metadata to disk...")
        faiss.write_index(self.index, str(self.index_dir / "faiss.index"))

        with open(self.index_dir / "chunk_ids.json", "w") as f:
            json.dump(self.chunk_ids, f)

        config = {
            "model_name": self.model_name,
            "embedding_dim": embedding_dim,
            "num_chunks": len(chunks),
            "index_type": index_type,
            "similarity_metric": self.similarity_metric,
            "normalize_embeddings": self.normalize_embeddings,
            "query_prefix": self.query_prefix,
            "passage_prefix": self.passage_prefix,
            "model_revision": self.model_revision,
        }
        with open(self.index_dir / "config.json", "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"✓ FAISS index built. {len(chunks)} chunks indexed.")

    def load_index(self) -> None:
        """Load index and metadata from disk."""
        logger.info("Loading FAISS index from disk...")

        index_path = self.index_dir / "faiss.index"
        if not index_path.exists():
            raise FileNotFoundError(f"Index file not found: {index_path}")

        # Load index
        self.index = faiss.read_index(str(index_path))

        # Load chunk_ids
        with open(self.index_dir / "chunk_ids.json") as f:
            self.chunk_ids = json.load(f)

        # Load config
        with open(self.index_dir / "config.json") as f:
            config = json.load(f)
        self.model_name = config["model_name"]
        actual_index_type = type(self.index).__name__
        index_type = config.get("index_type", actual_index_type)
        self.similarity_metric = config.get("similarity_metric", "cosine" if index_type == "IndexFlatIP" else "l2")
        self.normalize_embeddings = config.get("normalize_embeddings", self.similarity_metric == "cosine")
        self.query_prefix = config.get("query_prefix", "")
        self.passage_prefix = config.get("passage_prefix", "")
        self.model_revision = config.get("model_revision")
        expected_type = "IndexFlatIP" if self.similarity_metric == "cosine" else "IndexFlatL2"
        if index_type != expected_type or actual_index_type != expected_type:
            raise RuntimeError(
                f"FAISS config/runtime mismatch: config_type={index_type} "
                f"runtime_type={actual_index_type} metric={self.similarity_metric}"
            )
        if self.similarity_metric == "cosine" and not self.normalize_embeddings:
            raise RuntimeError("FAISS cosine config requires normalized embeddings")
        expected_chunks = int(config.get("num_chunks", len(self.chunk_ids)))
        if self.index.ntotal != expected_chunks or len(self.chunk_ids) != expected_chunks:
            raise RuntimeError(
                f"FAISS cardinality mismatch: index={self.index.ntotal} "
                f"ids={len(self.chunk_ids)} config={expected_chunks}"
            )

        # Load model
        logger.info(f"Loading SentenceTransformer model: {self.model_name}")
        model_kwargs = {"revision": self.model_revision} if self.model_revision else {}
        self.model = SentenceTransformer(self.model_name, **model_kwargs)

        # Load chunk metadata
        self._load_chunk_metadata()

        logger.info(f"✓ Loaded index with {len(self.chunk_ids)} chunks.")

    def _load_chunk_metadata(self) -> None:
        """Load chunk texts and document IDs from the configured corpus JSONL."""
        logger.info(f"Loading chunk metadata from {self.chunks_path}...")
        with open(self.chunks_path) as f:
            for line in f:
                chunk = json.loads(line)
                chunk_id = chunk["chunk_id"]
                self.chunk_texts[chunk_id] = chunk["text"]
                self.chunk_docs[chunk_id] = chunk.get("doc_id", "")

    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        """
        Retrieve top_k chunks for a query.

        Parameters
        ----------
        query : str
            Query text.
        top_k : int
            Number of results to return.

        Returns
        -------
        list[RetrievalResult]
            Ranked results sorted by score (descending).
        """
        if self.index is None or self.model is None:
            raise RuntimeError("Index not loaded. Call load_index() first.")

        # Encode query
        query_embedding = self.model.encode(
            [self.query_prefix + query], normalize_embeddings=self.normalize_embeddings,
        )
        query_embedding = np.array(query_embedding, dtype=np.float32)

        # Search
        distances, indices = self.index.search(query_embedding, top_k)
        distances = distances[0]
        indices = indices[0]

        # Convert distances to scores (L2 distance → similarity score)
        results = []
        for rank, (idx, distance) in enumerate(zip(indices, distances), 1):
            if idx == -1:  # Invalid result (shouldn't happen with IndexFlatL2)
                continue

            chunk_id = self.chunk_ids[idx]
            text = self.chunk_texts.get(chunk_id, "")
            doc_id = self.chunk_docs.get(chunk_id, "")

            score = float(distance) if self.similarity_metric == "cosine" else 1.0 / (1.0 + float(distance))

            results.append(
                RetrievalResult(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    text=text,
                    score=score,
                    rank=rank,
                    latency_ms=0.0,  # Set by retrieve_timed()
                    retriever=self.name,
                    extra={"raw_faiss_score": float(distance), "similarity_metric": self.similarity_metric},
                )
            )

        return results

    def write_run_file(
        self,
        queries: list[dict],
        top_k: int,
        output_path: Path | str,
    ) -> None:
        """
        Write TREC-format run file.

        Parameters
        ----------
        queries : list[dict]
            List of {"query_id": ..., "query": ...} or {"question_id": ..., "question": ...} dicts.
        top_k : int
            Number of results per query.
        output_path : Path | str
            Output path for run file (tab-separated).
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Writing run file to {output_path}...")
        with open(output_path, "w") as f:
            f.write("query_id\tQ0\tchunk_id\trank\tscore\tsystem_name\n")

            for query_dict in queries:
                query_id = query_dict.get("query_id", query_dict.get("question_id"))
                query_text = query_dict.get("query", query_dict.get("question"))

                results = self.retrieve(query_text, top_k=top_k)

                for result in results:
                    f.write(
                        f"{query_id}\tQ0\t{result.chunk_id}\t{result.rank}\t{result.score:.6f}\t{self.name}\n"
                    )

        logger.info(f"✓ Run file written to {output_path}")
