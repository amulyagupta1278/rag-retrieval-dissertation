#!/usr/bin/env python3
"""Compute oracle ceiling, then five-fold rule routing without a classifier."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.statistics import query_level_metrics
from src.utils.io_utils import load_jsonl, save_jsonl


def _graph_seed_bucket(run: dict | None) -> str:
    if not run or not run.get("results"):
        return "zero"
    extra = run["results"][0].get("extra", {})
    count = len(extra.get("seed_entities") or extra.get("seed_nodes") or [])
    return "zero" if count == 0 else "one" if count == 1 else "multiple"


def _feature(item: dict, graph_run: dict | None) -> tuple[str, bool, str, str]:
    words = item["question"].split()
    length = "short" if len(words) <= 8 else "medium" if len(words) <= 15 else "long"
    acronym = bool(re.search(r"\b[A-Z][A-Z0-9-]{1,9}\b", item["question"]))
    return item["category"], acronym, length, _graph_seed_bucket(graph_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=run.jsonl")
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean/router")
    args = parser.parse_args()
    qa_all = load_jsonl(args.qa)
    qa = {item["question_id"]: item for item in qa_all if item.get("split") == "dev"}
    qrels = QRelsBuilder.load_qrels_tsv(args.qrels)
    run_maps = {}
    for value in args.run:
        name, path = value.split("=", 1)
        selected = {run["query_id"]: run for run in load_jsonl(path) if run["query_id"] in qa}
        if set(selected) != set(qa):
            raise RuntimeError(f"{name} does not cover the complete dev split")
        run_maps[name] = selected
    metrics = {
        name: query_level_metrics(list(values.values()), qrels)
        for name, values in run_maps.items()
    }
    system_means = {
        name: sum(row["mrr_at_10"] for row in values.values()) / len(values)
        for name, values in metrics.items()
    }
    best_single = max(system_means, key=lambda name: (system_means[name], name))
    oracle_choices = {
        qid: max(metrics, key=lambda name: (metrics[name][qid]["mrr_at_10"], metrics[name][qid]["ndcg_at_10"], name))
        for qid in qa
    }
    oracle_mrr = sum(metrics[name][qid]["mrr_at_10"] for qid, name in oracle_choices.items()) / len(qa)
    oracle_gain = oracle_mrr - system_means[best_single]
    output = Path(args.output_root)
    output.mkdir(parents=True, exist_ok=True)
    if oracle_gain < 0.03:
        report = {
            "selection_split": "dev", "best_single": best_single,
            "best_single_mrr_at_10": system_means[best_single], "oracle_mrr_at_10": oracle_mrr,
            "oracle_gain": oracle_gain, "stop_threshold": 0.03, "stop_rule_passed": False,
            "decision": "do_not_build_router",
        }
        (output / "router_decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return

    graph_name = next((name for name in run_maps if "graph" in name), None)
    graph_runs = run_maps.get(graph_name, {})
    features = {qid: _feature(item, graph_runs.get(qid)) for qid, item in qa.items()}
    folds: dict[str, int] = {}
    by_category: dict[str, list[str]] = defaultdict(list)
    for qid, item in qa.items():
        by_category[item["category"]].append(qid)
    for category, query_ids in sorted(by_category.items()):
        for index, qid in enumerate(sorted(query_ids)):
            folds[qid] = index % 5

    def select_system(training: set[str], target: str) -> str:
        target_feature = features[target]
        groups = [
            [qid for qid in training if features[qid] == target_feature],
            [qid for qid in training if qa[qid]["category"] == qa[target]["category"]],
            sorted(training),
        ]
        group = next(values for values in groups if values)
        quality = {
            name: sum(metrics[name][qid]["ndcg_at_10"] for qid in group) / len(group)
            for name in metrics
        }
        best_quality = max(quality.values())
        eligible = [name for name, score in quality.items() if score >= best_quality - 0.01]
        latency = {
            name: sum(metrics[name][qid]["latency_ms"] for qid in group) / len(group)
            for name in eligible
        }
        return min(eligible, key=lambda name: (latency[name], name))

    choices = {}
    routed = []
    all_ids = set(qa)
    for fold in range(5):
        held = sorted(qid for qid, value in folds.items() if value == fold)
        training = all_ids - set(held)
        for qid in held:
            chosen = select_system(training, qid)
            choices[qid] = chosen
            source = run_maps[chosen][qid]
            routed.append({
                **source, "retriever": "rule_router",
                "config": {"fold": fold, "chosen_system": chosen, "features": features[qid], "trained_classifier": False},
            })
    routed.sort(key=lambda run: run["query_id"])
    run_path = output / "retrieval/rule_router_run.jsonl"
    save_jsonl(routed, run_path)
    evaluator = RetrievalEvaluator(args.qrels, args.categories, qa_dataset_path=args.qa, split="dev")
    bundles = evaluator.evaluate_run_file(run_path, retriever_name="rule_router")
    evaluator.save_metrics_csv(bundles, output / "metrics/rule_router_metrics.csv")
    aggregate = next(bundle for bundle in bundles if bundle.query_category == "all")
    report = {
        "selection_split": "dev", "folds": 5, "trained_classifier": False,
        "features": ["category", "acronym", "query_length", "graph_seed_count"],
        "best_single": best_single, "best_single_mrr_at_10": system_means[best_single],
        "oracle_mrr_at_10": oracle_mrr, "oracle_gain": oracle_gain,
        "stop_threshold": 0.03, "stop_rule_passed": True,
        "routed_mrr_at_10": aggregate.mrr_at_k.get(10, 0.0), "choices": dict(Counter(choices.values())),
    }
    (output / "router_decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
