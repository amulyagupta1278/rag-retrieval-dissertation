#!/usr/bin/env python3
"""Evaluate conditional equal-weight RRF combinations on dev queries."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.evaluator import RetrievalEvaluator
from src.retrievers.fusion import reciprocal_rank_fusion
from src.utils.io_utils import load_jsonl, save_jsonl


def _aggregate(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8") as handle:
        row = next(item for item in csv.DictReader(handle) if item["query_category"] == "all")
    return {"ndcg_at_10": float(row["ndcg@10"]), "mrr_at_10": float(row["mrr@10"]), "recall_at_10": float(row["recall@10"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-summary", required=True)
    parser.add_argument("--p2-decision", required=True)
    parser.add_argument("--p3-decision", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--bm25-run", required=True)
    parser.add_argument("--dense-run", required=True)
    parser.add_argument("--graph-run", required=True)
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean/rrf")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    if audit.get("audit_status") != "complete" or audit.get("questions_reviewed") != 60:
        raise RuntimeError("P4 is locked until the 60/60 audit is complete")
    # Requiring both decision files prevents silent use of pre-selection runs.
    json.loads(Path(args.p2_decision).read_text(encoding="utf-8"))
    json.loads(Path(args.p3_decision).read_text(encoding="utf-8"))
    qa = load_jsonl(args.qa)
    dev_ids = {item["question_id"] for item in qa if item.get("split") == "dev"}
    runs = {
        "bm25": [run for run in load_jsonl(args.bm25_run) if run["query_id"] in dev_ids],
        "dense": [run for run in load_jsonl(args.dense_run) if run["query_id"] in dev_ids],
        "graph": [run for run in load_jsonl(args.graph_run) if run["query_id"] in dev_ids],
    }
    for system, values in runs.items():
        if {run["query_id"] for run in values} != dev_ids:
            raise RuntimeError(f"{system} run does not cover the frozen dev split")
        if any(int(run.get("top_k", 0)) < 50 for run in values):
            raise RuntimeError(f"{system} must be requested at top-50 before RRF")
    combinations = {
        "bm25_dense": ("bm25", "dense"),
        "bm25_graph": ("bm25", "graph"),
        "bm25_dense_graph": ("bm25", "dense", "graph"),
    }
    output = Path(args.output_root)
    evaluator = RetrievalEvaluator(args.qrels, args.categories, qa_dataset_path=args.qa, split="dev")
    metrics: dict[str, dict[str, float]] = {}
    for name, systems in combinations.items():
        fused = reciprocal_rank_fusion({system: runs[system] for system in systems}, rrf_k=60, input_depth=50, output_depth=50)
        run_path = output / name / "retrieval/rrf_run.jsonl"
        save_jsonl(fused, run_path)
        bundles = evaluator.evaluate_run_file(run_path, retriever_name=f"rrf_{name}")
        metric_path = output / name / "metrics/rrf_metrics.csv"
        evaluator.save_metrics_csv(bundles, metric_path)
        metrics[name] = _aggregate(metric_path)
    # Compare against the strongest component using the same dev qrels.
    component_metrics = {}
    for name, values in runs.items():
        path = output / f"component_{name}.jsonl"
        save_jsonl(values, path)
        bundles = evaluator.evaluate_run_file(path, retriever_name=name)
        metric_path = output / f"component_{name}.csv"
        evaluator.save_metrics_csv(bundles, metric_path)
        component_metrics[name] = _aggregate(metric_path)
    best_component = max(component_metrics, key=lambda name: component_metrics[name]["ndcg_at_10"])
    best_fusion = max(metrics, key=lambda name: metrics[name]["ndcg_at_10"])
    gain = metrics[best_fusion]["ndcg_at_10"] - component_metrics[best_component]["ndcg_at_10"]
    report = {
        "selection_split": "dev", "rrf_k": 60, "input_depth": 50,
        "component_metrics": component_metrics, "fusion_metrics": metrics,
        "best_component": best_component, "best_fusion": best_fusion,
        "ndcg_at_10_gain": gain, "stop_threshold": 0.01,
        "stop_rule_passed": gain >= 0.01,
        "decision": "proceed_to_reranking" if gain >= 0.01 else "stop_and_retain_best_component",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "rrf_decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
