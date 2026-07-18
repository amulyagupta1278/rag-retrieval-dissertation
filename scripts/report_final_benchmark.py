#!/usr/bin/env python3
"""Render lineage, aggregate, category, latency, and hypothesis decision tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DISPLAY = {
    "bm25": "BM25", "faiss": "FAISS",
    "graphrag": "Entity-Co-occurrence Graph Retrieval",
}


def _load_metrics(path: str) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("metrics", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError(f"Metrics JSON has unsupported structure: {path}")
    return records


def _value(record: dict, group: str, k: int) -> float:
    values = record.get(group, {})
    return float(values.get(str(k), values.get(k, 0.0)))


def _row(record: dict) -> list[str]:
    return [
        DISPLAY.get(record["retriever"], record["retriever"]),
        record["query_category"], str(record["num_queries"]),
        f"{_value(record, 'mrr_at_k', 5):.4f}", f"{_value(record, 'mrr_at_k', 10):.4f}",
        f"{_value(record, 'recall_at_k', 5):.4f}", f"{_value(record, 'recall_at_k', 10):.4f}",
        f"{_value(record, 'ndcg_at_k', 10):.4f}", f"{float(record.get('avg_latency_ms', 0)):.2f}",
    ]


def _table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", action="append", required=True, help="STAGE=metrics.json")
    parser.add_argument("--statistics", required=True)
    parser.add_argument("--latency", default=None)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    stages = {}
    for value in args.metrics:
        if "=" not in value:
            raise ValueError("--metrics must use STAGE=PATH")
        stage, path = value.split("=", 1)
        stages[stage] = _load_metrics(path)
    statistics = json.loads(Path(args.statistics).read_text(encoding="utf-8"))
    if "hypothesis_decisions" not in statistics:
        raise RuntimeError("Final statistical report lacks pre-registered H1-H3 decisions")
    final_stage = list(stages)[-1]
    final_records = stages[final_stage]
    aggregate = [record for record in final_records if record["query_category"] == "all"]
    categories = [record for record in final_records if record["query_category"] != "all"]
    stage_rows = []
    for stage, records in stages.items():
        for record in records:
            if record["query_category"] == "all":
                stage_rows.append([stage, *_row(record)])
    markdown = [
        "# Final Retrieval Benchmark Report",
        "",
        "## Artifact-lineage comparison",
        "",
        _table(
            ["Stage", "System", "Slice", "N", "MRR@5", "MRR@10", "Recall@5", "Recall@10", "nDCG@10", "Avg ms"],
            stage_rows,
        ),
        "",
        "## Table 5.3 — Final aggregate",
        "",
        _table(["System", "Slice", "N", "MRR@5", "MRR@10", "Recall@5", "Recall@10", "nDCG@10", "Avg ms"], [_row(record) for record in aggregate]),
        "",
        "## Table 5.4 — Final per-category",
        "",
        _table(["System", "Category", "N", "MRR@5", "MRR@10", "Recall@5", "Recall@10", "nDCG@10", "Avg ms"], [_row(record) for record in categories]),
        "",
        "## Pre-registered hypothesis decisions",
        "",
    ]
    decision_rows = []
    for name, decision in sorted(statistics["hypothesis_decisions"].items()):
        decision_rows.append([
            name, decision["wording"], decision["outcome"], str(decision.get("comparator", "")),
        ])
    markdown.append(_table(["Hypothesis", "Wording", "Outcome", "Comparator"], decision_rows))
    if args.latency:
        latency = json.loads(Path(args.latency).read_text(encoding="utf-8"))
        markdown.extend(["", "## Latency protocol", "", "```json", json.dumps(latency, indent=2, sort_keys=True), "```"])
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = {
        "stages": stages, "final_stage": final_stage,
        "hypothesis_decisions": statistics["hypothesis_decisions"],
    }
    (output / "final_benchmark_report.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "final_benchmark_report.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    print(json.dumps({"final_stage": final_stage, "systems": len(aggregate)}, indent=2))


if __name__ == "__main__":
    main()
