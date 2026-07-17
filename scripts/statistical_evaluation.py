#!/usr/bin/env python3
"""Export query metrics, bootstrap CIs, and paired tests for frozen runs."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.statistics import (
    bootstrap_mean_ci, paired_bootstrap, paired_randomization_test,
    query_level_metrics, save_query_metrics_csv,
)
from src.utils.io_utils import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=path/to/run.jsonl")
    parser.add_argument("--split", choices=("all", "dev", "test", "holdout"), default="all")
    parser.add_argument("--samples", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    qa = load_jsonl(args.qa)
    selected = {
        item["question_id"] for item in qa
        if args.split == "all" or item.get("split") == args.split
    }
    if not selected:
        raise RuntimeError(f"No QA items selected for split={args.split}")
    category_by_id = {item["question_id"]: item["category"] for item in qa if item["question_id"] in selected}
    split_by_id = {item["question_id"]: item.get("split", "unknown") for item in qa if item["question_id"] in selected}
    qrels = {
        qid: value for qid, value in QRelsBuilder.load_qrels_tsv(args.qrels).items()
        if qid in selected
    }
    systems: dict[str, dict[str, dict[str, float]]] = {}
    for value in args.run:
        if "=" not in value:
            raise ValueError("--run must use NAME=PATH syntax")
        name, path = value.split("=", 1)
        runs = [run for run in load_jsonl(path) if run["query_id"] in selected]
        run_ids = {run["query_id"] for run in runs}
        if run_ids != selected:
            raise RuntimeError(f"{name} run does not exactly cover selected split")
        systems[name] = query_level_metrics(runs, qrels)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    save_query_metrics_csv(systems, output_dir / f"query_metrics_{args.split}.csv", category_by_id, split_by_id)
    metrics = ("mrr_at_5", "mrr_at_10", "recall_at_5", "recall_at_10", "ndcg_at_10")
    report: dict = {
        "split": args.split, "query_count": len(selected), "samples": args.samples,
        "seed": args.seed, "confidence_intervals": {}, "paired_comparisons": {},
    }
    for system, rows in sorted(systems.items()):
        report["confidence_intervals"][system] = {
            metric: bootstrap_mean_ci(rows, metric, samples=args.samples, seed=args.seed)
            for metric in metrics
        }
    for left, right in combinations(sorted(systems), 2):
        report["paired_comparisons"][f"{left}_minus_{right}"] = {
            metric: {
                "bootstrap": paired_bootstrap(
                    systems[left], systems[right], metric, samples=args.samples, seed=args.seed,
                ),
                "randomization": paired_randomization_test(
                    systems[left], systems[right], metric, samples=args.samples, seed=args.seed,
                ),
            }
            for metric in metrics
        }
    (output_dir / f"statistical_evaluation_{args.split}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"split": args.split, "queries": len(selected), "systems": sorted(systems)}, indent=2))


if __name__ == "__main__":
    main()
