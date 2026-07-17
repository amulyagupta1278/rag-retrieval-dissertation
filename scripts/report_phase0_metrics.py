#!/usr/bin/env python3
"""Produce Phase 0 aggregate/per-category metrics from existing top-10 runs."""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.metrics import (
    compute_mrr_at_k, compute_ndcg_at_k, compute_recall_at_k,
)
from src.utils.io_utils import load_jsonl

SYSTEMS = ("bm25", "faiss", "graphrag")
CATEGORIES = ("exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop")
MID_SEM_MRR = {"bm25": 0.83, "faiss": 0.80, "graphrag": 0.61}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _metrics(runs: list[dict], qrels: dict[str, dict[str, int]]) -> dict:
    values: dict[str, list[float]] = defaultdict(list)
    for run in runs:
        ranked = [result["chunk_id"] for result in run.get("results", [])]
        gold = set(qrels.get(run["query_id"], {}))
        values["mrr_at_5"].append(compute_mrr_at_k(ranked, gold, 5))
        values["mrr_at_10"].append(compute_mrr_at_k(ranked, gold, 10))
        values["recall_at_5"].append(compute_recall_at_k(ranked, gold, 5))
        values["recall_at_10"].append(compute_recall_at_k(ranked, gold, 10))
        values["ndcg_at_10"].append(compute_ndcg_at_k(ranked, gold, 10))
        values["avg_latency_ms"].append(float(run.get("total_latency_ms", 0.0)))
    return {key: round(_mean(score), 6) for key, score in values.items()} | {"num_queries": len(runs)}


def main() -> None:
    qa = load_jsonl("data/queries/qa_dataset.jsonl")
    category_by_id = {item["question_id"]: item["category"] for item in qa}
    qrels = QRelsBuilder.load_qrels_tsv("data/qrels/qrels.tsv")
    chunk_ids = {item["chunk_id"] for item in load_jsonl("data/chunks/chunks.jsonl")}
    aggregate: dict[str, dict] = {}
    per_category: dict[str, dict[str, dict]] = {}
    integrity: dict[str, dict] = {}

    for system in SYSTEMS:
        runs = load_jsonl(f"runs/retrieval/{system}_run.jsonl")
        run_qids = {run["query_id"] for run in runs}
        retrieved_ids = {result["chunk_id"] for run in runs for result in run.get("results", [])}
        integrity[system] = {
            "run_count": len(runs),
            "unique_query_count": len(run_qids),
            "unknown_retrieved_chunk_ids": sorted(retrieved_ids - chunk_ids),
        }
        aggregate[system] = _metrics(runs, qrels)
        per_category[system] = {}
        for category in CATEGORIES:
            selected = [run for run in runs if category_by_id.get(run["query_id"]) == category]
            per_category[system][category] = _metrics(selected, qrels)

    flags: list[str] = []
    if all(aggregate[system]["mrr_at_10"] < 0.10 for system in SYSTEMS):
        flags.append("all_systems_aggregate_mrr_at_10_below_0.10")
    if all(aggregate[system]["mrr_at_10"] < 0.30 * MID_SEM_MRR[system] for system in SYSTEMS):
        flags.append("all_systems_declined_over_70_percent_from_mid_sem")
    for category in CATEGORIES:
        if all(per_category[system][category]["mrr_at_10"] < 0.05 for system in SYSTEMS):
            flags.append(f"{category}:all_systems_mrr_at_10_below_0.05")
        if all(per_category[system][category]["recall_at_10"] < 0.10 for system in SYSTEMS):
            flags.append(f"{category}:all_systems_recall_at_10_below_0.10")
        if all(per_category[system][category]["mrr_at_10"] >= 0.95 for system in SYSTEMS):
            flags.append(f"{category}:all_systems_mrr_at_10_at_least_0.95")
    if len(qa) != 100 or len(qrels) != 100 or any(info["run_count"] != 100 for info in integrity.values()):
        flags.append("run_query_or_qrels_query_count_mismatch")
    gold_ids = {chunk_id for judgments in qrels.values() for chunk_id in judgments}
    if gold_ids - chunk_ids:
        flags.append("unknown_gold_chunk_ids")
    if any(info["unknown_retrieved_chunk_ids"] for info in integrity.values()):
        flags.append("unknown_retrieved_chunk_ids")

    report = {
        "corpus_chunks": len(chunk_ids), "queries": len(qa),
        "qrels_queries": len(qrels), "qrels_judgments": sum(map(len, qrels.values())),
        "aggregate": aggregate, "per_category": per_category,
        "integrity": integrity, "sanity_flags": flags,
    }
    output = Path("runs/reports/phase0_benchmark_metrics.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    columns = ("mrr_at_5", "mrr_at_10", "recall_at_5", "recall_at_10", "ndcg_at_10", "avg_latency_ms")
    with Path("runs/metrics/phase0_benchmark_metrics.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["system", "category", *columns])
        for system in SYSTEMS:
            writer.writerow([system, "all", *(aggregate[system][key] for key in columns)])
            for category in CATEGORIES:
                writer.writerow([system, category, *(per_category[system][category][key] for key in columns)])

    lines = ["# Phase 0 Retrieval Benchmark", "", "## Table 5.3 — Aggregate", "",
             "| System | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for system in SYSTEMS:
        row = aggregate[system]
        lines.append(f"| {system.upper()} | {row['mrr_at_5']:.4f} | {row['mrr_at_10']:.4f} | {row['recall_at_5']:.4f} | {row['recall_at_10']:.4f} | {row['ndcg_at_10']:.4f} | {row['avg_latency_ms']:.2f} |")
    lines += ["", "## Table 5.4 — Per category", "",
              "| System | Category | MRR@5 | MRR@10 | Recall@5 | Recall@10 | nDCG@10 | Avg latency (ms) |",
              "|---|---|---:|---:|---:|---:|---:|---:|"]
    for system in SYSTEMS:
        for category in CATEGORIES:
            row = per_category[system][category]
            lines.append(f"| {system.upper()} | {category} | {row['mrr_at_5']:.4f} | {row['mrr_at_10']:.4f} | {row['recall_at_5']:.4f} | {row['recall_at_10']:.4f} | {row['ndcg_at_10']:.4f} | {row['avg_latency_ms']:.2f} |")
    lines += ["", "## Sanity flags", "", *(f"- {flag}" for flag in flags or ["None"])]
    Path("runs/reports/phase0_benchmark_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
