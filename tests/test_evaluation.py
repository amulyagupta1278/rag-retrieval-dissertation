"""Unit tests for the evaluation layer (metrics)."""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.evaluation.metrics import (
    compute_mrr,
    compute_mrr_at_k,
    compute_recall_at_k,
    compute_ndcg_at_k,
    compute_precision_at_k,
    compute_all_metrics,
)


class TestMRR:
    def test_first_position(self):
        assert compute_mrr(["a", "b", "c"], {"a"}) == pytest.approx(1.0)

    def test_second_position(self):
        assert compute_mrr(["x", "a", "c"], {"a"}) == pytest.approx(0.5)

    def test_not_found(self):
        assert compute_mrr(["x", "y", "z"], {"a"}) == pytest.approx(0.0)

    def test_empty_gold(self):
        assert compute_mrr(["a", "b"], set()) == pytest.approx(0.0)

    def test_cutoffs_differ_when_first_relevant_is_between_six_and_ten(self):
        ranked = [f"chunk_{index}" for index in range(1, 11)]
        gold = {"chunk_7"}
        assert compute_mrr_at_k(ranked, gold, 5) == 0.0
        assert compute_mrr_at_k(ranked, gold, 10) == pytest.approx(1 / 7)


class TestRecallAtK:
    def test_full_recall(self):
        assert compute_recall_at_k(["a", "b", "c"], {"a", "b"}, k=2) == pytest.approx(1.0)

    def test_partial_recall(self):
        assert compute_recall_at_k(["a", "x", "y"], {"a", "b"}, k=3) == pytest.approx(0.5)

    def test_zero_recall(self):
        assert compute_recall_at_k(["x", "y", "z"], {"a"}, k=3) == pytest.approx(0.0)

    def test_k_less_than_gold(self):
        # Only k=1 retrieved, gold has 2 → recall = 0.5 if gold[0] retrieved
        assert compute_recall_at_k(["a", "b"], {"a", "b"}, k=1) == pytest.approx(0.5)


class TestNDCGAtK:
    def test_perfect_ranking(self):
        # Single gold item at rank 1 → nDCG = 1.0
        assert compute_ndcg_at_k(["a", "b", "c"], {"a"}, k=3) == pytest.approx(1.0)

    def test_gold_at_rank_2(self):
        dcg = 1.0 / math.log2(3)   # rank 2 → i=2
        idcg = 1.0 / math.log2(2)  # ideal: rank 1
        assert compute_ndcg_at_k(["x", "a", "b"], {"a"}, k=3) == pytest.approx(dcg / idcg, rel=1e-4)

    def test_no_gold_retrieved(self):
        assert compute_ndcg_at_k(["x", "y"], {"a"}, k=2) == pytest.approx(0.0)


class TestPrecisionAtK:
    def test_all_relevant(self):
        assert compute_precision_at_k(["a", "b"], {"a", "b"}, k=2) == pytest.approx(1.0)

    def test_half_relevant(self):
        assert compute_precision_at_k(["a", "x"], {"a", "b"}, k=2) == pytest.approx(0.5)

    def test_k_zero(self):
        assert compute_precision_at_k(["a"], {"a"}, k=0) == pytest.approx(0.0)


class TestComputeAllMetrics:
    def _make_run(self, qid: str, chunk_ids: list[str]) -> dict:
        return {
            "query_id": qid,
            "query_text": "test query",
            "retriever": "test",
            "top_k": 10,
            "results": [{"chunk_id": cid} for cid in chunk_ids],
            "total_latency_ms": 10.0,
        }

    def test_aggregate(self):
        runs = [
            self._make_run("q1", ["a", "b"]),
            self._make_run("q2", ["c", "a"]),
        ]
        qrels = {"q1": {"a": 1}, "q2": {"c": 1}}
        bundle = compute_all_metrics(runs, qrels, k_values=[1, 5], retriever="test")
        assert bundle.mrr == pytest.approx(1.0)
        assert bundle.recall_at_k[1] == pytest.approx(1.0)
