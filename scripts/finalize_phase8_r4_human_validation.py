#!/usr/bin/env python3
"""Freeze owner-reviewed Phase 8 R4 labels and recalculate offline results."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import shutil
import statistics
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

from evaluate_phase8_r4_five_systems import SYSTEMS, latency, load, means, metric, permutation


ROOT = Path(__file__).resolve().parents[1]
ZIP = Path("/Users/amulyagupta/Downloads/files.zip")
BASE = ROOT / "runs/phase8_r4_improvements"
OUT = ROOT / "runs/phase8_r4_human_validated"
AUDIT = ROOT / "audits/phase8_r4_human_validated"
ORIGINALS = ROOT / "submission/human_review/phase8_r4"
DIMS = [
    "correctness",
    "faithfulness",
    "completeness",
    "citation_accuracy",
    "unsupported_claim_severity",
    "abstention_quality",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def validate_completed(original: Path, completed: Path, expected_n: int) -> list[dict[str, str]]:
    source = read_csv(original)
    rows = read_csv(completed)
    if len(source) != expected_n or len(rows) != expected_n:
        raise ValueError(f"row count mismatch: {completed.name}")
    if len({row["review_row_id"] for row in rows}) != expected_n:
        raise ValueError(f"duplicate review IDs: {completed.name}")
    human = [name for name in source[0] if name.startswith("human_")]
    protected = [name for name in source[0] if name not in human]
    for index, (before, after) in enumerate(zip(source, rows), 1):
        for name in protected:
            if before[name] != after[name]:
                raise ValueError(f"protected mismatch {completed.name}:{index}:{name}")
    return rows


def correlation(joined: list[dict], x_key: str, y_key: str, rng: random.Random) -> dict:
    point = float(spearmanr([r[x_key] for r in joined], [r[y_key] for r in joined]).statistic)
    qids = sorted({r["query_id"] for r in joined})
    grouped = {qid: [r for r in joined if r["query_id"] == qid] for qid in qids}
    draws = []
    for _ in range(10_000):
        sample = [row for _ in qids for row in grouped[rng.choice(qids)]]
        value = spearmanr([r[x_key] for r in sample], [r[y_key] for r in sample]).statistic
        if not math.isnan(value):
            draws.append(float(value))
    return {
        "x": x_key,
        "y": y_key,
        "status": "not_estimable_constant_dimension" if math.isnan(point) else "estimated",
        "spearman_rho": None if math.isnan(point) else point,
        "record_n": len(joined),
        "query_n": len(qids),
        "bootstrap_samples": 10_000,
        "bootstrap_valid_n": len(draws),
        "ci95": None
        if not draws
        else [float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))],
    }


def main() -> None:
    if OUT.exists() or AUDIT.exists():
        raise SystemExit("human-validated R4 output exists; refusing overwrite")
    if not ZIP.is_file():
        raise SystemExit(f"missing approved ZIP: {ZIP}")

    names = {
        "mapping": "phase8_r4_gold_mapping_review_140_COMPLETED.csv",
        "generation": "phase8_r4_generation_human_review_100_COMPLETED.csv",
        "synthesis": "phase8_r4_synthesis_candidate_review_20_COMPLETED.csv",
    }
    with TemporaryDirectory() as temporary:
        temporary_path = Path(temporary)
        with zipfile.ZipFile(ZIP) as archive:
            if set(archive.namelist()) != set(names.values()):
                raise ValueError("ZIP member set differs from approved three files")
            archive.extractall(temporary_path)
        mapping = validate_completed(
            ORIGINALS / "phase8_r4_gold_mapping_review_140.csv",
            temporary_path / names["mapping"],
            140,
        )
        generation = validate_completed(
            ORIGINALS / "phase8_r4_generation_human_review_100_BLINDED.csv",
            temporary_path / names["generation"],
            100,
        )
        synthesis = validate_completed(
            ORIGINALS / "phase8_r4_synthesis_candidate_review_20.csv",
            temporary_path / names["synthesis"],
            20,
        )

        if Counter(row["human_mapping_decision_valid_invalid_uncertain"] for row in mapping) != {
            "valid": 140
        }:
            raise ValueError("mapping decisions differ from owner approval")
        if Counter(row["human_relevance_grade_0_1_2_U"] for row in mapping) != {
            "2": 139,
            "0": 1,
        }:
            raise ValueError("mapping grade distribution differs from owner approval")
        for row in generation:
            for dim in DIMS:
                value = row[f"human_{dim}_0_1_2"]
                if value not in {"0", "1", "2"}:
                    raise ValueError(f"invalid generation grade: {dim}={value}")
        if Counter(row["human_overall_accept_reject_revise"] for row in synthesis) != {
            "accept": 12,
            "revise": 4,
            "reject": 4,
        }:
            raise ValueError("synthesis disposition differs from owner approval")

        inputs = OUT / "owner_inputs"
        inputs.mkdir(parents=True)
        for member in names.values():
            shutil.copyfile(temporary_path / member, inputs / member)

    qa = load(BASE / "benchmark/qa_dev_test.jsonl")
    qmeta = {row["question_id"]: row for row in qa}
    gold: dict[str, set[str]] = defaultdict(set)
    qrel_rows = []
    for row in mapping:
        grade = int(row["human_relevance_grade_0_1_2_U"])
        qrel_rows.append(
            {
                "query_id": row["query_id"],
                "chunk_id": row["new_chunk_id"],
                "grade": grade,
                "owner_mapping_decision": row[
                    "human_mapping_decision_valid_invalid_uncertain"
                ],
                "review_row_id": row["review_row_id"],
            }
        )
        if grade > 0:
            gold[row["query_id"]].add(row["new_chunk_id"])
    if len(qrel_rows) != 140 or sum(row["grade"] == 0 for row in qrel_rows) != 1:
        raise ValueError("owner qrels failed final validation")
    qrels_dir = OUT / "qrels"
    qrels_dir.mkdir()
    (qrels_dir / "owner_qrels_140.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in qrel_rows), encoding="utf-8"
    )
    with (qrels_dir / "owner_qrels_140.tsv").open("w", encoding="utf-8", newline="") as stream:
        stream.write("query_id\tchunk_id\tgrade\n")
        for row in qrel_rows:
            stream.write(f"{row['query_id']}\t{row['chunk_id']}\t{row['grade']}\n")

    evaluated, summaries = {}, {}
    for system, path in SYSTEMS.items():
        run = load(path)
        ranking = {row["query_id"]: [x["chunk_id"] for x in row["results"]] for row in run}
        rows = [
            {
                "query_id": qid,
                "split": qmeta[qid]["split"],
                "category": qmeta[qid]["category"],
                "metrics": metric(ranking[qid], gold[qid]),
            }
            for qid in sorted(qmeta)
        ]
        evaluated[system] = rows
        summaries[system] = {
            "development": means([r for r in rows if r["split"] == "dev"]),
            "locked_test": means([r for r in rows if r["split"] == "test"]),
            "all_100_descriptive": means(rows),
            "locked_test_by_category": {
                category: means(
                    [r for r in rows if r["split"] == "test" and r["category"] == category]
                )
                for category in sorted({r["category"] for r in rows})
            },
            "latency": latency(run, system),
        }
    comparisons = []
    test_ids = sorted(qid for qid, row in qmeta.items() if row["split"] == "test")
    by_system = {system: {r["query_id"]: r for r in rows} for system, rows in evaluated.items()}
    for left, right in combinations(SYSTEMS, 2):
        result = permutation(
            [by_system[left][qid]["metrics"]["ndcg@10"] for qid in test_ids],
            [by_system[right][qid]["metrics"]["ndcg@10"] for qid in test_ids],
        )
        comparisons.append({"left": left, "right": right, "metric": "ndcg@10", **result})
    ordered = sorted(
        enumerate(comparisons), key=lambda item: item[1]["paired_randomization_p_two_sided"]
    )
    running = 0.0
    for rank, (index, row) in enumerate(ordered, 1):
        adjusted = min(
            1.0, row["paired_randomization_p_two_sided"] * (len(ordered) - rank + 1)
        )
        running = max(running, adjusted)
        comparisons[index]["holm_adjusted_p"] = running
    evaluation_dir = OUT / "retrieval_evaluation"
    evaluation_dir.mkdir()
    (evaluation_dir / "metrics.json").write_text(
        stable(
            {
                "status": "owner_validated_r4_complete",
                "primary_scope": "40-query locked test",
                "qrel_status": "owner-reviewed 140-row crosswalk with one intentional grade 0",
                "systems": summaries,
            }
        ),
        encoding="utf-8",
    )
    (evaluation_dir / "per_query.json").write_text(stable(evaluated), encoding="utf-8")
    (evaluation_dir / "exploratory_statistics.json").write_text(
        stable(
            {
                "status": "exploratory_owner_validated_not_preregistered",
                "method": "10,000 paired sign-flip randomizations and paired bootstrap percentile CI; seed 42; Holm across 10 pairwise nDCG@10 comparisons",
                "no_hypothesis_support_claimed": True,
                "comparisons": comparisons,
            }
        ),
        encoding="utf-8",
    )

    plans = {
        row["blinded_request_id"]: row
        for row in load(BASE / "generation_r4_freeze/request_plan.jsonl")
    }
    labels = []
    for row in generation:
        record = {
            "review_row_id": row["review_row_id"],
            "blinded_request_id": row["blinded_request_id"],
            "question": row["question"],
            "reference_answer": row["reference_answer"],
            "generated_answer": row["generated_answer"],
            "abstained": row["model_abstained"].lower() == "true",
            "abstention_reason": row["model_abstention_reason"],
            "cited_evidence_ids": [
                value.strip()
                for value in row["cited_evidence_ids"].split("|")
                if value.strip()
            ],
            "label_source": "human_owner_phase8_r4",
            "human_label": True,
            "owner_notes": row["human_notes"],
        }
        record.update({dim: int(row[f"human_{dim}_0_1_2"]) for dim in DIMS})
        labels.append(record)
    labels.sort(key=lambda row: row["blinded_request_id"])
    generation_dir = OUT / "generation_evaluation"
    generation_dir.mkdir()
    (generation_dir / "human_quality_labels_100.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in labels),
        encoding="utf-8",
    )

    old_ai = {
        row["blinded_request_id"]: row
        for row in load(BASE / "evaluation_ai_h5/ai_quality_labels_100.jsonl")
    }
    agreement = {"dimensions": {}, "record_n": 100, "status": "owner_vs_prior_ai_same_rows"}
    for dim in DIMS:
        owner_values = [row[dim] for row in labels]
        ai_values = [old_ai[row["blinded_request_id"]][dim] for row in labels]
        kappa = float(cohen_kappa_score(owner_values, ai_values))
        agreement["dimensions"][dim] = {
            "exact_agreement": sum(a == b for a, b in zip(owner_values, ai_values)) / 100,
            "cohen_kappa": None if math.isnan(kappa) else kappa,
            "owner_distribution": dict(sorted(Counter(owner_values).items())),
            "prior_ai_distribution": dict(sorted(Counter(ai_values).items())),
        }
    (generation_dir / "owner_ai_agreement.json").write_text(stable(agreement), encoding="utf-8")

    joined = []
    metric_index = {
        system: {row["query_id"]: row["metrics"] for row in rows}
        for system, rows in evaluated.items()
    }
    labels_by_id = {row["blinded_request_id"]: row for row in labels}
    for blind, plan in plans.items():
        label = labels_by_id[blind]
        metrics = metric_index[plan["system_id"]][plan["query_id"]]
        joined.append(
            {
                "blinded_request_id": blind,
                "query_id": plan["query_id"],
                "category": plan["category"],
                "system": plan["system_id"],
                "label_source": label["label_source"],
                **{dim: label[dim] for dim in DIMS},
                "abstained": label["abstained"],
                "mrr@10": metrics["mrr@10"],
                "ndcg@10": metrics["ndcg@10"],
                "recall@10": metrics["recall@10"],
            }
        )
    joined.sort(key=lambda row: row["blinded_request_id"])
    (generation_dir / "h5_joined_100.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in joined), encoding="utf-8"
    )
    system_summaries = {}
    for system in sorted({row["system"] for row in joined}):
        subset = [row for row in joined if row["system"] == system]
        system_summaries[system] = {
            "n": len(subset),
            "abstention_n": sum(row["abstained"] for row in subset),
            "dimension_means": {
                dim: statistics.fmean(row[dim] for row in subset) for dim in DIMS
            },
            "retrieval_means": {
                name: statistics.fmean(row[name] for row in subset)
                for name in ("mrr@10", "ndcg@10", "recall@10")
            },
        }
    rng = random.Random(42)
    analyses = [
        correlation(joined, "mrr@10", "faithfulness", rng),
        correlation(joined, "mrr@10", "correctness", rng),
        correlation(joined, "ndcg@10", "correctness", rng),
        correlation(joined, "recall@10", "completeness", rng),
    ]
    h5 = {
        "schema_version": 1,
        "status": "complete_exploratory_owner_evaluated",
        "hypothesis": "Retrieval quality does not guarantee generation faithfulness; retrieval and generation require separate evaluation.",
        "label_sources": {"human_owner_phase8_r4": 100},
        "qrel_status": "owner-reviewed 140-row crosswalk",
        "bootstrap": {"unit": "whole query preserving five-system panel", "samples": 10_000, "seed": 42},
        "correlations": analyses,
        "system_summaries": system_summaries,
        "decision": "exploratory_descriptive_only",
        "decision_reason": "R4 analysis was not preregistered and has no frozen effect threshold; owner labels remove prior automated-label limitation but do not make R4 confirmatory.",
        "interpretation_limits": [
            "R4 statistical analysis remains exploratory and not preregistered.",
            "Owner review is single-rater, not independent inter-rater replication.",
            "Associations do not establish causality or universal superiority.",
            "No quality dimensions were averaged into a composite score.",
        ],
    }
    (generation_dir / "h5_results.json").write_text(stable(h5), encoding="utf-8")

    synthesis_records = []
    for row in synthesis:
        synthesis_records.append(
            {
                "review_row_id": row["review_row_id"],
                "question_id": row["question_id"],
                "question": row["question"],
                "reference_answer": row["reference_answer"],
                "disposition": row["human_overall_accept_reject_revise"],
                "question_valid": row["human_question_valid_yes_no_uncertain"],
                "reference_answer_valid": row[
                    "human_reference_answer_valid_yes_no_uncertain"
                ],
                "evidence_complete": row["human_evidence_complete_yes_no_uncertain"],
                "revised_question": row["human_revised_question_if_needed"],
                "revised_reference_answer": row[
                    "human_revised_reference_answer_if_needed"
                ],
                "owner_notes": row["human_notes"],
                "primary_metrics_included": False,
            }
        )
    synthesis_dir = OUT / "synthesis_review"
    synthesis_dir.mkdir()
    (synthesis_dir / "owner_dispositions_20.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in synthesis_records),
        encoding="utf-8",
    )
    synthesis_summary = {
        "status": "owner_review_complete_pending_revision_work",
        "total": 20,
        "dispositions": dict(
            sorted(Counter(row["disposition"] for row in synthesis_records).items())
        ),
        "primary_metrics_included": 0,
        "revision_required_ids": [
            row["question_id"]
            for row in synthesis_records
            if row["disposition"] in {"revise", "reject"}
        ],
    }
    (synthesis_dir / "summary.json").write_text(stable(synthesis_summary), encoding="utf-8")

    old_metrics = json.loads((BASE / "evaluation_r4/metrics.json").read_text())
    changes = {}
    for system, summary in summaries.items():
        changes[system] = {
            metric_name: summary["locked_test"][metric_name]
            - old_metrics["systems"][system]["locked_test"][metric_name]
            for metric_name in summary["locked_test"]
        }
    (OUT / "change_report.json").write_text(
        stable(
            {
                "automated_source_preserved": True,
                "intentional_zero_grade_n": 1,
                "locked_test_metric_deltas_owner_minus_automatic": changes,
                "generation_label_source_changed_from": "offline_ai_knn_transfer_from_phase7_owner26",
                "generation_label_source_changed_to": "human_owner_phase8_r4",
            }
        ),
        encoding="utf-8",
    )

    AUDIT.mkdir(parents=True)
    status = {
        "schema_version": 1,
        "status": "owner_validated_r4_complete",
        "documents": 130,
        "chunks": 954,
        "primary_questions": 100,
        "systems": 5,
        "owner_reviewed_mapping_rows": 140,
        "owner_relevance_grade_distribution": {"0": 1, "2": 139},
        "owner_reviewed_generation_rows": 100,
        "owner_reviewed_synthesis_rows": 20,
        "synthesis_dispositions": synthesis_summary["dispositions"],
        "synthesis_primary_metrics_included": False,
        "human_validation_complete": True,
        "r4_claim_class": "human-owner-validated exploratory scaling evidence",
        "canonical_dissertation_evidence": "V2 pilot remains canonical confirmatory evidential base",
        "api_calls": 0,
        "automated_r4_evidence_preserved": True,
        "approved_zip_sha256": sha(ZIP),
    }
    (AUDIT / "canonical_status.json").write_text(stable(status), encoding="utf-8")
    artifacts = {
        str(path.relative_to(ROOT)): sha(path)
        for path in sorted(OUT.rglob("*"))
        if path.is_file()
    }
    manifest = {
        "schema_version": 1,
        "status": "frozen_phase8_r4_human_validation",
        "approved_zip": {"path": str(ZIP), "sha256": sha(ZIP)},
        "api_calls": 0,
        "protected_automated_artifacts_modified": 0,
        "artifacts": artifacts,
    }
    (AUDIT / "manifest.json").write_text(stable(manifest), encoding="utf-8")
    print(stable({"status": status, "locked_test_metrics": {k: v["locked_test"] for k, v in summaries.items()}, "h5": h5, "synthesis": synthesis_summary}))


if __name__ == "__main__":
    main()
