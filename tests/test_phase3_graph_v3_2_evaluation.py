"""Checks for frozen Graph v3.2 evaluation and blind pool expansion."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_phase3_graph_v3_2 import (
    BOOTSTRAPS,
    CATEGORIES,
    FORBIDDEN_BLIND_FIELDS,
    METRICS,
    SEED,
    paired_bootstrap,
    validate_rankings,
)
from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]
RUN = ROOT / "runs/v2/phase3_graph_v3_2"


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_phase3g_bootstrap_is_paired_deterministic_and_graph_minus_baseline() -> None:
    graph = [
        {"query_id": "q1", "metrics": {metric: 1.0 for metric in METRICS}},
        {"query_id": "q2", "metrics": {metric: 0.0 for metric in METRICS}},
    ]
    baseline = [
        {"query_id": "q1", "metrics": {metric: 0.0 for metric in METRICS}},
        {"query_id": "q2", "metrics": {metric: 0.0 for metric in METRICS}},
    ]
    first = paired_bootstrap(graph, baseline, "mrr_at_10")
    assert first == paired_bootstrap(graph, baseline, "mrr_at_10")
    assert first["point_effect_graph_minus_baseline"] == 0.5
    assert first["samples"] == BOOTSTRAPS == 10_000
    assert first["seed"] == SEED == 42
    assert first["unit"] == "whole query"


def test_rankings_reject_unknown_chunk_above_and_below_top10() -> None:
    import pytest
    qa = {"q1": {"question_id": "q1"}}
    known = {f"c{i}" for i in range(1, 51)}
    base = {"query_id": "q1", "ranking": [{"chunk_id": f"c{i}", "rank": i} for i in range(1, 51)]}
    for position in (0, 24):
        row = json.loads(json.dumps(base))
        row["ranking"][position]["chunk_id"] = "unknown"
        with pytest.raises(ValueError, match="unknown chunks"):
            validate_rankings([row], qa, known, "graph")


def test_phase3g_balanced_panel_covers_all_systems_categories_and_metrics() -> None:
    report = json.loads((RUN / "metrics/balanced_known_gold_metrics.json").read_text(encoding="utf-8"))
    assert set(report["systems"]) == {"bm25", "faiss_windowed_max", "entity_graph_v3_2"}
    for system in report["systems"].values():
        assert system["query_n"] == 34
        assert set(system["aggregate"]) == set(METRICS)
        assert tuple(system["per_category"]) == CATEGORIES
        assert sum(category["query_n"] for category in system["per_category"].values()) == 34
        assert all(set(category["metrics"]) == set(METRICS) for category in system["per_category"].values())
    coverage = report["graph_seed_coverage"]
    assert coverage["aggregate"] == {
        "mean_matched_seeds_per_query": 27 / 34,
        "no_seed_query_n": 10,
        "query_n": 34,
        "seed_coverage": 24 / 34,
        "seeded_query_n": 24,
    }
    assert coverage["per_category"]["entity_relation"]["no_seed_query_n"] == 0
    assert coverage["per_category"]["multi_hop"]["no_seed_query_n"] == 0
    assert coverage["per_category"]["paraphrase"]["no_seed_query_n"] == 6
    assert coverage["per_category"]["synthesis"]["no_seed_query_n"] == 4


def test_phase3g_taxonomy_covers_every_graph_completeness_miss() -> None:
    metrics = jsonl(RUN / "metrics/per_query_metrics.jsonl")
    graph = [row for row in metrics if row["system"] == "entity_graph_v3_2"]
    expected = {
        row["query_id"] for row in graph
        if row["metrics"]["complete_evidence_recall_at_5"] < 1
        or row["metrics"]["complete_evidence_recall_at_10"] < 1
    }
    failures = jsonl(RUN / "failure_taxonomy_at_5_and_10.jsonl")
    assert {row["query_id"] for row in failures} == expected
    assert len(failures) == 16
    assert all(row["rationale"] and row["known_gold_ids"] for row in failures)
    assert sum(row["miss_at_10"] for row in failures) == 13


def test_phase3g_pool_is_blind_unique_blank_and_preserves_504_inputs() -> None:
    blind = jsonl(RUN / "pool/provisional_blind_top10_bm25_faiss_graph_v3_2.jsonl")
    sealed = jsonl(RUN / "pool/sealed_provenance_bm25_faiss_graph_v3_2.jsonl")
    assert len(blind) == len(sealed) == 610
    assert len({(row["query_id"], row["chunk_id"]) for row in sealed}) == 610
    assert {row["display_id"] for row in blind} == {row["display_id"] for row in sealed}
    assert all(not (set(row) & FORBIDDEN_BLIND_FIELDS) for row in blind)
    assert all(not row["relevance_judgment"] and not row["reviewer_notes"] for row in blind)
    assert sha256_file(ROOT / "runs/v2/phase2a_r5_windowed/pool/provisional_blind_top10.jsonl") == "4ef28398b0394166279f9754b4127def4f625a6118c3a234ff030e2cc674052a"
    assert sha256_file(ROOT / "runs/v2/phase2a_r5_windowed/pool/sealed_provenance.jsonl") == "496cb8b18bc3ee506399a647c46122e243dc8be85a373edc0378f0fd55106af4"
    assert sha256_file(ROOT / "audits/phase2b/owner_judgments.csv") == "2dc3f2534c806d06cbf8327eb1858684efa80734e6c63f0a4163600e4969d5ad"
    assert all(
        contribution["system"] != "entity_graph_v3_1"
        for row in sealed for contribution in row["contributions"]
    )


def test_phase3g_comparisons_have_required_slices_and_no_h3_verdict() -> None:
    report = json.loads((RUN / "statistics/paired_bootstrap_graph_vs_baselines.json").read_text(encoding="utf-8"))
    assert report["inference"] == "exploratory pilot only; no final H3 verdict"
    assert set(report["comparisons"]) == {
        "entity_graph_v3_2_vs_bm25", "entity_graph_v3_2_vs_faiss_windowed_max",
    }
    for comparison in report["comparisons"].values():
        assert set(comparison) == {"aggregate", "entity_relation", "multi_hop"}
        assert all(set(slice_metrics) == set(METRICS) for slice_metrics in comparison.values())
        assert all(
            interval["samples"] == 10_000 and interval["seed"] == 42
            for slice_metrics in comparison.values() for interval in slice_metrics.values()
        )
