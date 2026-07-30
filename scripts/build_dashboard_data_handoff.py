#!/usr/bin/env python3
"""Build normalized, evidence-backed data files for dashboard implementation."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submission" / "dashboard_data"


def load_json(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def sha256(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty dataset: {name}")
    headers = list(rows[0])
    if any(list(row) != headers for row in rows):
        raise ValueError(f"non-uniform columns: {name}")
    with (OUT / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def system_label(system: str) -> str:
    return {
        "bm25": "BM25",
        "faiss_windowed_max": "FAISS windowed-max",
        "faiss_cosine": "FAISS normalized-cosine",
        "graph_v3_2": "Entity Graph v3.2",
        "graph_v4": "Entity Graph v4",
        "hybrid_rrf": "Hybrid RRF",
        "hybrid_r4": "Hybrid RRF (R4)",
        "prompt_rag_claude": "Prompt-RAG Claude",
    }[system]


OUT.mkdir(parents=True, exist_ok=True)

pilot_metrics_path = "runs/v2/phase6_seed42_final/metrics/balanced_metrics.json"
r4_metrics_path = "runs/phase8_r4_human_validated/retrieval_evaluation/metrics.json"
pilot_h5_path = "runs/v2/phase7_generation_claude_top3_v2/evaluation_v2_ai/h5_results.json"
r4_h5_path = "runs/phase8_r4_human_validated/generation_evaluation/h5_results.json"
r4_stats_path = "runs/phase8_r4_human_validated/retrieval_evaluation/exploratory_statistics.json"
pilot_stats_path = "runs/v2/phase6_seed42_final/statistics/preregistered_h1_h4_results.json"
r4_status_path = "audits/phase8_r4_human_validated/canonical_status.json"
r4_operational_status_path = "audits/phase8_r4/canonical_status.json"
phase7_cost_path = "audits/phase7_generation/v2/full_v2_success_checkpoint.json"
r4_retrieval_path = "runs/phase8_r4_improvements/prompt_rag_r4_v2_full/summary.json"
r4_generation_path = "runs/phase8_r4_improvements/generation_r4_v3_full/summary.json"
pilot_per_query_path = "runs/v2/phase6_seed42_final/metrics/final_pooled_per_query.jsonl"
r4_per_query_path = "runs/phase8_r4_human_validated/retrieval_evaluation/per_query.json"
pilot_questions_path = "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl"
r4_questions_path = "runs/phase8_r4_improvements/benchmark/qa_dev_test.jsonl"

pilot = load_json(pilot_metrics_path)
r4 = load_json(r4_metrics_path)
pilot_h5 = load_json(pilot_h5_path)
r4_h5 = load_json(r4_h5_path)
r4_stats = load_json(r4_stats_path)
r4_status = load_json(r4_status_path)
r4_operational_status = load_json(r4_operational_status_path)
phase7_cost = load_json(phase7_cost_path)
r4_retrieval = load_json(r4_retrieval_path)
r4_generation = load_json(r4_generation_path)

scope_rows = [
    {
        "benchmark": "V2 human-validated pilot",
        "claim_class": "canonical dissertation evidence",
        "documents": 22,
        "chunks": 140,
        "primary_questions": 34,
        "categories": 6,
        "synthesis_questions": 4,
        "relevance_pairs": 755,
        "human_validation_complete": True,
    },
    {
        "benchmark": "Phase 8 R4 expansion",
        "claim_class": "human-owner-validated exploratory scaling evidence",
        "documents": r4_status["documents"],
        "chunks": r4_status["chunks"],
        "primary_questions": r4_status["primary_questions"],
        "categories": 5,
        "synthesis_questions": r4_status.get(
            "synthesis_candidates", r4_status["owner_reviewed_synthesis_rows"]
        ),
        "relevance_pairs": 140,
        "human_validation_complete": r4_status["human_validation_complete"],
    },
]
write_csv("scope_comparison.csv", scope_rows)

retrieval_rows: list[dict[str, Any]] = []
for system, record in pilot.items():
    m = record["aggregate"]["metrics"]
    retrieval_rows.append(
        {
            "benchmark": "pilot",
            "claim_class": "human_validated_canonical",
            "split": "all_34",
            "system_key": system,
            "system": system_label(system),
            "query_n": record["aggregate"]["query_n"],
            "mrr_at_10": m["mrr_at_10"],
            "recall_at_10": m["recall_at_10"],
            "precision_at_10": m["precision_at_10"],
            "ndcg_at_10": m["graded_ndcg_at_10"],
            "hit_at_10": m["hit_rate_at_10"],
            "complete_evidence_recall_at_10": m["complete_evidence_recall_at_10"],
        }
    )
for system, record in r4["systems"].items():
    for split, query_n in (("all_100_descriptive", 100), ("development", 60), ("locked_test", 40)):
        m = record[split]
        retrieval_rows.append(
            {
                "benchmark": "phase8_r4",
                "claim_class": "owner_validated_exploratory",
                "split": split,
                "system_key": system,
                "system": system_label(system),
                "query_n": query_n,
                "mrr_at_10": m["mrr@10"],
                "recall_at_10": m["recall@10"],
                "precision_at_10": m["precision@10"],
                "ndcg_at_10": m["ndcg@10"],
                "hit_at_10": m["hit@10"],
                "complete_evidence_recall_at_10": "",
            }
        )
write_csv("retrieval_metrics.csv", retrieval_rows)

category_rows: list[dict[str, Any]] = []
for system, record in pilot.items():
    for category, category_record in record["per_category"].items():
        m = category_record["metrics"]
        category_rows.append(
            {
                "benchmark": "pilot",
                "claim_class": "human_validated_canonical",
                "split": "all_34",
                "system_key": system,
                "system": system_label(system),
                "category": category,
                "query_n": category_record["query_n"],
                "mrr_at_10": m["mrr_at_10"],
                "recall_at_10": m["recall_at_10"],
                "precision_at_10": m["precision_at_10"],
                "ndcg_at_10": m["graded_ndcg_at_10"],
                "hit_at_10": m["hit_rate_at_10"],
                "complete_evidence_recall_at_10": m["complete_evidence_recall_at_10"],
            }
        )
for system, record in r4["systems"].items():
    for category, m in record["locked_test_by_category"].items():
        category_rows.append(
            {
                "benchmark": "phase8_r4",
                "claim_class": "owner_validated_exploratory",
                "split": "locked_test",
                "system_key": system,
                "system": system_label(system),
                "category": category,
                "query_n": 8,
                "mrr_at_10": m["mrr@10"],
                "recall_at_10": m["recall@10"],
                "precision_at_10": m["precision@10"],
                "ndcg_at_10": m["ndcg@10"],
                "hit_at_10": m["hit@10"],
                "complete_evidence_recall_at_10": "",
            }
        )
write_csv("category_metrics.csv", category_rows)

pilot_questions = {
    row["question_id"]: row
    for row in (
        json.loads(line)
        for line in (ROOT / pilot_questions_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
}
r4_questions = {
    row["question_id"]: row
    for row in (
        json.loads(line)
        for line in (ROOT / r4_questions_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
}
query_rows: list[dict[str, Any]] = []
for line in (ROOT / pilot_per_query_path).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    q = pilot_questions[row["query_id"]]
    m = row["metrics"]
    query_rows.append(
        {
            "benchmark": "pilot",
            "claim_class": "human_validated_canonical",
            "split": "all_34",
            "query_id": row["query_id"],
            "category": row["category"],
            "question": q["question"],
            "reference_answer": q["reference_answer"],
            "system_key": row["system"],
            "system": system_label(row["system"]),
            "mrr_at_10": m["mrr_at_10"],
            "recall_at_10": m["recall_at_10"],
            "precision_at_10": m["precision_at_10"],
            "ndcg_at_10": m["graded_ndcg_at_10"],
            "hit_at_10": m["hit_rate_at_10"],
            "complete_evidence_recall_at_10": m["complete_evidence_recall_at_10"],
        }
    )
r4_per_query = load_json(r4_per_query_path)
for system, rows in r4_per_query.items():
    for row in rows:
        q = r4_questions[row["query_id"]]
        m = row["metrics"]
        query_rows.append(
            {
                "benchmark": "phase8_r4",
                "claim_class": "owner_validated_exploratory",
                "split": row["split"],
                "query_id": row["query_id"],
                "category": row["category"],
                "question": q["question"],
                "reference_answer": q["reference_answer"],
                "system_key": system,
                "system": system_label(system),
                "mrr_at_10": m["mrr@10"],
                "recall_at_10": m["recall@10"],
                "precision_at_10": m["precision@10"],
                "ndcg_at_10": m["ndcg@10"],
                "hit_at_10": m["hit@10"],
                "complete_evidence_recall_at_10": "",
            }
        )
write_csv("query_metrics.csv", query_rows)

generation_rows: list[dict[str, Any]] = []
for benchmark, payload, claim_class in (
    ("pilot_phase7", pilot_h5, "26_human_plus_144_disclosed_ai"),
    ("phase8_r4", r4_h5, "100_human_owner_reviewed"),
):
    for system, summary in payload["system_summaries"].items():
        dims = summary["dimension_means"]
        generation_rows.append(
            {
                "benchmark": benchmark,
                "claim_class": claim_class,
                "system_key": system,
                "system": system_label(system),
                "answer_n": summary["n"],
                "abstention_n": summary["abstention_n"],
                "correctness": dims["correctness"],
                "faithfulness": dims["faithfulness"],
                "completeness": dims["completeness"],
                "citation_accuracy": dims["citation_accuracy"],
                "unsupported_claim_severity": dims["unsupported_claim_severity"],
                "abstention_quality": dims["abstention_quality"],
            }
        )
write_csv("generation_quality.csv", generation_rows)

h5_rows: list[dict[str, Any]] = []
for benchmark, payload in (("pilot_phase7", pilot_h5), ("phase8_r4", r4_h5)):
    for row in payload["correlations"]:
        ci = row.get("ci95") or ["", ""]
        h5_rows.append(
            {
                "benchmark": benchmark,
                "claim_class": "exploratory_descriptive_only",
                "x": row["x"],
                "y": row["y"],
                "spearman_rho": row.get("spearman_rho", ""),
                "ci95_low": ci[0],
                "ci95_high": ci[1],
                "query_n": row["query_n"],
                "record_n": row["record_n"],
                "status": row.get("status", "estimated"),
            }
        )
write_csv("h5_correlations.csv", h5_rows)

stat_rows = [
    {
        "benchmark": "phase8_r4",
        "claim_class": "exploratory_not_preregistered",
        "metric": row["metric"],
        "left_system": system_label(row["left"]),
        "right_system": system_label(row["right"]),
        "difference_left_minus_right": row["difference"],
        "ci95_low": row["ci95"][0],
        "ci95_high": row["ci95"][1],
        "raw_p_two_sided": row["paired_randomization_p_two_sided"],
        "holm_adjusted_p": row["holm_adjusted_p"],
        "query_n": row["n"],
        "passes_holm_0_05": row["holm_adjusted_p"] < 0.05,
    }
    for row in r4_stats["comparisons"]
]
write_csv("r4_pairwise_statistics.csv", stat_rows)

operations_rows = [
    {
        "phase": "Phase 7 generation",
        "operation": "170 pilot answers",
        "valid_records": phase7_cost["full_panel_coverage_n"],
        "failures": phase7_cost["failure_n"],
        "retries": phase7_cost["retry_n"],
        "cost_usd": phase7_cost["cumulative_observed_phase7_cost_usd"],
        "hard_cap_usd": phase7_cost["hard_cap_usd"],
        "mean_latency_seconds": "",
    },
    {
        "phase": "Phase 8 R4 retrieval",
        "operation": "Prompt-RAG 100-query reranking",
        "valid_records": 100,
        "failures": r4_retrieval["failure_n"],
        "retries": r4_retrieval["retry_n"],
        "cost_usd": r4_retrieval["cost_usd"],
        "hard_cap_usd": r4_operational_status["absolute_hard_cap_usd"],
        "mean_latency_seconds": r4_retrieval["mean_latency_seconds"],
    },
    {
        "phase": "Phase 8 R4 generation",
        "operation": "100 answers across five systems",
        "valid_records": 100,
        "failures": r4_generation["failure_n"],
        "retries": r4_generation["retry_n"],
        "cost_usd": r4_operational_status["total_generation_cost_usd"],
        "hard_cap_usd": r4_operational_status["absolute_hard_cap_usd"],
        "mean_latency_seconds": r4_generation["mean_latency_seconds"],
    },
    {
        "phase": "Phase 8 R4 total",
        "operation": "retrieval plus generation",
        "valid_records": 200,
        "failures": 0,
        "retries": r4_operational_status["retries"],
        "cost_usd": r4_operational_status["cumulative_r4_api_cost_usd"],
        "hard_cap_usd": r4_operational_status["absolute_hard_cap_usd"],
        "mean_latency_seconds": "",
    },
]
write_csv("operations_cost_latency.csv", operations_rows)

validation_rows = [
    {
        "dataset": "Pilot relevance judgments",
        "row_count": 755,
        "human_rows": 755,
        "ai_rows": 0,
        "status": "human_validated_complete",
        "dashboard_badge": "CANONICAL",
        "allowed_claim": "primary dissertation retrieval evidence",
    },
    {
        "dataset": "Pilot generated answers",
        "row_count": 170,
        "human_rows": 26,
        "ai_rows": 144,
        "status": "mixed_human_ai_disclosed",
        "dashboard_badge": "MIXED LABELS",
        "allowed_claim": "exploratory generation evidence",
    },
    {
        "dataset": "R4 gold crosswalk mappings",
        "row_count": 140,
        "human_rows": 140,
        "ai_rows": 0,
        "status": "owner_review_complete",
        "dashboard_badge": "OWNER VALIDATED",
        "allowed_claim": "human-owner-validated exploratory retrieval scaling",
    },
    {
        "dataset": "R4 generated answers",
        "row_count": 100,
        "human_rows": 100,
        "ai_rows": 0,
        "status": "owner_review_complete",
        "dashboard_badge": "OWNER VALIDATED",
        "allowed_claim": "human-owner-evaluated exploratory answer-quality evidence",
    },
    {
        "dataset": "R4 synthesis candidates",
        "row_count": 20,
        "human_rows": 20,
        "ai_rows": 0,
        "status": "owner_review_complete_12_accept_4_revise_4_reject",
        "dashboard_badge": "REVIEWED · SEPARATE",
        "allowed_claim": "owner-reviewed candidates; excluded from primary metrics",
    },
]
write_csv("validation_status.csv", validation_rows)

source_paths = [
    pilot_metrics_path,
    pilot_stats_path,
    pilot_h5_path,
    r4_metrics_path,
    r4_stats_path,
    r4_h5_path,
    r4_status_path,
    r4_operational_status_path,
    phase7_cost_path,
    r4_retrieval_path,
    r4_generation_path,
    pilot_per_query_path,
    r4_per_query_path,
    pilot_questions_path,
    r4_questions_path,
]
sources = [{"path": p, "sha256": sha256(p)} for p in source_paths]

payload = {
    "schema_version": 1,
    "purpose": "frontend-neutral dissertation dashboard data handoff",
    "default_view": "pilot",
    "required_disclosure": (
        "Pilot is canonical confirmatory evidence. Phase 8 R4 is human-owner-validated "
        "exploratory scaling evidence and remains non-preregistered."
    ),
    "scope": scope_rows,
    "retrieval_metrics": retrieval_rows,
    "category_metrics": category_rows,
    "query_metrics": query_rows,
    "generation_quality": generation_rows,
    "h5_correlations": h5_rows,
    "r4_pairwise_statistics": stat_rows,
    "operations": operations_rows,
    "validation": validation_rows,
    "hypothesis_source": {
        "pilot_h1_h4_path": pilot_stats_path,
        "pilot_claim_class": "preregistered exploratory pilot evidence",
        "r4_claim_class": "exploratory not preregistered",
    },
    "sources": sources,
}
(OUT / "dashboard_payload_v2.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)

manifest = {
    "schema_version": 1,
    "generated_files": {},
    "source_files": sources,
}
for path in sorted(OUT.iterdir()):
    if path.name == "manifest.json" or not path.is_file():
        continue
    manifest["generated_files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
(OUT / "manifest.json").write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)

print(json.dumps({"output": str(OUT), "files": sorted(manifest["generated_files"])}, indent=2))
