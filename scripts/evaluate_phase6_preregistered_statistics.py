#!/usr/bin/env python3
"""Run preregistered exploratory H1-H4 tests on corrected Phase 6 metrics."""

from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import evaluate_phase6_seed42 as evaluation  # noqa: E402
from src.utils.atomic_io import write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


def exact_paired_randomization(
    left: list[dict[str, Any]], right: list[dict[str, Any]], metric: str
) -> dict[str, Any]:
    """Exact one-sided paired sign-randomization test for left > right."""
    if len(left) != len(right) or not left:
        raise ValueError("exact paired randomization requires equal non-empty slices")
    if [row["query_id"] for row in left] != [row["query_id"] for row in right]:
        raise ValueError("paired query order differs")
    differences = [
        a["metrics"][metric] - b["metrics"][metric] for a, b in zip(left, right)
    ]
    nonzero = [value for value in differences if value != 0.0]
    observed_sum = sum(nonzero)
    exceedances = 0
    total = 1 << len(nonzero)
    for signs in itertools.product((-1.0, 1.0), repeat=len(nonzero)):
        randomized_sum = sum(sign * value for sign, value in zip(signs, nonzero))
        if randomized_sum >= observed_sum - 1e-15:
            exceedances += 1
    return {
        "alternative": "left_greater_than_right",
        "effect_left_minus_right": statistics.fmean(differences),
        "exact_exceedance_n": exceedances,
        "exact_permutation_n": total,
        "method": "exact paired sign-randomization test; zero differences omitted",
        "nonzero_pair_n": len(nonzero),
        "p_value": exceedances / total,
        "query_n": len(differences),
    }


def paired_result(
    evaluated: dict[str, list[dict[str, Any]]],
    left: str,
    right: str,
    metric: str,
    categories: set[str] | None,
) -> dict[str, Any]:
    left_rows = evaluation.slice_rows(evaluated, left, categories)
    right_rows = evaluation.slice_rows(evaluated, right, categories)
    return {
        "bootstrap": evaluation.paired_bootstrap(left_rows, right_rows, metric),
        "randomization": exact_paired_randomization(left_rows, right_rows, metric),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-query-metrics", type=Path, required=True)
    parser.add_argument("--final-qrels", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--phase-plan", type=Path, required=True)
    parser.add_argument("--corrected-spec", type=Path, required=True)
    parser.add_argument("--bm25-ranking", type=Path, required=True)
    parser.add_argument("--faiss-ranking", type=Path, required=True)
    parser.add_argument("--graph-ranking", type=Path, required=True)
    parser.add_argument("--hybrid-ranking", type=Path, required=True)
    parser.add_argument("--prompt-ranking", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError("statistics output directory non-empty; pass --overwrite")

    rows = evaluation.read_jsonl(args.per_query_metrics)
    evaluated: dict[str, list[dict[str, Any]]] = {}
    for system in evaluation.EXPECTED_RANKING_HASHES:
        selected = sorted(
            (row for row in rows if row.get("system") == system),
            key=lambda row: row["query_id"],
        )
        if len(selected) != 34 or len({row["query_id"] for row in selected}) != 34:
            raise ValueError(f"per-query metrics incomplete for {system}")
        evaluated[system] = selected
    category_counts = {
        category: sum(row["category"] == category for row in evaluated["bm25"])
        for category in evaluation.CATEGORIES
    }
    if category_counts != {
        "entity_relation": 6,
        "exact_lookup": 6,
        "multi_hop": 6,
        "paraphrase": 6,
        "synthesis": 4,
        "terminology": 6,
    }:
        raise ValueError(f"category counts differ: {category_counts}")

    h1_categories = {"exact_lookup", "terminology"}
    h1_left = evaluation.slice_rows(evaluated, "bm25", h1_categories)
    h1_right = evaluation.slice_rows(evaluated, "faiss_windowed_max", h1_categories)
    h1_primary = evaluation.paired_bootstrap(h1_left, h1_right, "mrr_at_10")
    low, high = h1_primary["ci95"]
    h1_inspection_metrics = (
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
    )
    h1 = {
        "comparison": "bm25_minus_faiss_windowed_max",
        "effect_definition": "BM25 MRR@10 minus FAISS-windowed-max MRR@10",
        "inspection_panel": {
            metric: evaluation.paired_bootstrap(h1_left, h1_right, metric)
            for metric in h1_inspection_metrics
        },
        "primary_margin": [-0.05, 0.05],
        "primary_result": h1_primary,
        "primary_supported": low > -0.05 and high < 0.05,
        "query_categories": ["exact_lookup", "terminology"],
        "query_n": 12,
        "sensitivity_margin": [-0.03, 0.03],
        "sensitivity_supported": low > -0.03 and high < 0.03,
        "verdict": (
            "supported" if low > -0.05 and high < 0.05 else "inconclusive"
        ),
    }

    tests: list[dict[str, Any]] = []
    for metric in evaluation.METRICS:
        tests.append(
            {
                "comparison": "faiss_windowed_max_minus_bm25",
                "hypothesis": "H2",
                "metric": metric,
                "slice": "paraphrase",
                **paired_result(
                    evaluated,
                    "faiss_windowed_max",
                    "bm25",
                    metric,
                    {"paraphrase"},
                ),
            }
        )
    h3_metrics = (
        "mrr_at_10",
        "recall_at_10",
        "graded_ndcg_at_10",
        "complete_evidence_recall_at_10",
    )
    for category in ("entity_relation", "multi_hop"):
        for comparator in ("bm25", "faiss_windowed_max"):
            for metric in h3_metrics:
                tests.append(
                    {
                        "comparison": f"graph_v3_2_minus_{comparator}",
                        "hypothesis": "H3",
                        "metric": metric,
                        "slice": category,
                        **paired_result(
                            evaluated,
                            "graph_v3_2",
                            comparator,
                            metric,
                            {category},
                        ),
                    }
                )
    for comparator in (
        "bm25",
        "faiss_windowed_max",
        "graph_v3_2",
        "prompt_rag_claude",
    ):
        tests.append(
            {
                "comparison": f"hybrid_rrf_minus_{comparator}",
                "hypothesis": "H4",
                "metric": "mrr_at_10",
                "slice": "aggregate",
                **paired_result(
                    evaluated, "hybrid_rrf", comparator, "mrr_at_10", None
                ),
            }
        )
    if len(tests) != 32:
        raise ValueError("preregistered directional Holm family must contain 32 tests")
    evaluation.holm_adjust(tests)
    for test in tests:
        effect = test["bootstrap"]["effect_left_minus_right"]
        ci_low = test["bootstrap"]["ci95"][0]
        test["positive_effect"] = effect > 0.0
        test["ci_excludes_zero_in_predicted_direction"] = ci_low > 0.0
        test["directional_rule_met"] = bool(
            effect > 0.0 and ci_low > 0.0 and test["holm_reject_at_0_05"]
        )

    h2 = [test for test in tests if test["hypothesis"] == "H2"]
    h3 = [test for test in tests if test["hypothesis"] == "H3"]
    h4 = [test for test in tests if test["hypothesis"] == "H4"]
    summaries = {
        "H1": h1["verdict"],
        "H2": {
            "tests_met": sum(test["directional_rule_met"] for test in h2),
            "tests_n": len(h2),
            "verdict": (
                "metric_specific_support"
                if any(test["directional_rule_met"] for test in h2)
                else "not_supported"
            ),
        },
        "H3": {
            category: {
                "tests_met": sum(
                    test["directional_rule_met"]
                    for test in h3
                    if test["slice"] == category
                ),
                "tests_n": 8,
                "verdict": (
                    "metric_specific_support"
                    if any(
                        test["directional_rule_met"]
                        for test in h3
                        if test["slice"] == category
                    )
                    else "not_supported"
                ),
            }
            for category in ("entity_relation", "multi_hop")
        },
        "H4": {
            "comparisons_met": sum(test["directional_rule_met"] for test in h4),
            "comparisons_n": 4,
            "verdict": (
                "supported"
                if all(test["directional_rule_met"] for test in h4)
                else "not_supported"
            ),
        },
        "H5": "not_in_scope",
    }
    result = {
        "conclusions_are_exploratory_pilot_evidence": True,
        "h1_equivalence": h1,
        "holm_directional_family_n": len(tests),
        "holm_directional_tests": tests,
        "invalid_historical_statistics_reused": False,
        "protocol": {
            "bootstrap": "paired whole-query percentile, 10000 samples, seed 42",
            "directional": "exact paired sign-randomization",
            "multiplicity": "Holm across 32 frozen metric-specific H2-H4 tests",
        },
        "summaries": summaries,
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    result_path = args.output_dir / "preregistered_h1_h4_results.json"
    rows_path = args.output_dir / "directional_test_rows.jsonl"
    write_json(result_path, result, overwrite=args.overwrite)
    write_jsonl(
        rows_path,
        [
            {"test_id": f"{test['hypothesis']}:{index:02d}", **test}
            for index, test in enumerate(tests, 1)
        ],
        key="test_id",
        overwrite=args.overwrite,
    )

    input_paths = (
        args.per_query_metrics,
        args.final_qrels,
        args.protocol,
        args.phase_plan,
        args.corrected_spec,
        args.bm25_ranking,
        args.faiss_ranking,
        args.graph_ranking,
        args.hybrid_ranking,
        args.prompt_ranking,
    )
    manifest = {
        "code_hashes": {
            "scripts/evaluate_phase6_preregistered_statistics.py": sha256_file(
                ROOT / "scripts/evaluate_phase6_preregistered_statistics.py"
            ),
            "scripts/evaluate_phase6_seed42.py": sha256_file(
                ROOT / "scripts/evaluate_phase6_seed42.py"
            ),
        },
        "git_head_at_execution": args.git_head,
        "inputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in input_paths},
        "outputs": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in (result_path, rows_path)
        },
        "status": "frozen_exploratory_pilot_statistics",
    }
    write_json(args.output_dir / "manifest.json", manifest, overwrite=args.overwrite)
    print(json.dumps(summaries, sort_keys=True))


if __name__ == "__main__":
    main()
