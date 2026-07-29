#!/usr/bin/env python3
"""Disclosed offline AI transfer evaluation and exploratory R4 H5 analysis."""

from __future__ import annotations

import hashlib, json, math, random, statistics, sys
from collections import Counter
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.finalize_phase7_ai_evaluation_h5 import DIMS, build_features, classify  # noqa: E402
BASE = ROOT / "runs/phase8_r4_improvements"
OUT = BASE / "evaluation_ai_h5"
OWNER = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v1/phase7_owner_audit_26_COMPLETED.json"
INDEX = BASE / "generation_r4_v3_full/combined_100_record_index.jsonl"
PLAN = BASE / "generation_r4_freeze/request_plan.jsonl"
PAYLOADS = BASE / "generation_r4_freeze/request_payloads.jsonl"
QA = BASE / "benchmark/qa_dev_test.jsonl"
RETRIEVAL = BASE / "evaluation_r4/per_query.json"


def load(path): return json.loads(Path(path).read_text())
def rows(path): return [json.loads(x) for x in Path(path).read_text().splitlines() if x]
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def stable(value): return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
def dump(path, value): Path(path).parent.mkdir(parents=True, exist_ok=True); Path(path).write_text(stable(value) + "\n")


def correlation(joined, x_key, y_key, rng):
    point = float(spearmanr([r[x_key] for r in joined], [r[y_key] for r in joined]).statistic)
    qids = sorted({r["query_id"] for r in joined}); grouped = {q: [r for r in joined if r["query_id"] == q] for q in qids}; draws = []
    for _ in range(10_000):
        sample = [r for _ in qids for r in grouped[rng.choice(qids)]]
        stat = spearmanr([r[x_key] for r in sample], [r[y_key] for r in sample]).statistic
        if not math.isnan(stat): draws.append(float(stat))
    return {"x": x_key, "y": y_key, "status": "not_estimable_constant_dimension" if math.isnan(point) else "estimated", "spearman_rho": None if math.isnan(point) else point, "record_n": len(joined), "query_n": len(qids), "bootstrap_samples": 10_000, "bootstrap_valid_n": len(draws), "ci95": None if not draws else [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))]}


def main():
    if (OUT / "manifest.json").exists(): raise SystemExit("completed AI/H5 output exists; refusing overwrite")
    owner_rows = load(OWNER)["rows"]
    if len(owner_rows) != 26 or any(type(r[d]) is not int for r in owner_rows for d in DIMS): raise SystemExit("owner calibration rows invalid")
    index = {r["blinded_request_id"]: r for r in rows(INDEX)}; plans = {r["blinded_request_id"]: r for r in rows(PLAN)}; payloads = {r["blinded_request_id"]: r for r in rows(PAYLOADS)}
    qa = {r["question_id"]: r for r in rows(QA)}
    if len(index) != 100 or len(plans) != 100 or set(index) != set(plans): raise SystemExit("R4 generation coverage differs")
    r4_rows = []
    for blind in sorted(index):
        record = load(ROOT / index[blind]["validated_path"]); answer = record["answer"]
        payload = json.loads(payloads[blind]["request"]["messages"][0]["content"]); plan = plans[blind]
        r4_rows.append({"blinded_request_id": blind, "question": payload["question"], "reference_answer": qa[plan["query_id"]]["reference_answer"], "evidence": payload["evidence"], "generated_answer": answer["answer"], "cited_evidence_ids": answer["cited_evidence_ids"], "abstained": answer["abstained"], "abstention_reason": answer["abstention_reason"]})
    combined = [*owner_rows, *r4_rows]; features, resolved_model = build_features(combined); predictions, calibration = classify(combined, features, owner_rows)
    final = []
    for offset, row in enumerate(r4_rows, start=len(owner_rows)):
        final.append({**row, **{dim: int(predictions[dim][offset]) for dim in DIMS}, "label_source": "offline_ai_knn_transfer_from_phase7_owner26", "human_label": False, "ai_method": "all-MiniLM-L6-v2 features + 5-NN trained on 26 genuine Phase 7 owner labels"})
    OUT.mkdir(parents=True, exist_ok=True); (OUT / "ai_quality_labels_100.jsonl").write_text("".join(stable(r) + "\n" for r in final))
    agreement = {"schema_version": 1, "status": "not_estimable_on_r4", "r4_owner_label_overlap_n": 0, "r4_ai_owner_agreement": None, "historical_transfer_calibration": {"dataset": "Phase 7 genuine owner audit", "owner_n": 26, "method": "leave-one-owner-row-out 5-nearest-neighbor", "dimensions": calibration}, "resolved_embedding_model": resolved_model, "limitation": "Historical Phase 7 cross-validation is not R4 AI-owner agreement and not independent inter-rater reliability."}
    dump(OUT / "ai_owner_agreement.json", agreement)
    retrieval = load(RETRIEVAL); metric_index = {system: {r["query_id"]: r["metrics"] for r in system_rows} for system, system_rows in retrieval.items()}
    final_by_id = {r["blinded_request_id"]: r for r in final}; joined = []
    for blind, plan in plans.items():
        labels, metrics = final_by_id[blind], metric_index[plan["system_id"]][plan["query_id"]]
        joined.append({"blinded_request_id": blind, "query_id": plan["query_id"], "category": plan["category"], "system": plan["system_id"], "label_source": labels["label_source"], **{d: labels[d] for d in DIMS}, "abstained": labels["abstained"], "mrr@10": metrics["mrr@10"], "ndcg@10": metrics["ndcg@10"], "recall@10": metrics["recall@10"]})
    joined.sort(key=lambda r: r["blinded_request_id"]); (OUT / "h5_joined_100.jsonl").write_text("".join(stable(r) + "\n" for r in joined))
    systems = {}
    for system in sorted({r["system"] for r in joined}):
        subset = [r for r in joined if r["system"] == system]
        systems[system] = {"n": len(subset), "abstention_n": sum(r["abstained"] for r in subset), "dimension_means": {d: statistics.fmean(r[d] for r in subset) for d in DIMS}, "retrieval_means": {m: statistics.fmean(r[m] for r in subset) for m in ("mrr@10", "ndcg@10", "recall@10")}}
    rng = random.Random(42); analyses = [correlation(joined, "mrr@10", "faithfulness", rng), correlation(joined, "mrr@10", "correctness", rng), correlation(joined, "ndcg@10", "correctness", rng), correlation(joined, "recall@10", "completeness", rng)]
    h5 = {"schema_version": 1, "status": "complete_exploratory_ai_evaluated_pending_human_validation", "hypothesis": "Retrieval quality does not guarantee generation faithfulness; retrieval and generation require separate evaluation.", "label_sources": {"offline_ai_knn_transfer": 100, "human_owner_r4": 0}, "qrel_status": "automatic crosswalk pending human validation", "bootstrap": {"unit": "whole query preserving five-system panel", "samples": 10_000, "seed": 42}, "correlations": analyses, "system_summaries": systems, "decision": "exploratory_descriptive_only", "decision_reason": "No preregistered R4 effect threshold; labels and qrels lack R4 human validation.", "interpretation_limits": ["All 100 R4 quality labels are AI-assigned.", "R4 has no owner labels, so R4 AI-owner agreement is not estimable.", "Automatic qrel crosswalk remains pending human validation.", "Associations do not establish causality or hypothesis confirmation.", "No quality dimensions were averaged into a composite score."]}
    dump(OUT / "h5_results.json", h5)
    manifest = {"schema_version": 1, "status": "frozen_ai_evaluation_h5", "api_calls": 0, "human_owner_r4_labels": 0, "ai_assigned_r4_labels": 100, "inputs": {str(p.relative_to(ROOT)): sha(p) for p in [OWNER, INDEX, PLAN, PAYLOADS, QA, RETRIEVAL]}, "artifacts": {str(p.relative_to(ROOT)): sha(p) for p in sorted(OUT.glob("*")) if p.name != "manifest.json"}}
    dump(OUT / "manifest.json", manifest); print(json.dumps({"agreement": agreement, "h5": h5}, indent=2))


if __name__ == "__main__": main()
