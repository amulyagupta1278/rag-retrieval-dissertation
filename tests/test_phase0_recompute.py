"""Hand-computed tests for Phase 0 historical metric recomputation."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "forensics" / "recompute_midsem_metrics.py"
SPEC = importlib.util.spec_from_file_location("phase0_recompute", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_relevant_at_rank_one() -> None:
    metrics = MODULE.compute_query_metrics(["gold", "x"], {"gold"})
    assert metrics.mrr_at_5 == 1.0
    assert metrics.mrr_at_10 == 1.0
    assert metrics.recall_at_5 == 1.0
    assert metrics.ndcg_at_10 == 1.0


def test_relevant_exactly_at_cutoff() -> None:
    ranked = ["a", "b", "c", "d", "gold"]
    metrics = MODULE.compute_query_metrics(ranked, {"gold"})
    assert metrics.mrr_at_5 == pytest.approx(1 / 5)
    assert metrics.mrr_at_10 == pytest.approx(1 / 5)
    assert metrics.ndcg_at_10 == pytest.approx(1 / math.log2(6))


def test_relevant_after_first_cutoff() -> None:
    ranked = [f"x{i}" for i in range(6)] + ["gold"]
    metrics = MODULE.compute_query_metrics(ranked, {"gold"})
    assert metrics.mrr_at_5 == 0.0
    assert metrics.mrr_at_10 == pytest.approx(1 / 7)
    assert metrics.recall_at_5 == 0.0
    assert metrics.recall_at_10 == 1.0


def test_multiple_relevant_chunks_binary_ndcg() -> None:
    metrics = MODULE.compute_query_metrics(["g2", "x", "g1"], {"g1", "g2"})
    expected_dcg = 1 / math.log2(2) + 1 / math.log2(4)
    expected_idcg = 1 / math.log2(2) + 1 / math.log2(3)
    assert metrics.mrr_at_5 == 1.0
    assert metrics.recall_at_5 == 1.0
    assert metrics.ndcg_at_10 == pytest.approx(expected_dcg / expected_idcg)


def test_graded_ndcg_rewards_higher_grade_first() -> None:
    gains = {"high": 2.0, "low": 1.0}
    ideal = MODULE.graded_ndcg_at_k(["high", "low"], gains, 10)
    reversed_score = MODULE.graded_ndcg_at_k(["low", "high"], gains, 10)
    assert ideal == 1.0
    expected = (1 / math.log2(2) + 2 / math.log2(3)) / (
        2 / math.log2(2) + 1 / math.log2(3)
    )
    assert reversed_score == pytest.approx(expected)
    assert reversed_score < ideal


def test_graded_ndcg_ignores_nonpositive_qrels() -> None:
    gains = {"gold": 2.0, "judged_not_relevant": 0.0}
    assert MODULE.graded_ndcg_at_k(["judged_not_relevant", "gold"], gains, 10) == pytest.approx(
        1 / math.log2(3)
    )


def test_no_relevant_results() -> None:
    metrics = MODULE.compute_query_metrics(["x", "y"], {"gold"})
    assert metrics.mrr_at_5 == 0.0
    assert metrics.mrr_at_10 == 0.0
    assert metrics.recall_at_10 == 0.0
    assert metrics.ndcg_at_10 == 0.0


def test_empty_gold_rejected() -> None:
    with pytest.raises(MODULE.ValidationError, match="empty gold"):
        MODULE.compute_query_metrics(["x"], set())


def test_duplicate_result_rejected() -> None:
    with pytest.raises(MODULE.ValidationError, match="duplicate chunk IDs"):
        MODULE.compute_query_metrics(["x", "x"], {"x"})


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _valid_inputs(tmp_path: Path) -> tuple[list[dict], list[dict], dict, dict]:
    chunks = [{"chunk_id": "c1", "doc_id": "d1", "text": "text"}]
    queries = [{"question_id": "q1", "question": "question"}]
    qrels = {"q1": {"c1": 2.0}}
    runs = {"bm25": [{"query_id": "q1", "results": [{"chunk_id": "c1"}]}]}
    return chunks, queries, qrels, runs


def test_unknown_chunk_rejected(tmp_path: Path) -> None:
    chunks, queries, qrels, runs = _valid_inputs(tmp_path)
    runs["bm25"][0]["results"][0]["chunk_id"] = "missing"
    with pytest.raises(MODULE.ValidationError, match="unknown chunk ID"):
        MODULE.evaluate(chunks, queries, qrels, runs)


def test_unknown_nonrelevant_qrel_chunk_rejected(tmp_path: Path) -> None:
    chunks, queries, qrels, runs = _valid_inputs(tmp_path)
    qrels["q1"]["missing"] = 0.0
    with pytest.raises(MODULE.ValidationError, match="qrels.*unknown chunks"):
        MODULE.evaluate(chunks, queries, qrels, runs)


def test_missing_query_rejected(tmp_path: Path) -> None:
    chunks, queries, qrels, runs = _valid_inputs(tmp_path)
    runs["bm25"] = []
    with pytest.raises(MODULE.ValidationError, match="query set mismatch"):
        MODULE.evaluate(chunks, queries, qrels, runs)


def test_missing_qrels_query_rejected(tmp_path: Path) -> None:
    chunks, queries, _, runs = _valid_inputs(tmp_path)
    with pytest.raises(MODULE.ValidationError, match="qrels query set mismatch"):
        MODULE.evaluate(chunks, queries, {}, runs)


def test_duplicate_query_id_rejected(tmp_path: Path) -> None:
    chunks, queries, qrels, runs = _valid_inputs(tmp_path)
    runs["bm25"].append(dict(runs["bm25"][0]))
    with pytest.raises(MODULE.ValidationError, match="duplicate query_id"):
        MODULE.evaluate(chunks, queries, qrels, runs)


def test_empty_run_file_rejected(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(MODULE.ValidationError, match="is empty"):
        MODULE.load_jsonl(path, "run bm25")


def test_malformed_relevance_rejected(tmp_path: Path) -> None:
    path = tmp_path / "qrels.tsv"
    path.write_text("query_id\t0\tchunk_id\trelevance\nq1\t0\tc1\tnan-value\n", encoding="utf-8")
    with pytest.raises(MODULE.ValidationError, match="not numeric"):
        MODULE.load_qrels(path)


def test_output_collision_requires_overwrite(tmp_path: Path) -> None:
    chunks = tmp_path / "chunks.jsonl"
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.tsv"
    summary = tmp_path / "summary.csv"
    run = tmp_path / "run.jsonl"
    output = tmp_path / "output"
    _write_jsonl(chunks, [{"chunk_id": "c1", "doc_id": "d1", "text": "text"}])
    _write_jsonl(queries, [{"question_id": "q1", "question": "question"}])
    qrels.write_text("query_id\t0\tchunk_id\trelevance\nq1\t0\tc1\t2\n", encoding="utf-8")
    summary.write_text(
        "Retriever,MRR@5,MRR@10,Recall@5,Recall@10,nDCG@10\n"
        "BM25,1,1,1,1,1\n",
        encoding="utf-8",
    )
    _write_jsonl(run, [{"query_id": "q1", "results": [{"chunk_id": "c1"}]}])
    output.mkdir()
    (output / "existing.txt").write_text("preserve", encoding="utf-8")
    argv = [
        "--chunks", str(chunks), "--queries", str(queries), "--qrels", str(qrels),
        "--reported-summary", str(summary), "--run", f"bm25={run}",
        "--output-dir", str(output),
    ]
    with pytest.raises(MODULE.ValidationError, match="collision"):
        MODULE.main(argv)
