"""Deterministic query-level metrics and paired significance tests."""

from __future__ import annotations

import csv
import random
from pathlib import Path

from .metrics import compute_mrr_at_k, compute_ndcg_at_k, compute_recall_at_k


def query_level_metrics(
    runs: list[dict], qrels: dict[str, dict[str, int]], k_values: tuple[int, ...] = (5, 10),
) -> dict[str, dict[str, float]]:
    """Return one auditable metric row per query; reject duplicate run IDs."""
    output: dict[str, dict[str, float]] = {}
    for run in runs:
        query_id = run["query_id"]
        if query_id in output:
            raise ValueError(f"Duplicate query in run: {query_id}")
        ranked = [result["chunk_id"] for result in run.get("results", [])]
        gold = {chunk_id for chunk_id, relevance in qrels.get(query_id, {}).items() if relevance > 0}
        row: dict[str, float] = {"latency_ms": float(run.get("total_latency_ms", 0.0))}
        for k in k_values:
            row[f"mrr_at_{k}"] = compute_mrr_at_k(ranked, gold, k)
            row[f"recall_at_{k}"] = compute_recall_at_k(ranked, gold, k)
            row[f"ndcg_at_{k}"] = compute_ndcg_at_k(ranked, gold, k)
        output[query_id] = row
    return output


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def paired_bootstrap(
    left: dict[str, dict[str, float]], right: dict[str, dict[str, float]], metric: str,
    *, samples: int = 10_000, seed: int = 42,
) -> dict[str, float | int]:
    """Paired percentile-bootstrap CI for mean(left - right)."""
    if set(left) != set(right):
        raise ValueError("Paired bootstrap requires identical query IDs")
    query_ids = sorted(left)
    if not query_ids:
        raise ValueError("No shared query IDs for paired bootstrap")
    differences = [left[qid][metric] - right[qid][metric] for qid in query_ids]
    observed = sum(differences) / len(differences)
    rng = random.Random(seed)
    bootstrap_means = [
        sum(differences[rng.randrange(len(differences))] for _ in differences) / len(differences)
        for _ in range(samples)
    ]
    return {
        "num_queries": len(query_ids), "samples": samples, "seed": seed,
        "mean_difference": observed,
        "ci95_low": _percentile(bootstrap_means, 0.025),
        "ci95_high": _percentile(bootstrap_means, 0.975),
        "absolute_effect_size": abs(observed),
    }


def bootstrap_mean_ci(
    rows: dict[str, dict[str, float]], metric: str, *, samples: int = 10_000, seed: int = 42,
) -> dict[str, float | int]:
    """Percentile-bootstrap confidence interval for one system mean."""
    values = [rows[qid][metric] for qid in sorted(rows)]
    if not values:
        raise ValueError("Cannot bootstrap an empty metric set")
    rng = random.Random(seed)
    means = [
        sum(values[rng.randrange(len(values))] for _ in values) / len(values)
        for _ in range(samples)
    ]
    return {
        "num_queries": len(values), "samples": samples, "seed": seed,
        "mean": sum(values) / len(values),
        "ci95_low": _percentile(means, 0.025),
        "ci95_high": _percentile(means, 0.975),
    }


def paired_randomization_test(
    left: dict[str, dict[str, float]], right: dict[str, dict[str, float]], metric: str,
    *, samples: int = 10_000, seed: int = 42,
) -> dict[str, float | int]:
    """Two-sided paired randomization test using deterministic random sign flips."""
    if set(left) != set(right):
        raise ValueError("Paired randomization requires identical query IDs")
    query_ids = sorted(left)
    if not query_ids:
        raise ValueError("No shared query IDs for paired randomization")
    differences = [left[qid][metric] - right[qid][metric] for qid in query_ids]
    observed = abs(sum(differences) / len(differences))
    rng = random.Random(seed)
    extreme = 0
    for _ in range(samples):
        randomized = abs(sum(value if rng.random() < 0.5 else -value for value in differences) / len(differences))
        if randomized >= observed - 1e-15:
            extreme += 1
    return {
        "num_queries": len(query_ids), "samples": samples, "seed": seed,
        "observed_absolute_difference": observed,
        "p_value": (extreme + 1) / (samples + 1),
    }


def paired_noninferiority(
    left: dict[str, dict[str, float]], right: dict[str, dict[str, float]], metric: str,
    *, margin: float, samples: int = 10_000, seed: int = 42,
) -> dict[str, float | int | bool]:
    """One-sided percentile-bootstrap non-inferiority decision for left-right."""
    if margin < 0:
        raise ValueError("Non-inferiority margin must be non-negative")
    if set(left) != set(right) or not left:
        raise ValueError("Non-inferiority requires identical non-empty query IDs")
    query_ids = sorted(left)
    differences = [left[qid][metric] - right[qid][metric] for qid in query_ids]
    observed = sum(differences) / len(differences)
    rng = random.Random(seed)
    means = [
        sum(differences[rng.randrange(len(differences))] for _ in differences) / len(differences)
        for _ in range(samples)
    ]
    lower = _percentile(means, 0.05)
    return {
        "num_queries": len(query_ids), "samples": samples, "seed": seed,
        "margin": margin, "mean_difference": observed,
        "one_sided_ci95_low": lower,
        "noninferior": observed >= -margin and lower >= -margin,
    }


def holm_bonferroni(p_values: dict[str, float], alpha: float = 0.05) -> dict[str, dict]:
    """Return Holm-adjusted p-values and reject decisions."""
    if not 0 < alpha < 1:
        raise ValueError("alpha must be between 0 and 1")
    if any(not 0 <= value <= 1 for value in p_values.values()):
        raise ValueError("p-values must be between 0 and 1")
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, (total - index) * value))
        adjusted[name] = running
    return {
        name: {
            "raw_p_value": p_values[name],
            "adjusted_p_value": adjusted[name],
            "reject_null": adjusted[name] <= alpha,
        }
        for name in sorted(p_values)
    }


def save_query_metrics_csv(
    systems: dict[str, dict[str, dict[str, float]]], path: str | Path,
    category_by_id: dict[str, str] | None = None, split_by_id: dict[str, str] | None = None,
) -> None:
    """Write long-form query metrics for audit and paired analysis."""
    category_by_id = category_by_id or {}
    split_by_id = split_by_id or {}
    fields = [
        "system", "query_id", "category", "split", "mrr_at_5", "mrr_at_10",
        "recall_at_5", "recall_at_10", "ndcg_at_5", "ndcg_at_10", "latency_ms",
    ]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for system, rows in sorted(systems.items()):
            for query_id, metrics in sorted(rows.items()):
                writer.writerow({
                    "system": system, "query_id": query_id,
                    "category": category_by_id.get(query_id, "unknown"),
                    "split": split_by_id.get(query_id, "unknown"),
                    **{field: metrics.get(field, 0.0) for field in fields[4:]},
                })
