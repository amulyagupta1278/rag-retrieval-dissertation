#!/usr/bin/env python3
"""Evaluate five frozen retrieval rankings on final seed-42 Phase 6 qrels."""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402

SEED = 42
BOOTSTRAPS = 10_000
RANDOMIZATIONS = 10_000
METRICS = (
    "mrr_at_5",
    "mrr_at_10",
    "recall_at_5",
    "recall_at_10",
    "hit_rate_at_5",
    "hit_rate_at_10",
    "precision_at_5",
    "precision_at_10",
    "binary_ndcg_at_10",
    "graded_ndcg_at_10",
    "complete_evidence_recall_at_5",
    "complete_evidence_recall_at_10",
)
CATEGORIES = (
    "entity_relation",
    "exact_lookup",
    "multi_hop",
    "paraphrase",
    "synthesis",
    "terminology",
)
EXPECTED_RANKING_HASHES = {
    "bm25": "93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a",
    "faiss_windowed_max": "7e419626d2e7d00efaedfa9f1ce0dda01760dbce5c901b214e992e32df597115",
    "graph_v3_2": "68ad05ff4b600fa549f957b4bd44579af7e9d6addc2ddebff3f71a4584adc59a",
    "hybrid_rrf": "6570030a1c12edb38ff5c4e33b5dedb5d2fa83a05aa9a01ecd768bcf4edce249",
    "prompt_rag_claude": "e665aa4dc80b468a0fc2af06173ab0e6963786a578653c9a9083e6ffa6b1e04f",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL row must be object at {path}:{line_number}")
        rows.append(value)
    if not rows:
        raise ValueError(f"empty JSONL: {path}")
    return rows


def percentile(values: Sequence[float], percent: float) -> float:
    """Linear percentile matching common percentile interpolation."""
    if not values:
        raise ValueError("percentile requires non-empty values")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def query_metrics(ranked: Sequence[str], gains: dict[str, int]) -> dict[str, float]:
    """Calculate frozen balanced panel for one query."""
    relevant = {chunk_id for chunk_id, grade in gains.items() if grade > 0}
    if not relevant:
        raise ValueError("query has empty positive relevance set")
    if len(ranked) != len(set(ranked)):
        raise ValueError("ranked chunk IDs must be unique")

    def mrr(cutoff: int) -> float:
        return next(
            (
                1.0 / rank
                for rank, chunk_id in enumerate(ranked[:cutoff], 1)
                if chunk_id in relevant
            ),
            0.0,
        )

    def recall(cutoff: int) -> float:
        return len(set(ranked[:cutoff]) & relevant) / len(relevant)

    def hit(cutoff: int) -> float:
        return float(bool(set(ranked[:cutoff]) & relevant))

    def precision(cutoff: int) -> float:
        return sum(chunk_id in relevant for chunk_id in ranked[:cutoff]) / cutoff

    def ndcg(cutoff: int, *, graded: bool) -> float:
        observed = [
            gains.get(chunk_id, 0) if graded else int(chunk_id in relevant)
            for chunk_id in ranked[:cutoff]
        ]
        dcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(observed, 1))
        ideal = sorted(
            (gains[chunk_id] if graded else 1 for chunk_id in relevant), reverse=True
        )[:cutoff]
        idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal, 1))
        return dcg / idcg

    def complete(cutoff: int) -> float:
        return float(relevant.issubset(set(ranked[:cutoff])))

    return {
        "mrr_at_5": mrr(5),
        "mrr_at_10": mrr(10),
        "recall_at_5": recall(5),
        "recall_at_10": recall(10),
        "hit_rate_at_5": hit(5),
        "hit_rate_at_10": hit(10),
        "precision_at_5": precision(5),
        "precision_at_10": precision(10),
        "binary_ndcg_at_10": ndcg(10, graded=False),
        "graded_ndcg_at_10": ndcg(10, graded=True),
        "complete_evidence_recall_at_5": complete(5),
        "complete_evidence_recall_at_10": complete(10),
    }


def mean_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        raise ValueError("cannot aggregate empty query slice")
    return {
        metric: statistics.fmean(row["metrics"][metric] for row in rows)
        for metric in METRICS
    }


def paired_bootstrap(
    left: Sequence[dict[str, Any]],
    right: Sequence[dict[str, Any]],
    metric: str,
    *,
    seed: int = SEED,
    samples: int = BOOTSTRAPS,
) -> dict[str, Any]:
    """Paired whole-query percentile bootstrap for left minus right."""
    if len(left) != len(right) or not left:
        raise ValueError("paired bootstrap requires non-empty equal-length slices")
    if [row["query_id"] for row in left] != [row["query_id"] for row in right]:
        raise ValueError("paired bootstrap query order differs")
    differences = [
        a["metrics"][metric] - b["metrics"][metric] for a, b in zip(left, right)
    ]
    rng = random.Random(seed)
    means = [
        statistics.fmean(differences[rng.randrange(len(differences))] for _ in differences)
        for _ in range(samples)
    ]
    return {
        "bootstrap_samples": samples,
        "ci95": [percentile(means, 2.5), percentile(means, 97.5)],
        "effect_left_minus_right": statistics.fmean(differences),
        "method": "paired whole-query percentile bootstrap",
        "query_n": len(differences),
        "seed": seed,
    }


def paired_randomization(
    left: Sequence[dict[str, Any]],
    right: Sequence[dict[str, Any]],
    metric: str,
    *,
    seed: int = SEED,
    samples: int = RANDOMIZATIONS,
) -> dict[str, Any]:
    """One-sided paired sign-randomization test for left > right."""
    if len(left) != len(right) or not left:
        raise ValueError("paired randomization requires non-empty equal-length slices")
    differences = [
        a["metrics"][metric] - b["metrics"][metric] for a, b in zip(left, right)
    ]
    observed = statistics.fmean(differences)
    rng = random.Random(seed)
    exceedances = 0
    for _ in range(samples):
        randomized = statistics.fmean(
            value if rng.getrandbits(1) else -value for value in differences
        )
        if randomized >= observed - 1e-15:
            exceedances += 1
    return {
        "alternative": "left_greater_than_right",
        "effect_left_minus_right": observed,
        "method": "paired sign-randomization Monte Carlo test",
        "p_value": (exceedances + 1) / (samples + 1),
        "query_n": len(differences),
        "randomizations": samples,
        "seed": seed,
    }


def holm_adjust(tests: list[dict[str, Any]]) -> None:
    """Add Holm-adjusted p-values in place as one confirmatory family."""
    ordered = sorted(enumerate(tests), key=lambda item: item[1]["randomization"]["p_value"])
    running = 0.0
    total = len(tests)
    for position, (original_index, test) in enumerate(ordered):
        raw = test["randomization"]["p_value"]
        running = max(running, min(1.0, (total - position) * raw))
        tests[original_index]["holm_adjusted_p_value"] = running
        tests[original_index]["holm_reject_at_0_05"] = running <= 0.05


def load_qrels(path: Path, query_ids: set[str], chunk_ids: set[str]) -> dict[str, dict[str, int]]:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    row_n = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 4 or fields[1] != "0":
            raise ValueError(f"malformed qrel at {path}:{line_number}")
        query_id, _, chunk_id, raw_grade = fields
        if query_id not in query_ids or chunk_id not in chunk_ids:
            raise ValueError(f"unknown qrel identifier at {path}:{line_number}")
        if raw_grade not in {"0", "1", "2"}:
            raise ValueError(f"malformed relevance at {path}:{line_number}")
        if chunk_id in qrels[query_id]:
            raise ValueError(f"duplicate qrel pair at {path}:{line_number}")
        qrels[query_id][chunk_id] = int(raw_grade)
        row_n += 1
    if row_n != 755 or set(qrels) != query_ids:
        raise ValueError("final pooled qrels must contain 755 rows and all 34 queries")
    for query_id, gains in qrels.items():
        if not any(grade > 0 for grade in gains.values()):
            raise ValueError(f"query has no positive qrel: {query_id}")
    return dict(qrels)


def load_ranking(
    path: Path,
    system: str,
    query_ids: set[str],
    chunk_ids: set[str],
    qrels: dict[str, dict[str, int]],
) -> dict[str, list[str]]:
    expected_hash = EXPECTED_RANKING_HASHES[system]
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise ValueError(
            f"{system} frozen ranking hash mismatch: expected {expected_hash}, got {actual_hash}"
        )
    result: dict[str, list[str]] = {}
    for row in read_jsonl(path):
        query_id = row.get("query_id")
        if query_id in result:
            raise ValueError(f"duplicate ranking query: {system} {query_id}")
        ranking = row.get("ranking")
        if query_id not in query_ids or not isinstance(ranking, list) or len(ranking) > 50:
            raise ValueError(f"invalid ranking row: {system} {query_id}")
        ids = [item.get("chunk_id") for item in ranking]
        ranks = [item.get("rank") for item in ranking]
        if len(ids) != len(set(ids)) or not set(ids).issubset(chunk_ids):
            raise ValueError(f"duplicate or unknown ranked chunk: {system} {query_id}")
        if ranks != list(range(1, len(ranking) + 1)):
            raise ValueError(f"non-sequential ranks: {system} {query_id}")
        if any(chunk_id not in qrels[query_id] for chunk_id in ids[:10]):
            raise ValueError(f"unjudged top-10 pair: {system} {query_id}")
        result[query_id] = ids
    if set(result) != query_ids:
        raise ValueError(f"{system} query set differs from frozen QA")
    return result


def slice_rows(
    evaluated: dict[str, list[dict[str, Any]]], system: str, categories: set[str] | None
) -> list[dict[str, Any]]:
    return [
        row
        for row in evaluated[system]
        if categories is None or row["category"] in categories
    ]


def paired_result(
    evaluated: dict[str, list[dict[str, Any]]],
    left: str,
    right: str,
    metric: str,
    categories: set[str] | None,
) -> dict[str, Any]:
    left_rows = slice_rows(evaluated, left, categories)
    right_rows = slice_rows(evaluated, right, categories)
    return {
        "bootstrap": paired_bootstrap(left_rows, right_rows, metric),
        "randomization": paired_randomization(left_rows, right_rows, metric),
    }


def efficiency_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    phase2 = json.loads(args.phase2a_efficiency.read_text(encoding="utf-8"))
    graph = json.loads(args.graph_manifest.read_text(encoding="utf-8"))
    hybrid = json.loads(args.hybrid_latency.read_text(encoding="utf-8"))
    prompt_trace = json.loads(args.prompt_trace_operational.read_text(encoding="utf-8"))
    prompt_full = json.loads(args.prompt_full_operational.read_text(encoding="utf-8"))
    bm25_size = sum(
        path.stat().st_size for path in args.bm25_index_dir.rglob("*") if path.is_file()
    )
    faiss_size = sum(
        path.stat().st_size for path in args.faiss_index_dir.rglob("*") if path.is_file()
    )
    return {
        "bm25": {
            "build_time_seconds": phase2["build_decomposition"]["bm25_total_seconds"],
            "index_size_bytes": bm25_size,
            "latency_ms": phase2["timing"]["bm25"]["total_ms"],
            "peak_memory": phase2["memory"],
        },
        "faiss_windowed_max": {
            "build_time_seconds": phase2["build_decomposition"]["faiss_total_seconds"],
            "index_size_bytes": faiss_size,
            "latency_ms": phase2["timing"]["faiss-windowed-max"]["total_ms"],
            "peak_memory": phase2["memory"],
        },
        "graph_v3_2": graph["efficiency"],
        "hybrid_rrf": {
            "additional_index_size_bytes": hybrid["index_size_bytes"]["hybrid_additional_index"],
            "component_index_size_bytes": hybrid["index_size_bytes"],
            "latency_ms": hybrid["timings"]["sequential_end_to_end_ms"],
            "latency_interpretation": hybrid["latency_interpretation"],
            "process_peak_rss_bytes": hybrid["process_peak_rss_bytes"],
        },
        "prompt_rag_claude": {
            "automatic_retries": (
                prompt_trace["automatic_retry_n"] + prompt_full["automatic_retry_n"]
            ),
            "cumulative_recorded_observed_cost_usd": prompt_full["spend"][
                "cumulative_recorded_observed_cost_usd"
            ],
            "full_recovery_26_primary_latency_ms": prompt_full["latency_ms"],
            "full_recovery_actual_input_tokens": prompt_full["recovery"]["actual_input_tokens"],
            "full_recovery_actual_output_tokens": prompt_full["recovery"]["actual_output_tokens"],
            "local_additional_index_size_bytes": 0,
            "model": prompt_full["model"],
            "note": (
                "Latency summary covers 26 recovery primary calls; trace summary covers "
                "24 calls including 8 primary and 16 repeatability calls. They are not "
                "pooled into one latency statistic."
            ),
            "trace_24_call_latency_ms": prompt_trace["latency_ms"],
            "trace_actual_input_tokens": prompt_trace["provider_usage"]["actual_input_tokens"],
            "trace_actual_output_tokens": prompt_trace["provider_usage"]["actual_output_tokens"],
        },
        "source_artifacts": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in (
                args.phase2a_efficiency,
                args.graph_manifest,
                args.hybrid_latency,
                args.prompt_trace_operational,
                args.prompt_full_operational,
            )
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--first-pass-qrels", type=Path, required=True)
    parser.add_argument("--bm25-ranking", type=Path, required=True)
    parser.add_argument("--faiss-ranking", type=Path, required=True)
    parser.add_argument("--graph-ranking", type=Path, required=True)
    parser.add_argument("--hybrid-ranking", type=Path, required=True)
    parser.add_argument("--prompt-ranking", type=Path, required=True)
    parser.add_argument("--phase2a-efficiency", type=Path, required=True)
    parser.add_argument("--graph-manifest", type=Path, required=True)
    parser.add_argument("--hybrid-latency", type=Path, required=True)
    parser.add_argument("--prompt-trace-operational", type=Path, required=True)
    parser.add_argument("--prompt-full-operational", type=Path, required=True)
    parser.add_argument("--bm25-index-dir", type=Path, required=True)
    parser.add_argument("--faiss-index-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    output_dir = args.output_dir
    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"output directory non-empty; pass --overwrite: {output_dir}")

    chunks = read_jsonl(args.chunks)
    qa = read_jsonl(args.qa)
    if len(chunks) != 140 or len(qa) != 34:
        raise ValueError("frozen corpus/query counts must be 140/34")
    chunk_ids = {row["chunk_id"] for row in chunks}
    if len(chunk_ids) != 140:
        raise ValueError("duplicate chunk IDs")
    qa_by_id = {row["question_id"]: row for row in qa}
    if len(qa_by_id) != 34:
        raise ValueError("duplicate query IDs")
    category_counts = Counter(row["category"] for row in qa)
    if category_counts != Counter(
        {
            "exact_lookup": 6,
            "terminology": 6,
            "paraphrase": 6,
            "entity_relation": 6,
            "multi_hop": 6,
            "synthesis": 4,
        }
    ):
        raise ValueError(f"unexpected category counts: {dict(category_counts)}")

    query_ids = set(qa_by_id)
    qrels = load_qrels(args.qrels, query_ids, chunk_ids)
    first_pass_qrels = load_qrels(args.first_pass_qrels, query_ids, chunk_ids)
    ranking_paths = {
        "bm25": args.bm25_ranking,
        "faiss_windowed_max": args.faiss_ranking,
        "graph_v3_2": args.graph_ranking,
        "hybrid_rrf": args.hybrid_ranking,
        "prompt_rag_claude": args.prompt_ranking,
    }
    rankings = {
        system: load_ranking(path, system, query_ids, chunk_ids, qrels)
        for system, path in ranking_paths.items()
    }

    evaluated: dict[str, list[dict[str, Any]]] = {}
    first_pass_evaluated: dict[str, list[dict[str, Any]]] = {}
    per_query_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for system, system_rankings in rankings.items():
        rows = []
        first_rows = []
        for query_id in sorted(query_ids):
            ranked = system_rankings[query_id]
            row = {
                "category": qa_by_id[query_id]["category"],
                "metrics": query_metrics(ranked, qrels[query_id]),
                "positive_qrel_n": sum(grade > 0 for grade in qrels[query_id].values()),
                "query_id": query_id,
                "system": system,
            }
            rows.append(row)
            per_query_rows.append({"row_id": f"{system}:{query_id}", **row})
            first_rows.append(
                {
                    "category": qa_by_id[query_id]["category"],
                    "metrics": query_metrics(ranked, first_pass_qrels[query_id]),
                    "query_id": query_id,
                    "system": system,
                }
            )
            positive = {
                chunk_id for chunk_id, grade in qrels[query_id].items() if grade > 0
            }
            retrieved = set(ranked[:10])
            if not positive.issubset(retrieved):
                failure_rows.append(
                    {
                        "category": qa_by_id[query_id]["category"],
                        "failure_id": f"{system}:{query_id}",
                        "missing_positive_chunk_ids": sorted(positive - retrieved),
                        "query_id": query_id,
                        "recall_at_10": row["metrics"]["recall_at_10"],
                        "system": system,
                        "taxonomy": (
                            "no_positive_in_top10"
                            if not (positive & retrieved)
                            else "incomplete_multi_evidence_top10"
                        ),
                        "top10_chunk_ids": ranked[:10],
                    }
                )
        evaluated[system] = rows
        first_pass_evaluated[system] = first_rows

    metrics: dict[str, Any] = {}
    for system, rows in evaluated.items():
        metrics[system] = {
            "aggregate": {"metrics": mean_metrics(rows), "query_n": len(rows)},
            "per_category": {
                category: {
                    "metrics": mean_metrics([row for row in rows if row["category"] == category]),
                    "query_n": category_counts[category],
                }
                for category in CATEGORIES
            },
            "retrieval_coverage": {
                "empty_ranking_n": sum(not rankings[system][query_id] for query_id in query_ids),
                "empty_ranking_per_category": {
                    category: sum(
                        not rankings[system][query_id]
                        for query_id in query_ids
                        if qa_by_id[query_id]["category"] == category
                    )
                    for category in CATEGORIES
                },
                "query_n": 34,
            },
        }

    changed_labels = []
    for query_id in sorted(query_ids):
        for chunk_id in sorted(qrels[query_id]):
            before = first_pass_qrels[query_id][chunk_id]
            after = qrels[query_id][chunk_id]
            if before != after:
                changed_labels.append(
                    {
                        "chunk_id": chunk_id,
                        "final_grade": after,
                        "first_pass_grade": before,
                        "query_id": query_id,
                    }
                )
    metric_changes: dict[str, Any] = {"changed_labels": changed_labels, "systems": {}}
    for system in rankings:
        system_changes: dict[str, Any] = {}
        for slice_name, categories in (
            ("aggregate", None),
            *((category, {category}) for category in CATEGORIES),
        ):
            before_metrics = mean_metrics(slice_rows(first_pass_evaluated, system, categories))
            after_metrics = mean_metrics(slice_rows(evaluated, system, categories))
            deltas = {
                metric: after_metrics[metric] - before_metrics[metric] for metric in METRICS
            }
            system_changes[slice_name] = {
                "after": after_metrics,
                "before": before_metrics,
                "deltas": deltas,
                "material_deltas_abs_ge_0_01": {
                    metric: value for metric, value in deltas.items() if abs(value) >= 0.01
                },
                "query_n": len(slice_rows(evaluated, system, categories)),
            }
        metric_changes["systems"][system] = system_changes

    uncertainty: dict[str, Any] = {}
    for system in rankings:
        uncertainty[system] = {}
        for slice_name, categories in (
            ("aggregate", None),
            *((category, {category}) for category in CATEGORIES),
        ):
            left = slice_rows(evaluated, system, categories)
            right = slice_rows(evaluated, "bm25", categories)
            uncertainty[system][slice_name] = {
                "comparator": "bm25",
                "metric_intervals": {
                    metric: paired_bootstrap(left, right, metric) for metric in METRICS
                },
                "query_n": len(left),
            }

    h1_left = slice_rows(evaluated, "bm25", {"exact_lookup", "terminology"})
    h1_right = slice_rows(evaluated, "faiss_windowed_max", {"exact_lookup", "terminology"})
    h1_bootstrap = paired_bootstrap(h1_left, h1_right, "mrr_at_10")
    low, high = h1_bootstrap["ci95"]
    h1 = {
        "comparison": "bm25_minus_faiss_windowed_max",
        "endpoint": "mrr_at_10",
        "primary_margin": [-0.05, 0.05],
        "primary_supported": low > -0.05 and high < 0.05,
        "query_categories": ["exact_lookup", "terminology"],
        "result": h1_bootstrap,
        "sensitivity_margin": [-0.03, 0.03],
        "sensitivity_supported": low > -0.03 and high < 0.03,
    }

    directional: list[dict[str, Any]] = []
    for metric in METRICS:
        result = paired_result(
            evaluated, "faiss_windowed_max", "bm25", metric, {"paraphrase"}
        )
        directional.append(
            {
                "comparison": "faiss_windowed_max_minus_bm25",
                "hypothesis": "H2",
                "metric": metric,
                "slice": "paraphrase",
                **result,
            }
        )
    h3_metrics = (
        "mrr_at_10",
        "recall_at_10",
        "graded_ndcg_at_10",
        "complete_evidence_recall_at_10",
    )
    for category in ("entity_relation", "multi_hop"):
        for baseline in ("bm25", "faiss_windowed_max"):
            for metric in h3_metrics:
                result = paired_result(
                    evaluated, "graph_v3_2", baseline, metric, {category}
                )
                directional.append(
                    {
                        "comparison": f"graph_v3_2_minus_{baseline}",
                        "hypothesis": "H3",
                        "metric": metric,
                        "slice": category,
                        **result,
                    }
                )
    for comparator in ("bm25", "faiss_windowed_max", "graph_v3_2", "prompt_rag_claude"):
        result = paired_result(evaluated, "hybrid_rrf", comparator, "mrr_at_10", None)
        directional.append(
            {
                "comparison": f"hybrid_rrf_minus_{comparator}",
                "hypothesis": "H4",
                "metric": "mrr_at_10",
                "slice": "aggregate",
                **result,
            }
        )
    holm_adjust(directional)
    for test in directional:
        ci_low = test["bootstrap"]["ci95"][0]
        effect = test["bootstrap"]["effect_left_minus_right"]
        test["positive_effect"] = effect > 0.0
        test["ci_excludes_zero_in_predicted_direction"] = ci_low > 0.0
        test["directional_rule_met"] = bool(
            effect > 0.0 and ci_low > 0.0 and test["holm_reject_at_0_05"]
        )
    h2_tests = [test for test in directional if test["hypothesis"] == "H2"]
    h3_tests = [test for test in directional if test["hypothesis"] == "H3"]
    h4_tests = [test for test in directional if test["hypothesis"] == "H4"]
    statistics_output = {
        "confirmatory_directional_family_size": len(directional),
        "directional_tests": directional,
        "h1_equivalence": h1,
        "inference_boundary": "pilot evidence; no final dissertation hypothesis verdict",
        "multiplicity": "Holm across all H2-H4 directional comparisons in this file",
        "exploratory_summaries": {
            "H1": (
                "supported_by_primary_equivalence_rule"
                if h1["primary_supported"]
                else "inconclusive"
            ),
            "H2": {
                "directional_metric_tests_met": sum(
                    test["directional_rule_met"] for test in h2_tests
                ),
                "directional_metric_tests_n": len(h2_tests),
                "status": (
                    "not_supported_on_pilot"
                    if not any(test["directional_rule_met"] for test in h2_tests)
                    else "metric_specific_support_only"
                ),
            },
            "H3": {
                category: {
                    "directional_tests_met": sum(
                        test["directional_rule_met"]
                        for test in h3_tests
                        if test["slice"] == category
                    ),
                    "directional_tests_n": sum(test["slice"] == category for test in h3_tests),
                    "status": (
                        "not_supported_on_pilot"
                        if not any(
                            test["directional_rule_met"]
                            for test in h3_tests
                            if test["slice"] == category
                        )
                        else "metric_specific_support_only"
                    ),
                }
                for category in ("entity_relation", "multi_hop")
            },
            "H4": {
                "all_comparators_pass": all(test["directional_rule_met"] for test in h4_tests),
                "comparisons_met": sum(test["directional_rule_met"] for test in h4_tests),
                "comparisons_n": len(h4_tests),
                "status": (
                    "supported_on_pilot"
                    if all(test["directional_rule_met"] for test in h4_tests)
                    else "not_supported_on_pilot"
                ),
            },
            "H5": "not_evaluated_generation_phase_separate",
        },
        "protocol": {
            "bootstrap_samples": BOOTSTRAPS,
            "randomizations": RANDOMIZATIONS,
            "seed": SEED,
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "balanced_metrics.json", metrics, overwrite=args.overwrite)
    write_json(
        output_dir / "paired_uncertainty_vs_bm25.json",
        uncertainty,
        overwrite=args.overwrite,
    )
    write_json(
        output_dir / "hypothesis_aligned_statistics.json",
        statistics_output,
        overwrite=args.overwrite,
    )
    write_jsonl(
        output_dir / "per_query_metrics.jsonl",
        per_query_rows,
        key="row_id",
        overwrite=args.overwrite,
    )
    write_jsonl(
        output_dir / "failure_taxonomy.jsonl",
        failure_rows,
        key="failure_id",
        overwrite=args.overwrite,
    )
    write_json(
        output_dir / "first_pass_to_final_metric_changes.json",
        metric_changes,
        overwrite=args.overwrite,
    )
    write_json(
        output_dir / "efficiency_snapshot.json",
        efficiency_snapshot(args),
        overwrite=args.overwrite,
    )

    input_paths = (
        args.chunks,
        args.qa,
        args.qrels,
        args.first_pass_qrels,
        *ranking_paths.values(),
        args.phase2a_efficiency,
        args.graph_manifest,
        args.hybrid_latency,
        args.prompt_trace_operational,
        args.prompt_full_operational,
    )
    output_paths = tuple(
        output_dir / name
        for name in (
            "balanced_metrics.json",
            "paired_uncertainty_vs_bm25.json",
            "hypothesis_aligned_statistics.json",
            "per_query_metrics.jsonl",
            "efficiency_snapshot.json",
            "failure_taxonomy.jsonl",
            "first_pass_to_final_metric_changes.json",
        )
    )
    manifest = {
        "category_counts": dict(sorted(category_counts.items())),
        "code_hashes": {
            "scripts/evaluate_phase6_seed42.py": sha256_file(
                ROOT / "scripts/evaluate_phase6_seed42.py"
            )
        },
        "git_head_at_execution": "7fe23bf9e55e36ab56b2520fc2997b86c3f6e6df",
        "inputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in input_paths},
        "metric_definitions": {
            "binary_ndcg_at_10": (
                "DCG uses gain 1 for every qrel grade >0; IDCG sorts binary gains."
            ),
            "complete_evidence_recall_at_k": (
                "1 only when every qrel grade >0 is in top-k; otherwise 0."
            ),
            "graded_ndcg_at_10": "DCG and IDCG use raw qrel grades 0,1,2 as gains.",
            "mrr_at_k": "reciprocal rank of first qrel grade >0 within top-k; else 0.",
            "precision_at_k": "count of qrel grade >0 in top-k divided by k.",
            "recall_at_k": "fraction of all qrel grade >0 retrieved in top-k.",
        },
        "outputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in output_paths},
        "phase": "phase6_seed42_final_pooled_metrics",
        "qrels_scope": (
            "complete judgments for 755-pair five-system top-10 union pool; not "
            "exhaustive over 140-chunk corpus"
        ),
        "status": "frozen_pilot_evidence",
        "systems": list(rankings),
    }
    write_json(output_dir / "evaluation_manifest.json", manifest, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "aggregate": {
                    system: value["aggregate"]["metrics"]
                    for system, value in metrics.items()
                },
                "h1": h1,
                "output_manifest_sha256": sha256_file(output_dir / "evaluation_manifest.json"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
