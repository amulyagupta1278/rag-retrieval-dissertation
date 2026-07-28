#!/usr/bin/env python3
"""Disclosed offline AI labeling for Phase 7 and exploratory H5 analysis."""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sentence_transformers import SentenceTransformer
from sklearn.metrics import cohen_kappa_score
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
EVAL = RUN / "evaluation_v1"
AUDIT = ROOT / "audits/phase7_generation/v2/evaluation_v2_ai"
OUT = RUN / "evaluation_v2_ai"
QA = ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl"
PER_QUERY = ROOT / "runs/v2/phase6_seed42_final/metrics/final_pooled_per_query.jsonl"
OWNER = EVAL / "phase7_owner_audit_26_COMPLETED.json"
DIMS = (
    "correctness", "faithfulness", "completeness", "citation_accuracy",
    "unsupported_claim_severity", "abstention_quality",
)
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
APPROVAL = (
    "Approve disclosed AI evaluation of remaining 144 Phase 7 answers, using frozen rubric "
    "and protected evidence only. Preserve 26 owner labels as human audit truth, measure "
    "AI-owner agreement, mark all other labels AI-assigned, run H5, update documentation, "
    "test, commit, and push. No additional API calls."
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(canonical(row) for row in rows))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def answer_path(record: dict) -> Path:
    return ROOT / record["validated_answer_path"]


def full_rows() -> list[dict]:
    plans = {r["blinded_request_id"]: r for r in load_jsonl(RUN / "sealed/request_plan.jsonl")}
    payloads = {r["blinded_request_id"]: r for r in load_jsonl(RUN / "blinded/request_payloads.jsonl")}
    coverage = {r["blinded_request_id"]: r for r in load_jsonl(RUN / "full_v2/sealed/coverage_manifest.jsonl")}
    qa = {r["question_id"]: r for r in load_jsonl(QA)}
    if not (set(plans) == set(payloads) == set(coverage)) or len(plans) != 170:
        raise ValueError("frozen Phase 7 inputs mismatch")
    rows = []
    for blinded_id in sorted(plans):
        plan = plans[blinded_id]
        payload = json.loads(payloads[blinded_id]["request"]["messages"][0]["content"])
        answer = load(answer_path(coverage[blinded_id]))["answer"]
        rows.append({
            "blinded_request_id": blinded_id,
            "question": payload["question"],
            "reference_answer": qa[plan["query_id"]]["reference_answer"],
            "evidence": payload["evidence"],
            "generated_answer": answer["answer"],
            "cited_evidence_ids": answer["cited_evidence_ids"],
            "abstained": answer["abstained"],
            "abstention_reason": answer["abstention_reason"],
        })
    return rows


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def jaccard(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a or b else 0.0


def build_features(rows: list[dict]) -> tuple[np.ndarray, str]:
    # Local-only prevents network access and makes this an offline evaluation.
    model = SentenceTransformer(MODEL_NAME, revision=MODEL_REVISION, local_files_only=True)
    texts = []
    for row in rows:
        answer = row["generated_answer"] or row["abstention_reason"]
        evidence = " ".join(item["text"] for item in row["evidence"])
        cited_ids = set(row["cited_evidence_ids"])
        cited = " ".join(item["text"] for item in row["evidence"] if item["evidence_id"] in cited_ids)
        texts.extend((row["question"], row["reference_answer"], answer, evidence, cited or evidence))
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    features = []
    for i, row in enumerate(rows):
        q, ref, ans, evidence, cited = embeddings[i * 5:(i + 1) * 5]
        answer_text = row["generated_answer"] or row["abstention_reason"]
        evidence_text = " ".join(item["text"] for item in row["evidence"])
        cited_ids = set(row["cited_evidence_ids"])
        cited_text = " ".join(item["text"] for item in row["evidence"] if item["evidence_id"] in cited_ids) or evidence_text
        features.append([
            float(ans @ ref), float(ans @ evidence), float(ans @ cited), float(ref @ evidence), float(q @ ans),
            jaccard(answer_text, row["reference_answer"]), jaccard(answer_text, evidence_text),
            jaccard(answer_text, cited_text), jaccard(row["reference_answer"], evidence_text),
            float(row["abstained"]) * 5.0, len(row["evidence"]) / 3.0,
            len(row["cited_evidence_ids"]) / 3.0, min(len(tokens(answer_text)) / 100.0, 2.0),
        ])
    revision = getattr(model, "model_card_data", None)
    return np.asarray(features, dtype=float), str(getattr(revision, "model_id", MODEL_NAME) or MODEL_NAME)


def classify(rows: list[dict], features: np.ndarray, owner_rows: list[dict]):
    index = {row["blinded_request_id"]: i for i, row in enumerate(rows)}
    owner_indices = [index[row["blinded_request_id"]] for row in owner_rows]
    scaler = StandardScaler().fit(features[owner_indices])
    x = scaler.transform(features)
    predictions = {dim: np.zeros(len(rows), dtype=int) for dim in DIMS}
    loo = {dim: [] for dim in DIMS}
    for dim in DIMS:
        y = np.asarray([row[dim] for row in owner_rows], dtype=int)
        for holdout in range(len(owner_indices)):
            train = [i for i in range(len(owner_indices)) if i != holdout]
            model = KNeighborsClassifier(n_neighbors=5, weights="distance")
            model.fit(x[[owner_indices[i] for i in train]], y[train])
            loo[dim].append(int(model.predict(x[[owner_indices[holdout]]])[0]))
        model = KNeighborsClassifier(n_neighbors=5, weights="distance")
        model.fit(x[owner_indices], y)
        predictions[dim] = model.predict(x).astype(int)
    agreement = {}
    for dim in DIMS:
        actual = [row[dim] for row in owner_rows]
        predicted = loo[dim]
        agreement[dim] = {
            "exact_n": sum(a == b for a, b in zip(actual, predicted)),
            "n": len(actual),
            "exact_rate": sum(a == b for a, b in zip(actual, predicted)) / len(actual),
            "cohen_kappa": float(cohen_kappa_score(actual, predicted)),
            "owner_distribution": dict(sorted(Counter(actual).items())),
            "ai_loo_distribution": dict(sorted(Counter(predicted).items())),
        }
    return predictions, agreement


def correlation(rows: list[dict], x_key: str, y_key: str, rng: random.Random) -> dict:
    x = [row[x_key] for row in rows]
    y = [row[y_key] for row in rows]
    point = float(spearmanr(x, y).statistic)
    query_ids = sorted({row["query_id"] for row in rows})
    grouped = {qid: [row for row in rows if row["query_id"] == qid] for qid in query_ids}
    draws = []
    for _ in range(10_000):
        sample = [row for _qid in range(len(query_ids)) for row in grouped[rng.choice(query_ids)]]
        stat = spearmanr([r[x_key] for r in sample], [r[y_key] for r in sample]).statistic
        if not math.isnan(stat):
            draws.append(float(stat))
    return {
        "x": x_key, "y": y_key, "spearman_rho": point, "record_n": len(rows), "query_n": 34,
        "bootstrap_samples": 10_000, "bootstrap_valid_n": len(draws),
        "ci95": [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
    }


def main() -> None:
    owner_doc = load(OWNER)
    owner_rows = owner_doc["rows"]
    if len(owner_rows) != 26 or any(type(row[d]) is not int for row in owner_rows for d in DIMS):
        raise SystemExit("owner audit invalid")
    rows = full_rows()
    owner_by_id = {row["blinded_request_id"]: row for row in owner_rows}
    features, resolved_model = build_features(rows)
    predictions, agreement = classify(rows, features, owner_rows)

    final = []
    for i, row in enumerate(rows):
        owner = owner_by_id.get(row["blinded_request_id"])
        scores = {dim: int(owner[dim] if owner else predictions[dim][i]) for dim in DIMS}
        final.append({
            **row, **scores,
            "label_source": "human_owner" if owner else "offline_ai_knn",
            "owner_notes": owner["owner_notes"] if owner else "",
            "ai_method": None if owner else "all-MiniLM-L6-v2 features + 5-NN trained on 26 owner labels",
        })
    if Counter(row["label_source"] for row in final) != {"offline_ai_knn": 144, "human_owner": 26}:
        raise ValueError("label-source counts mismatch")
    OUT.mkdir(parents=True, exist_ok=True)
    final_path = OUT / "final_quality_labels_170.jsonl"
    write_jsonl(final_path, final)

    agreement_report = {
        "schema_version": 1, "status": "complete",
        "method": "leave-one-owner-row-out 5-nearest-neighbor prediction",
        "embedding_model": MODEL_NAME, "embedding_model_revision": MODEL_REVISION,
        "resolved_model": resolved_model,
        "owner_audit_n": 26, "ai_labeled_n": 144, "owner_override_n": 26,
        "dimensions": agreement,
        "limitation": "Agreement estimates are internal cross-validation on a small audit sample, not independent human inter-rater reliability.",
    }
    write(OUT / "ai_owner_agreement.json", agreement_report)

    plans = {r["blinded_request_id"]: r for r in load_jsonl(RUN / "sealed/request_plan.jsonl")}
    retrieval = {r["row_id"]: r for r in load_jsonl(PER_QUERY)}
    joined = []
    for row in final:
        plan = plans[row["blinded_request_id"]]
        metric = retrieval[f'{plan["system_id"]}:{plan["query_id"]}']
        joined.append({
            "blinded_request_id": row["blinded_request_id"], "query_id": plan["query_id"],
            "category": plan["category"], "system": plan["system_id"], "label_source": row["label_source"],
            **{dim: row[dim] for dim in DIMS},
            "abstained": row["abstained"],
            "mrr_at_10": metric["metrics"]["mrr_at_10"],
            "graded_ndcg_at_10": metric["metrics"]["graded_ndcg_at_10"],
            "complete_evidence_recall_at_10": metric["metrics"]["complete_evidence_recall_at_10"],
        })
    write_jsonl(OUT / "h5_joined_query_system_rows.jsonl", joined)

    systems = {}
    for system in sorted({r["system"] for r in joined}):
        subset = [r for r in joined if r["system"] == system]
        systems[system] = {
            "n": len(subset), "abstention_n": sum(r["abstained"] for r in subset),
            "dimension_means": {dim: sum(r[dim] for r in subset) / len(subset) for dim in DIMS},
            "retrieval_means": {key: sum(r[key] for r in subset) / len(subset) for key in ("mrr_at_10", "graded_ndcg_at_10", "complete_evidence_recall_at_10")},
        }
    rng = random.Random(42)
    analyses = [
        correlation(joined, "mrr_at_10", "faithfulness", rng),
        correlation(joined, "mrr_at_10", "correctness", rng),
        correlation(joined, "graded_ndcg_at_10", "correctness", rng),
        correlation(joined, "complete_evidence_recall_at_10", "completeness", rng),
    ]
    h5 = {
        "schema_version": 1, "status": "complete_exploratory_ai_evaluated",
        "hypothesis": "Retrieval quality (MRR) does not translate monotonically into generation faithfulness; retrieval and generation require separate evaluation.",
        "label_sources": {"human_owner": 26, "offline_ai_knn": 144},
        "bootstrap": {"unit": "whole query preserving five-system panel", "samples": 10_000, "seed": 42},
        "correlations": analyses, "system_summaries": systems,
        "decision": "exploratory_descriptive_only",
        "decision_reason": "Frozen protocol defines analysis but no minimum effect or confirmatory H5 decision threshold.",
        "interpretation_limits": [
            "AI-assigned labels dominate full panel (144/170).",
            "Owner audit is 26 records and is not independent inter-rater evaluation.",
            "Associations do not establish causality or universal system superiority.",
            "No dimensions were averaged into a composite score.",
        ],
    }
    write(OUT / "h5_results.json", h5)

    approval = {"schema_version": 1, "status": "owner_approved", "statement": APPROVAL, "api_calls_authorized": False}
    write(AUDIT / "owner_approval.json", approval)
    artifacts = [final_path, OUT / "ai_owner_agreement.json", OUT / "h5_joined_query_system_rows.jsonl", OUT / "h5_results.json", AUDIT / "owner_approval.json"]
    manifest = {
        "schema_version": 1, "status": "phase7_complete_ai_evaluated",
        "owner_label_n": 26, "ai_assigned_label_n": 144, "api_call_n": 0,
        "owner_input_sha256": sha(OWNER), "h5_protocol_sha256": sha(RUN / "h5_protocol.json"),
        "artifacts": {str(p.relative_to(ROOT)): sha(p) for p in artifacts},
    }
    write(AUDIT / "freeze_manifest.json", manifest)
    print(json.dumps({"agreement": agreement_report, "h5": h5, "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
