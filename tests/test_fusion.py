import pytest

from src.retrievers.fusion import reciprocal_rank_fusion


def _run(system, ranked):
    return [{
        "query_id": "q1", "question": "test", "retriever": system,
        "total_latency_ms": 1.0,
        "results": [
            {"chunk_id": chunk, "doc_id": chunk, "text": chunk, "rank": rank, "score": 1.0 / rank}
            for rank, chunk in enumerate(ranked, 1)
        ],
    }]


def test_rrf_is_equal_weight_and_deterministic():
    runs = {"bm25": _run("bm25", ["a", "b"]), "dense": _run("dense", ["b", "a"])}
    first = reciprocal_rank_fusion(runs, rrf_k=60, input_depth=2, output_depth=2)
    second = reciprocal_rank_fusion(runs, rrf_k=60, input_depth=2, output_depth=2)
    assert first == second
    assert [item["chunk_id"] for item in first[0]["results"]] == ["a", "b"]
    assert first[0]["results"][0]["score"] == pytest.approx(1 / 61 + 1 / 62)


def test_rrf_rejects_misaligned_query_sets():
    left = _run("left", ["a"])
    right = _run("right", ["b"])
    right[0]["query_id"] = "q2"
    with pytest.raises(ValueError, match="identical query IDs"):
        reciprocal_rank_fusion({"left": left, "right": right})
