#!/usr/bin/env python3
"""Freeze owner-adjudicated seed-42 Phase 6 labels and pooled qrels.

This mechanical step never assigns relevance. It validates owner inputs, reconstructs
the 100 regrade agreements from the owner's complete disagreement handoff, calculates
agreement, and writes deterministic additive artifacts. Historical Phase 6 files are
not modified.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import write_bytes, write_json  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402

GRADES = {"0", "1", "2"}
FIRST_PASS_FIELDS = (
    "display_id",
    "query_id",
    "question",
    "reference_answer",
    "chunk_id",
    "source_document_title",
    "candidate_chunk",
    "relevance_grade",
    "rationale",
)
PROTECTED_FIELDS = (
    "query_id",
    "question",
    "reference_answer",
    "source_document_title",
    "candidate_chunk",
)
ADJUDICATION_FIELDS = (
    "display_id",
    "query_id",
    "question",
    "reference_answer",
    "source_document_title",
    "candidate_chunk",
    "first_pass_grade",
    "second_pass_grade",
    "grade_transition",
    "final_grade",
    "owner_rationale",
)
FINAL_LABEL_FIELDS = (
    "display_id",
    "query_id",
    "chunk_id",
    "final_relevance_grade",
    "label_source",
    "adjudication_rationale",
)


def read_csv(path: Path, expected_fields: Iterable[str]) -> list[dict[str, str]]:
    """Read UTF-8 CSV and fail closed on schema or duplicate display IDs."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != tuple(expected_fields):
            raise ValueError(
                f"unexpected CSV schema in {path}: {reader.fieldnames}; "
                f"expected {list(expected_fields)}"
            )
        rows = list(reader)
    ids = [row["display_id"] for row in rows]
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate display_id in {path}")
    return rows


def csv_bytes(rows: list[dict[str, Any]], fields: Iterable[str]) -> bytes:
    """Serialize rows as deterministic RFC-style CSV with LF endings."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(fields),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def kappa(first: list[int], second: list[int], *, quadratic: bool) -> float:
    """Calculate unweighted or quadratic-weighted Cohen's kappa for grades 0..2."""
    if len(first) != len(second) or not first:
        raise ValueError("kappa requires two non-empty equal-length grade lists")
    n = len(first)
    first_counts = Counter(first)
    second_counts = Counter(second)

    def weight(left: int, right: int) -> float:
        if not quadratic:
            return float(left != right)
        return ((left - right) / 2.0) ** 2

    observed = sum(weight(left, right) for left, right in zip(first, second)) / n
    expected = sum(
        weight(left, right)
        * (first_counts[left] / n)
        * (second_counts[right] / n)
        for left in range(3)
        for right in range(3)
    )
    if math.isclose(expected, 0.0):
        return 1.0 if math.isclose(observed, 0.0) else 0.0
    return 1.0 - observed / expected


def validate_hash(path: Path, expected: str, label: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch: expected {expected}, got {actual}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first-pass", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--sealed-provenance", type=Path, required=True)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--owner-adjudication", type=Path, required=True)
    parser.add_argument("--owner-approval", type=Path, required=True)
    parser.add_argument("--labels-output", type=Path, required=True)
    parser.add_argument("--qrels-output", type=Path, required=True)
    parser.add_argument("--audit-dir", type=Path, required=True)
    parser.add_argument("--owner-input-copy", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    paths = {
        key: value.resolve()
        for key, value in vars(args).items()
        if isinstance(value, Path)
    }
    first_path = paths["first_pass"]
    sample_path = paths["sample"]
    provenance_path = paths["sealed_provenance"]
    sample_manifest_path = paths["sample_manifest"]
    owner_path = paths["owner_adjudication"]
    approval_path = paths["owner_approval"]
    labels_path = paths["labels_output"]
    qrels_path = paths["qrels_output"]
    audit_dir = paths["audit_dir"]
    copy_path = paths["owner_input_copy"]

    for path in (labels_path, qrels_path, copy_path):
        if path.exists() and not args.overwrite:
            raise FileExistsError(f"output exists; pass --overwrite explicitly: {path}")
    if audit_dir.exists() and any(audit_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(
            f"audit directory is non-empty; pass --overwrite explicitly: {audit_dir}"
        )

    sample_manifest = json.loads(sample_manifest_path.read_text(encoding="utf-8"))
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    validate_hash(first_path, sample_manifest["source_csv_sha256"], "first-pass input")
    validate_hash(sample_path, sample_manifest["regrade_package_sha256"], "seed-42 sample")
    validate_hash(
        provenance_path,
        sample_manifest["sealed_provenance_sha256"],
        "seed-42 sealed provenance",
    )
    validate_hash(
        owner_path,
        approval["final_adjudication_csv_sha256"],
        "owner adjudication",
    )
    contract = approval.get("reconstruction_contract", {})
    required_contract = {
        "adjudication_csv_contains_complete_seed42_disagreement_set",
        "listed_rows_use_second_pass_grade_for_agreement_calculation",
        "listed_rows_use_final_grade_for_final_labels",
        "sampled_rows_not_listed_in_adjudication_csv_are_owner_regrade_agreements",
    }
    if any(contract.get(field) is not True for field in required_contract):
        raise ValueError("owner approval lacks complete reconstruction contract")
    if sample_manifest.get("seed") != 42 or sample_manifest.get("stratified") is not False:
        raise ValueError("sample manifest is not frozen seed-42 blind random sample")

    first_rows = read_csv(first_path, FIRST_PASS_FIELDS)
    sample_rows = read_csv(
        sample_path,
        (
            "display_id",
            "query_id",
            "question",
            "reference_answer",
            "chunk_id",
            "source_document_title",
            "candidate_chunk",
            "second_relevance_grade",
            "second_rationale",
        ),
    )
    owner_rows = read_csv(owner_path, ADJUDICATION_FIELDS)
    if len(first_rows) != 755 or len(sample_rows) != 114 or len(owner_rows) != 14:
        raise ValueError(
            "unexpected input counts; required first-pass=755, seed42 sample=114, "
            "owner disagreements=14"
        )
    if any(row["relevance_grade"] not in GRADES for row in first_rows):
        raise ValueError("first-pass grades must be 0, 1, or 2")
    if any(row["second_relevance_grade"] or row["second_rationale"] for row in sample_rows):
        raise ValueError("frozen seed-42 sample must remain blank")

    first_by_id = {row["display_id"]: row for row in first_rows}
    sample_by_id = {row["display_id"]: row for row in sample_rows}
    provenance_by_id = {row["display_id"]: row for row in provenance["rows"]}
    if set(sample_by_id) != set(provenance_by_id):
        raise ValueError("seed-42 sample and sealed provenance IDs differ")
    if not set(sample_by_id).issubset(first_by_id):
        raise ValueError("seed-42 sample contains unknown first-pass display IDs")
    if not {row["display_id"] for row in owner_rows}.issubset(sample_by_id):
        raise ValueError("owner adjudication contains display ID outside seed-42 sample")

    for display_id, sample in sample_by_id.items():
        first = first_by_id[display_id]
        for field in (
            "query_id",
            "question",
            "reference_answer",
            "chunk_id",
            "source_document_title",
            "candidate_chunk",
        ):
            if sample[field] != first[field]:
                raise ValueError(f"sample protected field mismatch: {display_id} {field}")
        if provenance_by_id[display_id]["first_pass_grade"] != first["relevance_grade"]:
            raise ValueError(f"sealed first-pass grade mismatch: {display_id}")

    owner_by_id: dict[str, dict[str, str]] = {}
    for owner in owner_rows:
        display_id = owner["display_id"]
        sample = sample_by_id[display_id]
        first = first_by_id[display_id]
        for field in PROTECTED_FIELDS:
            if owner[field] != sample[field]:
                raise ValueError(f"owner protected field mismatch: {display_id} {field}")
        if owner["first_pass_grade"] != first["relevance_grade"]:
            raise ValueError(f"owner first-pass grade mismatch: {display_id}")
        if owner["second_pass_grade"] not in GRADES or owner["final_grade"] not in GRADES:
            raise ValueError(f"invalid owner grade: {display_id}")
        if owner["second_pass_grade"] == owner["first_pass_grade"]:
            raise ValueError(f"owner adjudication row is not a disagreement: {display_id}")
        expected_transition = f"{owner['first_pass_grade']} → {owner['second_pass_grade']}"
        if owner["grade_transition"] != expected_transition:
            raise ValueError(f"incorrect grade transition: {display_id}")
        if not owner["owner_rationale"].strip():
            raise ValueError(f"blank owner rationale: {display_id}")
        owner_by_id[display_id] = owner

    owner_final_counts = Counter(row["final_grade"] for row in owner_rows)
    if owner_final_counts != Counter({"1": 3, "2": 11}):
        raise ValueError(f"owner final grade counts differ: {dict(owner_final_counts)}")

    agreement_rows: list[dict[str, str]] = []
    first_grades: list[int] = []
    second_grades: list[int] = []
    for display_id in sorted(sample_by_id):
        first_grade = first_by_id[display_id]["relevance_grade"]
        owner = owner_by_id.get(display_id)
        second_grade = owner["second_pass_grade"] if owner else first_grade
        agreement_rows.append(
            {
                "display_id": display_id,
                "first_pass_grade": first_grade,
                "second_pass_grade": second_grade,
                "agreement": str(first_grade == second_grade).lower(),
                "reconstruction_source": (
                    "owner_adjudication_disagreement"
                    if owner
                    else "owner_attested_regrade_agreement"
                ),
            }
        )
        first_grades.append(int(first_grade))
        second_grades.append(int(second_grade))

    agreements = sum(left == right for left, right in zip(first_grades, second_grades))
    disagreements = len(first_grades) - agreements
    if disagreements != len(owner_rows):
        raise ValueError("reconstructed disagreement count does not equal owner adjudication rows")
    agreement_summary = {
        "agreement_n": agreements,
        "cohen_kappa_quadratic_weighted": kappa(first_grades, second_grades, quadratic=True),
        "cohen_kappa_unweighted": kappa(first_grades, second_grades, quadratic=False),
        "disagreement_n": disagreements,
        "exact_agreement": agreements / len(first_grades),
        "first_pass_distribution": dict(sorted(Counter(map(str, first_grades)).items())),
        "owner_adjudication_row_n": len(owner_rows),
        "sample_n": len(first_grades),
        "sampling_design": "seed42_blind_simple_random_without_replacement",
        "second_pass_distribution": dict(sorted(Counter(map(str, second_grades)).items())),
        "status": "human_owner_regrade_and_adjudication_complete",
    }

    final_rows: list[dict[str, str]] = []
    sampled_ids = set(sample_by_id)
    for first in sorted(first_rows, key=lambda row: row["display_id"]):
        display_id = first["display_id"]
        owner = owner_by_id.get(display_id)
        if owner:
            grade = owner["final_grade"]
            source = "owner_adjudication_seed42"
            rationale = owner["owner_rationale"]
        elif display_id in sampled_ids:
            grade = first["relevance_grade"]
            source = "owner_regrade_agreement_seed42"
            rationale = ""
        else:
            grade = first["relevance_grade"]
            source = "owner_first_pass_unsampled_seed42"
            rationale = first["rationale"]
        final_rows.append(
            {
                "display_id": display_id,
                "query_id": first["query_id"],
                "chunk_id": first["chunk_id"],
                "final_relevance_grade": grade,
                "label_source": source,
                "adjudication_rationale": rationale,
            }
        )

    final_grade_counts = Counter(row["final_relevance_grade"] for row in final_rows)
    label_source_counts = Counter(row["label_source"] for row in final_rows)
    if final_grade_counts != Counter({"0": 572, "1": 89, "2": 94}):
        raise ValueError(f"unexpected final grade distribution: {dict(final_grade_counts)}")
    if label_source_counts != Counter(
        {
            "owner_first_pass_unsampled_seed42": 641,
            "owner_regrade_agreement_seed42": 100,
            "owner_adjudication_seed42": 14,
        }
    ):
        raise ValueError(f"unexpected label source counts: {dict(label_source_counts)}")

    qrel_rows = sorted(
        (
            row["query_id"],
            "0",
            row["chunk_id"],
            row["final_relevance_grade"],
        )
        for row in final_rows
    )
    if len({(query_id, chunk_id) for query_id, _, chunk_id, _ in qrel_rows}) != 755:
        raise ValueError("duplicate query/chunk pair in final qrels")
    qrels_bytes = "".join("\t".join(row) + "\n" for row in qrel_rows).encode("utf-8")

    write_bytes(copy_path, owner_path.read_bytes(), overwrite=args.overwrite)
    write_bytes(labels_path, csv_bytes(final_rows, FINAL_LABEL_FIELDS), overwrite=args.overwrite)
    write_bytes(qrels_path, qrels_bytes, overwrite=args.overwrite)
    write_bytes(
        audit_dir / "regrade_agreement_rows.csv",
        csv_bytes(
            agreement_rows,
            (
                "display_id",
                "first_pass_grade",
                "second_pass_grade",
                "agreement",
                "reconstruction_source",
            ),
        ),
        overwrite=args.overwrite,
    )
    write_json(audit_dir / "agreement_summary.json", agreement_summary, overwrite=args.overwrite)
    integrity = {
        "checks": {
            "all_owner_rows_are_seed42_sample_members": True,
            "all_owner_rows_are_disagreements": True,
            "blank_owner_grades": 0,
            "blank_owner_rationales": 0,
            "duplicate_final_pairs": 0,
            "owner_protected_field_mismatches": 0,
            "owner_reported_grade_counts_match": True,
            "seed42_sample_and_provenance_ids_match": True,
        },
        "final_grade_counts": dict(sorted(final_grade_counts.items())),
        "label_source_counts": dict(sorted(label_source_counts.items())),
        "status": "passed",
    }
    write_json(audit_dir / "integrity_audit.json", integrity, overwrite=args.overwrite)

    input_paths = (
        first_path,
        sample_path,
        provenance_path,
        sample_manifest_path,
        owner_path,
        approval_path,
    )
    output_paths = (
        copy_path,
        labels_path,
        qrels_path,
        audit_dir / "regrade_agreement_rows.csv",
        audit_dir / "agreement_summary.json",
        audit_dir / "integrity_audit.json",
    )
    manifest = {
        "code_hashes": {
            "scripts/finalize_phase6_seed42.py": sha256_file(
                ROOT / "scripts/finalize_phase6_seed42.py"
            )
        },
        "historical_seed123_artifacts_modified": False,
        "inputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in input_paths},
        "outputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in output_paths},
        "phase": "phase6_seed42_owner_adjudicated_freeze",
        "qrels_exhaustive_within_pool": True,
        "qrels_scope": "755-pair union top-10 pool from five frozen retrieval systems",
        "status": "frozen",
    }
    write_json(audit_dir / "freeze_manifest.json", manifest, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "agreement": agreement_summary,
                "final_grade_counts": dict(sorted(final_grade_counts.items())),
                "labels_sha256": sha256_file(labels_path),
                "qrels_sha256": sha256_file(qrels_path),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
