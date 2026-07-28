#!/usr/bin/env python3
"""Run pilot-frozen BM25+graph RRF on Phase 8 automated benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.evaluator import RetrievalEvaluator
from src.retrievers.fusion import reciprocal_rank_fusion
from src.utils.io_utils import load_jsonl, save_jsonl


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bm25-run", required=True)
    parser.add_argument("--graph-run", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--output-root", required=True)
    args = parser.parse_args()

    qa = load_jsonl(args.qa)
    expected = {row["question_id"] for row in qa}
    runs = {
        "bm25": load_jsonl(args.bm25_run),
        "graph_v3_2": load_jsonl(args.graph_run),
    }
    for name, rows in runs.items():
        if {row["query_id"] for row in rows} != expected or len(rows) != len(expected):
            raise RuntimeError(f"{name} does not exactly cover Phase 8 questions")
        if any(int(row.get("top_k", 0)) < 50 for row in rows):
            raise RuntimeError(f"{name} was not requested at frozen top-50 depth")

    fused = reciprocal_rank_fusion(runs, rrf_k=60, input_depth=50, output_depth=50)
    for row in fused:
        row["retriever"] = "hybrid_rrf"
        row["config_snapshot"] = {
            "components": ["bm25", "graph_v3_2"],
            "rrf_k": 60,
            "input_depth": 50,
            "output_depth": 50,
            "selection_source": "frozen_phase4_pilot_configuration",
        }
    output = Path(args.output_root)
    run_path = output / "retrieval/hybrid_rrf_run.jsonl"
    save_jsonl(fused, run_path)
    evaluator = RetrievalEvaluator(
        args.qrels, args.categories, qa_dataset_path=args.qa, chunks_path=args.chunks,
    )
    bundles = evaluator.evaluate_run_file(run_path, retriever_name="hybrid_rrf")
    metrics_path = output / "metrics/hybrid_rrf_metrics.csv"
    evaluator.save_metrics_csv(bundles, metrics_path)
    aggregate = next(bundle.to_dict() for bundle in bundles if bundle.query_category == "all")
    summary = {
        "status": "complete_exploratory_automated_qrels",
        "questions": len(expected),
        "rrf_k": 60,
        "input_depth": 50,
        "output_depth": 50,
        "configuration_selected_on_phase8": False,
        "human_qrels": False,
        "aggregate": aggregate,
    }
    (output / "operational_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
