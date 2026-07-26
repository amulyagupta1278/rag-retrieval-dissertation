"""Independent read-only metric oracle; imports no production metric code."""

from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
METRICS = (
    "mrr_at_5", "mrr_at_10", "recall_at_5", "recall_at_10",
    "hit_rate_at_5", "hit_rate_at_10", "precision_at_5", "precision_at_10",
    "binary_ndcg_at_10", "graded_ndcg_at_10",
    "complete_evidence_recall_at_5", "complete_evidence_recall_at_10",
)


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def independent_metrics(ranking: list[str], gains: dict[str, int]) -> dict[str, float]:
    """Test-side balanced panel implementation using linear graded gains."""

    if not gains or not any(value > 0 for value in gains.values()):
        raise ValueError("positive gold required")
    if len(ranking) != len(set(ranking)):
        raise ValueError("duplicate ranking")
    positive = {chunk_id for chunk_id, gain in gains.items() if gain > 0}

    def mrr(k: int) -> float:
        return next((1 / rank for rank, chunk_id in enumerate(ranking[:k], 1) if chunk_id in positive), 0.0)

    def recall(k: int) -> float:
        return len(set(ranking[:k]) & positive) / len(positive)

    def ndcg(k: int, graded: bool) -> float:
        values = {chunk_id: (gain if graded else 1) for chunk_id, gain in gains.items() if gain > 0}
        dcg = sum(values.get(chunk_id, 0) / math.log2(rank + 1) for rank, chunk_id in enumerate(ranking[:k], 1))
        ideal = sorted(values.values(), reverse=True)[:k]
        idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, 1))
        return dcg / idcg

    result: dict[str, float] = {}
    for k in (5, 10):
        hits = len(set(ranking[:k]) & positive)
        result[f"mrr_at_{k}"] = mrr(k)
        result[f"recall_at_{k}"] = recall(k)
        result[f"hit_rate_at_{k}"] = float(hits > 0)
        result[f"precision_at_{k}"] = hits / k
        result[f"complete_evidence_recall_at_{k}"] = float(positive <= set(ranking[:k]))
    result["binary_ndcg_at_10"] = ndcg(10, False)
    result["graded_ndcg_at_10"] = ndcg(10, True)
    return result


def test_tiny_hand_computed_fixture() -> None:
    result = independent_metrics(["low", "x", "high"], {"high": 2, "low": 1})
    assert result["mrr_at_5"] == 1
    assert result["recall_at_5"] == 1
    assert result["hit_rate_at_5"] == 1
    assert result["precision_at_5"] == pytest.approx(2 / 5)
    assert result["complete_evidence_recall_at_5"] == 1
    expected_binary = (1 + 1 / math.log2(4)) / (1 + 1 / math.log2(3))
    expected_graded = (1 + 2 / math.log2(4)) / (2 + 1 / math.log2(3))
    assert result["binary_ndcg_at_10"] == pytest.approx(expected_binary)
    assert result["graded_ndcg_at_10"] == pytest.approx(expected_graded)


@pytest.mark.parametrize("phase", ["phase3_graph_v3_2", "phase4_hybrid"])
def test_independent_per_query_and_aggregate_recomputation(phase: str) -> None:
    run = ROOT / "runs/v2" / phase
    per_query = rows(run / "metrics/per_query_metrics.jsonl")
    qrels = rows(ROOT / "data/v2/pilot/qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl")
    gains: dict[str, dict[str, int]] = defaultdict(dict)
    for row in qrels:
        gains[row["query_id"]][row["chunk_id"]] = row["relevance"]
    recomputed: dict[str, list[dict]] = defaultdict(list)
    for row in per_query:
        ranking = [item["chunk_id"] for item in row["top10"]]
        actual = independent_metrics(ranking, gains[row["query_id"]])
        assert set(actual) == set(row["metrics"]) == set(METRICS)
        for metric in METRICS:
            assert actual[metric] == pytest.approx(row["metrics"][metric], abs=1e-12)
        recomputed[row["system"]].append({"category": row["category"], "metrics": actual})

    report = json.loads((run / "metrics/balanced_known_gold_metrics.json").read_text(encoding="utf-8"))
    for system, system_rows in recomputed.items():
        aggregate = {metric: statistics.mean(row["metrics"][metric] for row in system_rows) for metric in METRICS}
        saved_system = report["systems"][system]
        saved_aggregate = saved_system["aggregate"] if phase == "phase3_graph_v3_2" else saved_system["aggregate"]["metrics"]
        for metric in METRICS:
            assert aggregate[metric] == pytest.approx(saved_aggregate[metric], abs=1e-12)
        for category in sorted({row["category"] for row in system_rows}):
            subset = [row for row in system_rows if row["category"] == category]
            saved_category = saved_system["per_category"][category]
            saved_metrics = saved_category["metrics"]
            assert saved_category["query_n"] == len(subset)
            for metric in METRICS:
                expected = statistics.mean(row["metrics"][metric] for row in subset)
                assert expected == pytest.approx(saved_metrics[metric], abs=1e-12)
