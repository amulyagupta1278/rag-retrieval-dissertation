from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/evaluate_phase6_seed42.py"
SPEC = importlib.util.spec_from_file_location("evaluate_phase6_seed42", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_metric_hand_fixtures() -> None:
    gains = {"a": 2, "b": 1}
    rank1 = MODULE.query_metrics(["a", "x", "b", "y", "z"], gains)
    assert rank1["mrr_at_5"] == 1.0
    assert rank1["recall_at_5"] == 1.0
    assert rank1["complete_evidence_recall_at_5"] == 1.0
    cutoff = MODULE.query_metrics(["x1", "x2", "x3", "x4", "a", "b"], gains)
    assert cutoff["mrr_at_5"] == pytest.approx(0.2)
    assert cutoff["recall_at_5"] == 0.5
    after = MODULE.query_metrics(["x1", "x2", "x3", "x4", "x5", "a"], {"a": 2})
    assert after["mrr_at_5"] == 0.0
    assert after["mrr_at_10"] == pytest.approx(1 / 6)
    miss = MODULE.query_metrics(["x1", "x2", "x3", "x4", "x5"], {"a": 2})
    assert miss["hit_rate_at_5"] == 0.0
    assert miss["graded_ndcg_at_10"] == 0.0


def test_metric_rejects_empty_gold_and_duplicate_results() -> None:
    with pytest.raises(ValueError, match="empty positive relevance"):
        MODULE.query_metrics(["a"], {"a": 0})
    with pytest.raises(ValueError, match="must be unique"):
        MODULE.query_metrics(["a", "a"], {"a": 2})


def test_binary_and_graded_ndcg_differ_by_definition() -> None:
    result = MODULE.query_metrics(["context", "direct"], {"direct": 2, "context": 1})
    assert result["binary_ndcg_at_10"] == 1.0
    assert result["graded_ndcg_at_10"] < 1.0


def test_holm_monotonic_adjustment() -> None:
    tests = [
        {"randomization": {"p_value": value}}
        for value in (0.01, 0.02, 0.5)
    ]
    MODULE.holm_adjust(tests)
    assert [test["holm_adjusted_p_value"] for test in tests] == pytest.approx(
        [0.03, 0.04, 0.5]
    )


def test_frozen_metric_artifacts() -> None:
    output = ROOT / "runs/v2/phase6_seed42_metrics"
    manifest_path = output / "evaluation_manifest.json"
    if not manifest_path.exists():
        pytest.skip("seed-42 evaluation command has not run yet")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["status"] == "frozen_pilot_evidence"
    assert manifest["systems"] == [
        "bm25",
        "faiss_windowed_max",
        "graph_v3_2",
        "hybrid_rrf",
        "prompt_rag_claude",
    ]
    assert manifest["category_counts"] == {
        "entity_relation": 6,
        "exact_lookup": 6,
        "multi_hop": 6,
        "paraphrase": 6,
        "synthesis": 4,
        "terminology": 6,
    }
    for path, digest in manifest["inputs"].items():
        assert MODULE.sha256_file(ROOT / path) == digest
    for path, digest in manifest["code_hashes"].items():
        assert MODULE.sha256_file(ROOT / path) == digest
    for path, digest in manifest["outputs"].items():
        assert MODULE.sha256_file(ROOT / path) == digest
    statistics_output = json.loads(
        (output / "hypothesis_aligned_statistics.json").read_text()
    )
    assert statistics_output["protocol"] == {
        "bootstrap_samples": 10_000,
        "randomizations": 10_000,
        "seed": 42,
    }
    assert statistics_output["h1_equivalence"]["primary_margin"] == [-0.05, 0.05]
    assert statistics_output["h1_equivalence"]["sensitivity_margin"] == [-0.03, 0.03]
    assert statistics_output["multiplicity"].startswith("Holm")
    changes = json.loads((output / "first_pass_to_final_metric_changes.json").read_text())
    assert len(changes["changed_labels"]) == 5
