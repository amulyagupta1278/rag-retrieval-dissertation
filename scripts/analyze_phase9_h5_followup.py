#!/usr/bin/env python3
"""Run preregistered Phase 9 H5 analysis after workbook and sealed-map completion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from scipy.stats import spearmanr

from validate_phase9_h5_followup import validate


SEED = 42
SAMPLES = 10_000


def jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sheet_rows(path: Path, sheet: str):
    wb = load_workbook(path, data_only=True, read_only=True)
    ws = wb[sheet]
    header = [cell.value for cell in ws[1]]
    return [dict(zip(header, row)) for row in ws.iter_rows(min_row=2, values_only=True)]


def faith(row, partial_weight=0.5):
    total = row["final_total_claims"]
    if not total:
        return None
    return (row["final_fully_supported"] + partial_weight * row["final_partially_supported"]) / total


def describe(rows, values):
    if not values:
        return {"answer_n": 0, "distinct_n": 0, "sd": None, "spearman_rho": None}
    rho = spearmanr([row["mrr@10"] for row in rows], values).statistic if len(set(values)) > 1 else None
    return {
        "answer_n": len(values), "distinct_n": len(set(round(value, 12) for value in values)),
        "sd": float(np.std(values, ddof=1)) if len(values) > 1 else None,
        "spearman_rho": None if rho is None or np.isnan(rho) else float(rho),
    }


def clustered_ci(rows, y_values):
    query_ids = sorted({row["query_id"] for row in rows})
    grouped = {qid: [i for i, row in enumerate(rows) if row["query_id"] == qid] for qid in query_ids}
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(SAMPLES):
        indices = [idx for qid in rng.choice(query_ids, len(query_ids), replace=True) for idx in grouped[qid]]
        rho = spearmanr([rows[i]["mrr@10"] for i in indices], [y_values[i] for i in indices]).statistic
        if not np.isnan(rho):
            draws.append(float(rho))
    return [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))], len(draws)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("sealed_mapping", type=Path, help="JSONL: answer_slot_id, query_id, system_id, mrr@10")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate(args.workbook, require_complete=True)
    adjudicated = {row["answer_slot_id"]: row for row in sheet_rows(args.workbook, "Adjudication")}
    mapping = jsonl(args.sealed_mapping)
    if len(mapping) != 150 or len({row["answer_slot_id"] for row in mapping}) != 150:
        raise ValueError("sealed mapping must contain 150 unique answer slots")
    rows, excluded = [], 0
    conservative_values = []
    for item in mapping:
        adjudicated_row = adjudicated[item["answer_slot_id"]]
        score = faith(adjudicated_row)
        if score is None:
            excluded += 1
            continue
        rows.append({**item, "faithfulness": score})
        conservative_values.append(faith(adjudicated_row, partial_weight=0.0))
    mapped_question_n = len({row["query_id"] for row in mapping})
    if mapped_question_n < 30:
        raise ValueError("sealed panel requires 30 questions")
    y = [row["faithfulness"] for row in rows]
    rho = float(spearmanr([row["mrr@10"] for row in rows], y).statistic)
    ci, valid_draws = clustered_ci(rows, y)
    sd = float(np.std(y, ddof=1))
    distinct = len(set(round(value, 12) for value in y))
    coverage = len(rows) / 150
    supported = coverage >= 0.8 and sd >= 0.10 and distinct >= 3 and abs(rho) < 0.20 and ci[0] >= -0.30 and ci[1] <= 0.30
    estimable = coverage >= 0.8 and sd >= 0.10 and distinct >= 3
    prompt_sensitivity = {}
    for version in sorted({row["prompt_version"] for row in rows}):
        selected = [row for row in rows if row["prompt_version"] == version]
        prompt_sensitivity[version] = describe(selected, [row["faithfulness"] for row in selected])
    total_claims = sum(adjudicated[item["answer_slot_id"]]["final_total_claims"] or 0 for item in mapping)
    fully_supported = sum(adjudicated[item["answer_slot_id"]]["final_fully_supported"] or 0 for item in mapping)
    partially_supported = sum(adjudicated[item["answer_slot_id"]]["final_partially_supported"] or 0 for item in mapping)
    unsupported = sum(adjudicated[item["answer_slot_id"]]["final_unsupported"] or 0 for item in mapping)
    contradicted = sum(adjudicated[item["answer_slot_id"]]["final_contradicted"] or 0 for item in mapping)
    result = {
        "hypothesis": "H5",
        "decision": "supported" if supported else ("not_supported" if estimable else "not_estimable"),
        "answer_n": len(rows),
        "question_n": mapped_question_n,
        "claim_bearing_question_n": len({row["query_id"] for row in rows}),
        "excluded_no_verifiable_claims_n": excluded,
        "faithfulness_sd": sd,
        "faithfulness_distinct_n": distinct,
        "spearman_rho": rho,
        "ci95": ci,
        "bootstrap_samples": SAMPLES,
        "bootstrap_valid_n": valid_draws,
        "seed": SEED,
        "primary_score": "(fully_supported + 0.5*partially_supported) / total_verifiable_claims",
        "claim_counts": {"total": total_claims, "fully_supported": fully_supported, "partially_supported": partially_supported, "unsupported": unsupported, "contradicted": contradicted},
        "aggregate_claim_weighted_faithfulness": (fully_supported + 0.5 * partially_supported) / total_claims,
        "sensitivity": {
            "partial_support_zero_credit": describe(rows, conservative_values),
            "prompt_version": prompt_sensitivity,
            "reviewer_A_equals_reviewer_B_all_150_rows": True,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
