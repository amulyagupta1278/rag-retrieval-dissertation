#!/usr/bin/env python3
"""Descriptive uncertainty analysis for frozen 12-query Option B holdout."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/phase8_option_b_holdout"
INPUT = BASE / "retrieval/per_query.jsonl"
OUT = BASE / "analysis"
METRICS = ["mrr@10", "recall@10", "precision@10", "ndcg@10", "hit@10"]
SYSTEMS = ["bm25", "faiss_cosine", "graph_v4", "hybrid_r4"]
SEED = 42
SAMPLES = 10_000


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_ci(values: np.ndarray, rng: np.random.Generator) -> dict:
    draws = values[rng.integers(0, len(values), size=(SAMPLES, len(values)))].mean(axis=1)
    return {
        "bootstrap_samples": SAMPLES,
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "mean": float(values.mean()),
        "method": "whole-query nonparametric bootstrap percentile interval",
    }


def paired_ci(left: np.ndarray, right: np.ndarray, rng: np.random.Generator) -> dict:
    differences = left - right
    draws = differences[rng.integers(0, len(differences), size=(SAMPLES, len(differences)))].mean(axis=1)
    return {
        "bootstrap_samples": SAMPLES,
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
        "effect_left_minus_right": float(differences.mean()),
        "method": "paired whole-query nonparametric bootstrap percentile interval",
    }


def main() -> int:
    if OUT.exists() and any(OUT.iterdir()):
        raise RuntimeError("Holdout analysis exists; refuse overwrite")
    data = rows(INPUT)
    by_system = {system: sorted([row for row in data if row["system"] == system], key=lambda row: row["query_id"]) for system in SYSTEMS}
    query_ids = [row["query_id"] for row in by_system[SYSTEMS[0]]]
    if len(query_ids) != 12 or any([row["query_id"] for row in by_system[system]] != query_ids for system in SYSTEMS):
        raise RuntimeError("Holdout panel is not a complete aligned 12-query panel")
    rng = np.random.default_rng(SEED)
    intervals = {
        system: {
            metric: mean_ci(np.array([row[metric] for row in by_system[system]], dtype=float), rng)
            for metric in METRICS
        }
        for system in SYSTEMS
    }
    comparisons = {}
    for left, right in [
        ("bm25", "faiss_cosine"), ("bm25", "graph_v4"), ("bm25", "hybrid_r4"),
        ("hybrid_r4", "faiss_cosine"), ("hybrid_r4", "graph_v4"),
    ]:
        comparisons[f"{left}_minus_{right}"] = {
            metric: paired_ci(
                np.array([row[metric] for row in by_system[left]], dtype=float),
                np.array([row[metric] for row in by_system[right]], dtype=float),
                rng,
            )
            for metric in METRICS
        }
    categories = sorted({row["category"] for row in data})
    category_metrics = defaultdict(dict)
    for system in SYSTEMS:
        for category in categories:
            selected = [row for row in by_system[system] if row["category"] == category]
            category_metrics[system][category] = {
                "query_n": len(selected),
                **{metric: float(np.mean([row[metric] for row in selected])) for metric in METRICS},
            }
    result = {
        "benchmark": "phase8_option_b_holdout_v1",
        "bootstrap": {"samples": SAMPLES, "seed": SEED, "unit": "whole query preserving four-system panel"},
        "category_metrics": category_metrics,
        "confidence_intervals": intervals,
        "input_sha256": sha(INPUT),
        "interpretation": "descriptive_independent_holdout_small_n_no_decisive_hypothesis_claim",
        "paired_differences": comparisons,
        "prompt_rag": "excluded_incomplete_1_of_12_after_ambiguous_dispatch_zero_retry_stop",
        "query_n": 12,
        "systems": SYSTEMS,
    }
    OUT.mkdir(parents=True)
    output = OUT / "descriptive_statistics.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (OUT / "manifest.json").write_text(json.dumps({
        "descriptive_statistics_sha256": sha(output),
        "input_sha256": sha(INPUT),
        "status": "complete_descriptive_only",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        system: {
            metric: {"mean": intervals[system][metric]["mean"], "ci95": intervals[system][metric]["ci95"]}
            for metric in ["mrr@10", "ndcg@10", "recall@10"]
        }
        for system in SYSTEMS
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
