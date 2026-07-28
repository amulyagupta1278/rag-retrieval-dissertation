#!/usr/bin/env python3
"""Freeze canonical completed seed-42 regrade and final owner adjudication."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.finalize_phase6_seed42 import (  # noqa: E402
    ADJUDICATION_FIELDS,
    FIRST_PASS_FIELDS,
    GRADES,
    PROTECTED_FIELDS,
    csv_bytes,
    kappa,
    read_csv,
)
from src.utils.atomic_io import write_bytes, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402

REQUIRED_REGRADE_FIELDS = (
    "display_id",
    "query_id",
    "question",
    "reference_answer",
    "chunk_id",
    "source_document_title",
    "candidate_chunk",
    "second_relevance_grade",
    "second_rationale",
)
FINAL_LABEL_FIELDS = (
    "display_id",
    "query_id",
    "chunk_id",
    "final_relevance_grade",
    "label_source",
    "adjudication_rationale",
)
EXPECTED_REGRADE_SHA256 = "e12c4c427ddf7b5ea58063c19e3063ddfcf223b2762ee2089e8434b26dc9bc00"
EXPECTED_ADJUDICATION_SHA256 = "9fd10b3267fbcd339c3ce65b2c5796a99b17672f69c32d4a39cbdc9055fa4aa7"


def parse_qrels(path: Path) -> dict[tuple[str, str], str]:
    """Read four-column TSV qrels, rejecting malformed or duplicate pairs."""
    result: dict[tuple[str, str], str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split("\t")
        if len(fields) != 4 or fields[1] != "0" or fields[3] not in GRADES:
            raise ValueError(f"malformed qrel at {path}:{line_number}")
        key = (fields[0], fields[2])
        if key in result:
            raise ValueError(f"duplicate qrel at {path}:{line_number}")
        result[key] = fields[3]
    if not result:
        raise ValueError(f"empty qrels: {path}")
    return result


def distribution(values: list[str]) -> dict[str, int]:
    return {grade: Counter(values)[grade] for grade in sorted(GRADES)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-pass", type=Path, required=True)
    parser.add_argument("--blank-sample", type=Path, required=True)
    parser.add_argument("--sealed-provenance", type=Path, required=True)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--completed-regrade", type=Path, required=True)
    parser.add_argument("--owner-adjudication", type=Path, required=True)
    parser.add_argument("--owner-authorization", type=Path, required=True)
    parser.add_argument("--historical-invalid-qrels", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--validation-timestamp", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    output_root = args.output_root
    if output_root.exists() and any(output_root.iterdir()) and not args.overwrite:
        raise FileExistsError(f"output root non-empty; pass --overwrite: {output_root}")

    authorization = json.loads(args.owner_authorization.read_text(encoding="utf-8"))
    sample_manifest = json.loads(args.sample_manifest.read_text(encoding="utf-8"))
    sealed = json.loads(args.sealed_provenance.read_text(encoding="utf-8"))
    expected_authorization = authorization["completed_human_regrade"]["expected_sha256"]
    if expected_authorization != EXPECTED_REGRADE_SHA256:
        raise ValueError("authorization regrade hash differs from canonical contract")
    if authorization["final_owner_adjudication"]["expected_sha256"] != EXPECTED_ADJUDICATION_SHA256:
        raise ValueError("authorization adjudication hash differs from canonical contract")
    if sha256_file(args.completed_regrade) != EXPECTED_REGRADE_SHA256:
        raise ValueError("completed human regrade SHA-256 mismatch")
    if sha256_file(args.owner_adjudication) != EXPECTED_ADJUDICATION_SHA256:
        raise ValueError("owner adjudication SHA-256 mismatch")
    if sha256_file(args.first_pass) != sample_manifest["source_csv_sha256"]:
        raise ValueError("first-pass SHA-256 differs from seed-42 sample manifest")
    if sha256_file(args.blank_sample) != sample_manifest["regrade_package_sha256"]:
        raise ValueError("blank seed-42 sample SHA-256 mismatch")
    if sha256_file(args.sealed_provenance) != sample_manifest["sealed_provenance_sha256"]:
        raise ValueError("sealed seed-42 provenance SHA-256 mismatch")
    if sample_manifest.get("seed") != 42 or sample_manifest.get("stratified") is not False:
        raise ValueError("sample is not blind simple-random seed-42 sample")

    first_rows = read_csv(args.first_pass, FIRST_PASS_FIELDS)
    blank_rows = read_csv(args.blank_sample, REQUIRED_REGRADE_FIELDS)
    regrade_rows = read_csv(args.completed_regrade, REQUIRED_REGRADE_FIELDS)
    adjudication_rows = read_csv(args.owner_adjudication, ADJUDICATION_FIELDS)
    if (len(first_rows), len(blank_rows), len(regrade_rows), len(adjudication_rows)) != (
        755,
        114,
        114,
        14,
    ):
        raise ValueError("required row counts are first=755, sample=114, regrade=114, adjudication=14")
    if len({(row["query_id"], row["chunk_id"]) for row in regrade_rows}) != 114:
        raise ValueError("duplicate query/chunk pair in completed regrade")
    if any(row["second_relevance_grade"] not in GRADES for row in regrade_rows):
        raise ValueError("completed regrade contains blank, U, or invalid grade")

    first_by_id = {row["display_id"]: row for row in first_rows}
    blank_by_id = {row["display_id"]: row for row in blank_rows}
    regrade_by_id = {row["display_id"]: row for row in regrade_rows}
    sealed_by_id = {row["display_id"]: row for row in sealed["rows"]}
    if set(blank_by_id) != set(regrade_by_id) or set(blank_by_id) != set(sealed_by_id):
        raise ValueError("completed regrade membership differs from exact seed-42 sample")
    for display_id, regrade in regrade_by_id.items():
        blank = blank_by_id[display_id]
        first = first_by_id.get(display_id)
        if first is None:
            raise ValueError(f"sample ID missing from first pass: {display_id}")
        for field in (
            "query_id",
            "question",
            "reference_answer",
            "chunk_id",
            "source_document_title",
            "candidate_chunk",
        ):
            if regrade[field] != blank[field] or regrade[field] != first[field]:
                raise ValueError(f"protected regrade mismatch: {display_id} {field}")
        if sealed_by_id[display_id]["first_pass_grade"] != first["relevance_grade"]:
            raise ValueError(f"sealed first-pass mismatch: {display_id}")

    disagreement_ids = {
        display_id
        for display_id, regrade in regrade_by_id.items()
        if regrade["second_relevance_grade"]
        != sealed_by_id[display_id]["first_pass_grade"]
    }
    adjudication_by_id = {row["display_id"]: row for row in adjudication_rows}
    if disagreement_ids != set(adjudication_by_id) or len(disagreement_ids) != 14:
        raise ValueError("owner adjudication IDs differ from exact human disagreement set")
    for display_id, row in adjudication_by_id.items():
        regrade = regrade_by_id[display_id]
        first = first_by_id[display_id]
        for field in PROTECTED_FIELDS:
            if row[field] != regrade[field]:
                raise ValueError(f"protected adjudication mismatch: {display_id} {field}")
        if row["first_pass_grade"] != first["relevance_grade"]:
            raise ValueError(f"adjudication first-pass mismatch: {display_id}")
        if row["second_pass_grade"] != regrade["second_relevance_grade"]:
            raise ValueError(f"adjudication second-pass mismatch: {display_id}")
        if row["final_grade"] not in GRADES or not row["owner_rationale"].strip():
            raise ValueError(f"invalid final owner decision: {display_id}")
        if row["grade_transition"] != f"{row['first_pass_grade']} → {row['second_pass_grade']}":
            raise ValueError(f"invalid adjudication transition: {display_id}")
    if Counter(row["final_grade"] for row in adjudication_rows) != Counter({"1": 3, "2": 11}):
        raise ValueError("owner adjudication final grade distribution differs")

    first_grades = [int(first_by_id[row["display_id"]]["relevance_grade"]) for row in regrade_rows]
    second_grades = [int(row["second_relevance_grade"]) for row in regrade_rows]
    agreement_n = sum(left == right for left, right in zip(first_grades, second_grades))
    confusion = {
        str(left): {
            str(right): sum(
                a == left and b == right for a, b in zip(first_grades, second_grades)
            )
            for right in range(3)
        }
        for left in range(3)
    }
    per_grade = {}
    for grade in range(3):
        denominator = sum(value == grade for value in first_grades)
        numerator = sum(
            left == right == grade for left, right in zip(first_grades, second_grades)
        )
        per_grade[str(grade)] = {
            "agreement": numerator / denominator if denominator else None,
            "agreement_n": numerator,
            "first_pass_n": denominator,
        }
    transitions = Counter(f"{left}->{right}" for left, right in zip(first_grades, second_grades))
    agreement_report = {
        "cohen_kappa_quadratic_weighted": kappa(first_grades, second_grades, quadratic=True),
        "cohen_kappa_unweighted": kappa(first_grades, second_grades, quadratic=False),
        "confusion_matrix_first_rows_second_columns": confusion,
        "disagreement_n": len(regrade_rows) - agreement_n,
        "exact_agreement": agreement_n / len(regrade_rows),
        "exact_agreement_n": agreement_n,
        "first_pass_distribution": distribution([str(value) for value in first_grades]),
        "per_first_pass_grade_agreement": per_grade,
        "sample_n": len(regrade_rows),
        "second_pass_distribution": distribution([str(value) for value in second_grades]),
        "transition_counts": dict(sorted(transitions.items())),
        "u_n": 0,
    }
    if agreement_n != 100 or len(disagreement_ids) != 14:
        raise ValueError("human agreement result differs from expected 100/114")

    provenance_rows: list[dict[str, Any]] = []
    final_rows: list[dict[str, str]] = []
    sampled_ids = set(regrade_by_id)
    for first in sorted(first_rows, key=lambda row: row["display_id"]):
        display_id = first["display_id"]
        regrade = regrade_by_id.get(display_id)
        adjudication = adjudication_by_id.get(display_id)
        if adjudication:
            grade = adjudication["final_grade"]
            source = "owner_adjudication"
            rationale = adjudication["owner_rationale"]
        elif regrade:
            if regrade["second_relevance_grade"] != first["relevance_grade"]:
                raise ValueError(f"unadjudicated disagreement: {display_id}")
            grade = regrade["second_relevance_grade"]
            source = "seed42_regrade_agreement"
            rationale = ""
        else:
            grade = first["relevance_grade"]
            source = "first_pass_unsampled"
            rationale = first["rationale"]
        final = {
            "display_id": display_id,
            "query_id": first["query_id"],
            "chunk_id": first["chunk_id"],
            "final_relevance_grade": grade,
            "label_source": source,
            "adjudication_rationale": rationale,
        }
        final_rows.append(final)
        provenance_rows.append(
            {
                "adjudication_rationale": rationale,
                "chunk_id": first["chunk_id"],
                "display_id": display_id,
                "final_relevance_grade": int(grade),
                "first_pass_grade": int(first["relevance_grade"]),
                "label_source": source,
                "query_id": first["query_id"],
                "second_pass_grade": (
                    int(regrade["second_relevance_grade"]) if display_id in sampled_ids else None
                ),
            }
        )
    source_counts = Counter(row["label_source"] for row in final_rows)
    grade_counts = Counter(row["final_relevance_grade"] for row in final_rows)
    if source_counts != Counter(
        {"first_pass_unsampled": 641, "seed42_regrade_agreement": 100, "owner_adjudication": 14}
    ):
        raise ValueError(f"final label source counts differ: {dict(source_counts)}")
    if grade_counts != Counter({"0": 572, "1": 89, "2": 94}):
        raise ValueError(f"final grade distribution differs: {dict(grade_counts)}")
    if len({(row["query_id"], row["chunk_id"]) for row in final_rows}) != 755:
        raise ValueError("duplicate final query/chunk pair")

    qrel_rows = sorted(
        (row["query_id"], "0", row["chunk_id"], row["final_relevance_grade"])
        for row in final_rows
    )
    qrels_bytes = "".join("\t".join(row) + "\n" for row in qrel_rows).encode("utf-8")
    historical = parse_qrels(args.historical_invalid_qrels)
    final_by_pair = {(row[0], row[2]): row[3] for row in qrel_rows}
    if set(historical) != set(final_by_pair):
        raise ValueError("historical invalid and corrected qrels pair sets differ")
    final_by_pair_row = {(row["query_id"], row["chunk_id"]): row for row in final_rows}
    change_rows = []
    for pair in sorted(final_by_pair):
        if historical[pair] == final_by_pair[pair]:
            continue
        label = final_by_pair_row[pair]
        change_rows.append(
            {
                "chunk_id": pair[1],
                "corrected_grade": int(final_by_pair[pair]),
                "display_id": label["display_id"],
                "historical_invalid_grade": int(historical[pair]),
                "label_source": label["label_source"],
                "owner_rationale": label["adjudication_rationale"],
                "query_id": pair[0],
            }
        )

    regrade_copy = output_root / "human_regrade/regrade_package_seed42_COMPLETED.csv"
    adjudication_copy = output_root / "owner_adjudication/phase6_owner_adjudication_14_FINAL.csv"
    labels_path = output_root / "final_labels/phase6_final_labels.csv"
    provenance_path = output_root / "final_labels/provenance.jsonl"
    qrels_path = output_root / "qrels/phase6_final_pooled_qrels.tsv"
    write_bytes(regrade_copy, args.completed_regrade.read_bytes(), overwrite=args.overwrite)
    write_bytes(adjudication_copy, args.owner_adjudication.read_bytes(), overwrite=args.overwrite)
    write_bytes(labels_path, csv_bytes(final_rows, FINAL_LABEL_FIELDS), overwrite=args.overwrite)
    write_jsonl(provenance_path, provenance_rows, key="display_id", overwrite=args.overwrite)
    write_bytes(qrels_path, qrels_bytes, overwrite=args.overwrite)

    common = {
        "protocol": "docs/EXPERIMENT_PROTOCOL_V2.md",
        "validated_at_utc": args.validation_timestamp,
    }
    write_json(
        output_root / "human_regrade/validation.json",
        {
            **common,
            "copied_sha256": sha256_file(regrade_copy),
            "grade_distribution": distribution(
                [row["second_relevance_grade"] for row in regrade_rows]
            ),
            "original_sha256": sha256_file(args.completed_regrade),
            "original_source_path": str(args.completed_regrade),
            "protected_mismatch_n": 0,
            "row_n": 114,
            "status": "passed",
            "u_n": 0,
            "unique_display_id_n": 114,
            "unique_pair_n": 114,
        },
        overwrite=args.overwrite,
    )
    write_json(
        output_root / "human_regrade/agreement_report.json",
        {**common, **agreement_report},
        overwrite=args.overwrite,
    )
    write_json(
        output_root / "owner_adjudication/validation.json",
        {
            **common,
            "blank_grade_n": 0,
            "blank_rationale_n": 0,
            "copied_sha256": sha256_file(adjudication_copy),
            "disagreement_set_match": True,
            "final_grade_distribution": distribution(
                [row["final_grade"] for row in adjudication_rows]
            ),
            "invalid_grade_n": 0,
            "original_sha256": sha256_file(args.owner_adjudication),
            "original_source_path": str(args.owner_adjudication),
            "protected_mismatch_n": 0,
            "row_n": 14,
            "status": "passed",
            "unique_display_id_n": 14,
        },
        overwrite=args.overwrite,
    )
    integrity = {
        "ai_assigned_final_label_n": 0,
        "duplicate_display_id_n": 0,
        "duplicate_pair_n": 0,
        "final_grade_distribution": dict(sorted(grade_counts.items())),
        "label_source_counts": dict(sorted(source_counts.items())),
        "missing_grade_n": 0,
        "row_n": 755,
        "status": "passed",
        "u_n": 0,
    }
    write_json(output_root / "final_labels/integrity_audit.json", integrity, overwrite=args.overwrite)
    write_json(
        output_root / "final_labels/grade_distribution.json",
        dict(sorted(grade_counts.items())),
        overwrite=args.overwrite,
    )
    write_json(
        output_root / "qrels/change_report.json",
        {
            "changed_qrel_n": len(change_rows),
            "changes": change_rows,
            "comparison_only_no_performance_interpretation": True,
            "corrected_qrels_sha256": sha256_file(qrels_path),
            "historical_invalid_qrels_path": str(args.historical_invalid_qrels.relative_to(ROOT)),
            "historical_invalid_qrels_sha256": sha256_file(args.historical_invalid_qrels),
        },
        overwrite=args.overwrite,
    )
    write_json(
        output_root / "qrels/manifest.json",
        {
            "final_label_sha256": sha256_file(labels_path),
            "qrels_sha256": sha256_file(qrels_path),
            "row_n": 755,
            "source_label_path": str(labels_path.relative_to(ROOT)),
            "status": "frozen",
        },
        overwrite=args.overwrite,
    )

    input_paths = (
        args.first_pass,
        args.blank_sample,
        args.sealed_provenance,
        args.sample_manifest,
        args.completed_regrade,
        args.owner_adjudication,
        args.owner_authorization,
        args.historical_invalid_qrels,
    )
    generated_paths = tuple(
        path
        for path in output_root.rglob("*")
        if path.is_file() and path.name != "freeze_manifest.json"
    )
    manifest = {
        "code_hashes": {
            "scripts/finalize_phase6_seed42.py": sha256_file(
                ROOT / "scripts/finalize_phase6_seed42.py"
            ),
            "scripts/freeze_phase6_seed42_final.py": sha256_file(
                ROOT / "scripts/freeze_phase6_seed42_final.py"
            ),
        },
        "final_label_sha256": sha256_file(labels_path),
        "final_qrels_sha256": sha256_file(qrels_path),
        "historical_artifacts_modified": False,
        "inputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in input_paths if path.is_relative_to(ROOT)},
        "outputs": {
            str(path.relative_to(ROOT)): sha256_file(path) for path in sorted(generated_paths)
        },
        "phase": "phase6_seed42_final_human_owner_correction",
        "status": "frozen",
        "validation_timestamp_utc": args.validation_timestamp,
    }
    manifest["external_inputs"] = {
        str(path): sha256_file(path)
        for path in (args.completed_regrade, args.owner_adjudication)
        if not path.is_relative_to(ROOT)
    }
    write_json(output_root / "freeze_manifest.json", manifest, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "agreement": agreement_report,
                "changed_qrel_n": len(change_rows),
                "final_label_sha256": sha256_file(labels_path),
                "final_qrels_sha256": sha256_file(qrels_path),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
