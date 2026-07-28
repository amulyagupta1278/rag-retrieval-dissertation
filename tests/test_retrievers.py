"""Unit tests for BM25 and FAISS retrievers (index build + retrieval)."""
from __future__ import annotations



import sys
import tempfile
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.retrievers.bm25_retriever import BM25Retriever
from src.retrievers.base_retriever import RetrievalResult
from src.retrievers.faiss_retriever import FAISSRetriever
from src.retrievers.graphrag_retriever import GraphRAGRetriever

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
        assert index_path.with_suffix(".pkl.config.json").exists()
        r2.validate_provenance(SAMPLE_CHUNKS, require_complete=True)

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


def test_faiss_cosine_contract_requires_normalization(tmp_path):
    with pytest.raises(ValueError, match="requires normalized"):
        FAISSRetriever(index_dir=tmp_path, similarity_metric="cosine", normalize_embeddings=False)


def test_graph_human_label_is_not_legacy_machine_key():
    assert GraphRAGRetriever.name == "graphrag"
    assert GraphRAGRetriever.human_name == "Entity-Co-occurrence Graph Retrieval"
    assert GraphRAGRetriever.human_name.lower() != GraphRAGRetriever.name


def test_graph_seed_filter_rejects_generic_hub_and_records_trace(tmp_path):
    import networkx as nx

    retriever = GraphRAGRetriever(
        graph_path=tmp_path / "graph.gpickle", nodes_path=tmp_path / "nodes.jsonl",
        edges_path=tmp_path / "edges.jsonl", seed_filtering=True,
    )
    graph = nx.Graph()
    graph.add_node("scheme", type="entity", label="scheme")
    graph.add_node("alpha mission", type="entity", label="alpha mission")
    graph.add_node("c1", type="chunk", label="c1")
    graph.add_edge("scheme", "c1")
    graph.add_edge("alpha mission", "c1")
    retriever._graph = graph
    retriever._chunk_meta = {"c1": {"doc_id": "d1", "text": "Alpha Mission supports households."}}
    retriever._extractor.extract = lambda query: ["scheme", "alpha mission"]
    results = retriever.retrieve("How does Alpha Mission scheme work?", 1)
    assert results[0].chunk_id == "c1"
    assert retriever.last_trace["selected_seeds"] == ["alpha mission"]
    assert any(item["node"] == "scheme" and item["reason"] == "generic" for item in retriever.last_trace["seed_decisions"])


def test_graph_zero_seed_lexical_fallback_is_deterministic(tmp_path):
    import networkx as nx

    retriever = GraphRAGRetriever(
        graph_path=tmp_path / "graph.gpickle", nodes_path=tmp_path / "nodes.jsonl",
        edges_path=tmp_path / "edges.jsonl", seed_filtering=True, lexical_fallback=True,
    )
    retriever._graph = nx.Graph()
    retriever._chunk_meta = {
        "c1": {"doc_id": "d1", "text": "Farmers receive drought insurance."},
        "c2": {"doc_id": "d2", "text": "Students receive scholarships."},
    }
    retriever._refresh_retrieval_metadata()
    retriever._extractor.extract = lambda query: []
    first = [item.chunk_id for item in retriever.retrieve("drought farmers", 2)]
    second = [item.chunk_id for item in retriever.retrieve("drought farmers", 2)]
    assert first == second == ["c1"]
    assert retriever.last_trace["fallback"] == "lexical"


def test_faiss_load_rejects_runtime_index_type_mismatch(tmp_path):
    import faiss
    import numpy as np

    index = faiss.IndexFlatL2(2)
    index.add(np.array([[0.0, 1.0]], dtype="float32"))
    faiss.write_index(index, str(tmp_path / "faiss.index"))
    (tmp_path / "chunk_ids.json").write_text('["c1"]', encoding="utf-8")
    (tmp_path / "config.json").write_text(json.dumps({
        "model_name": "unused", "num_chunks": 1, "index_type": "IndexFlatIP",
        "similarity_metric": "cosine", "normalize_embeddings": True,
    }), encoding="utf-8")
    chunks = tmp_path / "chunks.jsonl"
    chunks.write_text('{"chunk_id":"c1","doc_id":"d1","text":"text"}\n', encoding="utf-8")
    retriever = FAISSRetriever(
        index_dir=tmp_path, chunks_path=chunks,
        similarity_metric="cosine", normalize_embeddings=True,
    )
    with pytest.raises(RuntimeError, match="config/runtime mismatch"):
        retriever.load_index()
