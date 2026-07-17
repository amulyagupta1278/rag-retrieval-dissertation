#!/usr/bin/env python3
"""Conditionally rerank the winning RRF run on development queries only."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sentence_transformers import CrossEncoder

from src.evaluation.evaluator import RetrievalEvaluator
from src.utils.io_utils import load_jsonl, save_jsonl

MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
REVISION = "c5ee24cb16019beea0893ab7796b1df96625c6b8"


def _aggregate(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8") as handle:
        row = next(item for item in csv.DictReader(handle) if item["query_category"] == "all")
    return {"ndcg_at_10": float(row["ndcg@10"]), "mrr_at_10": float(row["mrr@10"]), "recall_at_10": float(row["recall@10"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rrf-decision", required=True)
    parser.add_argument("--rrf-run", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean/reranker")
    args = parser.parse_args()
    rrf_decision = json.loads(Path(args.rrf_decision).read_text(encoding="utf-8"))
    if not rrf_decision.get("stop_rule_passed"):
        raise RuntimeError("Reranker is locked because RRF did not pass its gain threshold")
    qa = load_jsonl(args.qa)
    dev_ids = {item["question_id"] for item in qa if item.get("split") == "dev"}
    runs = [run for run in load_jsonl(args.rrf_run) if run["query_id"] in dev_ids]
    if {run["query_id"] for run in runs} != dev_ids or any(len(run.get("results", [])) < 50 for run in runs):
        raise RuntimeError("Reranking requires a complete dev top-50 RRF run")
    model = CrossEncoder(MODEL, revision=REVISION)
    evaluator = RetrievalEvaluator(args.qrels, args.categories, qa_dataset_path=args.qa, split="dev")
    output = Path(args.output_root)
    metrics = {}
    for depth in (20, 50):
        reranked_runs = []
        for run in runs:
            candidates = run["results"][:depth]
            pairs = [(run["question"], result.get("text", "")) for result in candidates]
            start = time.perf_counter_ns()
            scores = model.predict(pairs, show_progress_bar=False)
            rerank_ms = (time.perf_counter_ns() - start) / 1_000_000
            ordered = sorted(
                zip(candidates, scores), key=lambda item: (-float(item[1]), item[0]["chunk_id"]),
            )
            results = [
                {
                    **result, "rank": rank, "score": float(score), "retriever": "cross_encoder_reranker",
                    "extra": {**result.get("extra", {}), "reranker_model": MODEL, "rerank_depth": depth},
                }
                for rank, (result, score) in enumerate(ordered, 1)
            ]
            reranked_runs.append({
                **run, "retriever": "cross_encoder_reranker", "top_k": depth,
                "total_latency_ms": float(run.get("total_latency_ms", 0.0)) + rerank_ms,
                "results": results,
                "config": {"model": MODEL, "revision": REVISION, "rerank_depth": depth, "selection_split": "dev"},
            })
        run_path = output / f"top_{depth}/retrieval/reranked_run.jsonl"
        save_jsonl(reranked_runs, run_path)
        bundles = evaluator.evaluate_run_file(run_path, retriever_name=f"reranker_top_{depth}")
        metric_path = output / f"top_{depth}/metrics/reranker_metrics.csv"
        evaluator.save_metrics_csv(bundles, metric_path)
        metrics[f"top_{depth}"] = _aggregate(metric_path)
    best = max(metrics, key=lambda name: metrics[name]["ndcg_at_10"])
    baseline = rrf_decision["fusion_metrics"][rrf_decision["best_fusion"]]["ndcg_at_10"]
    gain = metrics[best]["ndcg_at_10"] - baseline
    report = {
        "selection_split": "dev", "model": MODEL, "revision": REVISION,
        "metrics": metrics, "best_depth": best, "rrf_ndcg_at_10": baseline,
        "ndcg_at_10_gain": gain, "stop_threshold": 0.01,
        "stop_rule_passed": gain >= 0.01,
        "decision": "retain_reranker" if gain >= 0.01 else "stop_and_retain_rrf",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "reranker_decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
