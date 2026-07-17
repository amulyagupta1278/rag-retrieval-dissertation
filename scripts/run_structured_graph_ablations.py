#!/usr/bin/env python3
"""Run G0–G4 structured-graph ablations on the frozen dev split only."""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.statistics import query_level_metrics
from src.utils.io_utils import load_jsonl

ABLATIONS = {
    "g1_aliases": (False, False, False),
    "g2_typed_metadata": (True, False, False),
    "g3_weighted_traversal": (True, True, False),
    "g4_lexical_fallback": (True, True, True),
}


def _cross_ndcg_from_run(run_path: str, qa: list[dict], qrels: dict) -> float:
    selected = {
        item["question_id"] for item in qa
        if item.get("split") == "dev" and item["category"] in {"entity_relation", "multi_hop"}
    }
    rows = query_level_metrics(
        [run for run in load_jsonl(run_path) if run["query_id"] in selected], qrels,
    )
    return sum(row["ndcg_at_10"] for row in rows.values()) / len(rows) if rows else 0.0


def _cross_ndcg_from_csv(path: Path) -> float:
    values = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["query_category"] in {"entity_relation", "multi_hop"}:
                values.append(float(row["ndcg@10"]))
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-summary", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--g0-run", required=True)
    parser.add_argument("--index-root", default="indexes/model_selection/v3_clean/structured_graph")
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean/structured_graph")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    if audit.get("audit_status") != "complete" or audit.get("questions_reviewed") != 60:
        raise RuntimeError("P3 is locked until the 60/60 human audit is complete")
    qa = load_jsonl(args.qa)
    qrels = QRelsBuilder.load_qrels_tsv(args.qrels)
    scores = {"g0_entity_cooccurrence": _cross_ndcg_from_run(args.g0_run, qa, qrels)}
    for name, (typed, weighted, fallback) in ABLATIONS.items():
        index = Path(args.index_root) / name
        output = Path(args.output_root) / name
        command = [
            sys.executable, "experiments/run_structured_graph.py", "--rebuild", "--split", "dev",
            "--chunks", args.chunks, "--qa-dataset", args.qa, "--qrels", args.qrels,
            "--query-categories", args.categories, "--index-dir", str(index),
            "--output-root", str(output), "--use-aliases",
            "--use-typed-metadata" if typed else "--no-use-typed-metadata",
            "--use-weighted-traversal" if weighted else "--no-use-weighted-traversal",
            "--use-fallback" if fallback else "--no-use-fallback",
        ]
        print("+", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": "0"}, check=True)
        scores[name] = _cross_ndcg_from_csv(output / "metrics/structured_graph_metrics.csv")
    best = max((name for name in ABLATIONS), key=lambda name: (scores[name], name))
    gain = scores[best] - scores["g0_entity_cooccurrence"]
    report = {
        "selection_split": "dev", "metric": "mean entity_relation/multi_hop nDCG@10",
        "scores": scores, "best_structured_ablation": best, "gain_over_g0": gain,
        "stop_threshold": 0.05, "stop_rule_passed": gain >= 0.05,
        "decision": "retain_structured_graph" if gain >= 0.05 else "stop_and_retain_g0",
    }
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "ablation_decision.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
