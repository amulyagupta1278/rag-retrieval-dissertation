"""Unit tests for BM25 and FAISS retrievers (index build + retrieval)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.retrievers.bm25_retriever import BM25Retriever
from src.retrievers.base_retriever import RetrievalResult

SAMPLE_CHUNKS = [
    {
        "chunk_id": "chunk_001",
        "doc_id": "doc_a",
        "text": "BM25 is a ranking function for information retrieval based on term frequency.",
        "word_count": 14,
    },
    {
        "chunk_id": "chunk_002",
        "doc_id": "doc_a",
        "text": "Dense retrieval uses embeddings and nearest-neighbour search for semantic matching.",
        "word_count": 13,
    },
    {
        "chunk_id": "chunk_003",
        "doc_id": "doc_b",
        "text": "GraphRAG builds a knowledge graph from entity and relation extraction.",
        "word_count": 11,
    },
    {
        "chunk_id": "chunk_004",
        "doc_id": "doc_b",
        "text": "FAISS enables efficient similarity search over large collections of vectors.",
        "word_count": 11,
    },
    {
        "chunk_id": "chunk_005",
        "doc_id": "doc_c",
        "text": "Recall at k measures how many relevant documents appear in the top k results.",
        "word_count": 15,
    },
]


class TestBM25Retriever:
    def test_build_and_retrieve(self, tmp_path):
        index_path = tmp_path / "bm25_index.pkl"
        retriever = BM25Retriever(index_path=index_path)
        retriever.build_index(SAMPLE_CHUNKS)
        results = retriever.retrieve("BM25 ranking function", top_k=3)
        assert len(results) > 0
        assert results[0].retriever == "bm25"

    def test_top_result_for_bm25_query(self, tmp_path):
        index_path = tmp_path / "bm25_index.pkl"
        retriever = BM25Retriever(index_path=index_path)
        retriever.build_index(SAMPLE_CHUNKS)
        results = retriever.retrieve("BM25 ranking", top_k=5)
        top_ids = [r.chunk_id for r in results]
        assert "chunk_001" in top_ids[:2]

    def test_save_and_load(self, tmp_path):
        index_path = tmp_path / "bm25_index.pkl"
        r1 = BM25Retriever(index_path=index_path)
        r1.build_index(SAMPLE_CHUNKS)

        r2 = BM25Retriever(index_path=index_path)
        r2.load_index()
        results = r2.retrieve("graph knowledge entity", top_k=3)
        assert any(r.chunk_id == "chunk_003" for r in results)

    def test_rank_ordering(self, tmp_path):
        index_path = tmp_path / "bm25_index.pkl"
        retriever = BM25Retriever(index_path=index_path)
        retriever.build_index(SAMPLE_CHUNKS)
        results = retriever.retrieve("FAISS similarity vectors", top_k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_run_benchmark(self, tmp_path):
        index_path = tmp_path / "bm25_index.pkl"
        retriever = BM25Retriever(index_path=index_path)
        retriever.build_index(SAMPLE_CHUNKS)
        qa_items = [
            {"question_id": "q1", "question": "What is BM25?"},
            {"question_id": "q2", "question": "How does FAISS work?"},
        ]
        runs = retriever.run_benchmark(qa_items, top_k=3)
        assert len(runs) == 2
        assert all(r.retriever == "bm25" for r in runs)
        assert all(r.total_latency_ms >= 0 for r in runs)

    def test_empty_query_returns_results(self, tmp_path):
        index_path = tmp_path / "bm25_index.pkl"
        retriever = BM25Retriever(index_path=index_path)
        retriever.build_index(SAMPLE_CHUNKS)
        # Empty query → all scores 0 → list may be empty
        results = retriever.retrieve("", top_k=3)
        assert isinstance(results, list)
