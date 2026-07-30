#!/usr/bin/env python3
"""Validate and freeze Phase 7 human-owner audit without inventing missing labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "runs/v2/phase7_generation_claude_top3_v2/evaluation_v1"
AUDIT = ROOT / "audits/phase7_generation/v2/evaluation_v1"
DIMS = (
    "correctness",
    "faithfulness",
    "completeness",
    "citation_accuracy",
    "unsupported_claim_severity",
    "abstention_quality",
)
PROTECTED = (
    "blinded_request_id",
    "question",
    "reference_answer",
    "evidence",
    "generated_answer",
    "abstained",
    "abstention_reason",
    "cited_evidence_ids",
)


def canonical(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("completed_json", type=Path)
    args = parser.parse_args()

    source = args.completed_json.resolve()
    package_path = EVAL / "owner_audit_package.json"
    package = load(package_path)
    completed = load(source)
    if completed.get("schema_version") != 1:
        raise SystemExit("completed schema_version must equal 1")
    expected = package["rows"]
    rows = completed.get("rows")
    if not isinstance(rows, list) or len(rows) != 26:
        raise SystemExit("completed audit must contain exactly 26 rows")
    if len({row.get("blinded_request_id") for row in rows}) != 26:
        raise SystemExit("completed audit IDs must be unique")
    if [row.get("blinded_request_id") for row in rows] != [row["blinded_request_id"] for row in expected]:
        raise SystemExit("completed audit IDs/order differ from frozen package")

    for index, (actual, frozen) in enumerate(zip(rows, expected, strict=True)):
        for field in PROTECTED:
            if actual.get(field) != frozen.get(field):
                raise SystemExit(f"protected mismatch row {index + 1}: {field}")
        for dim in DIMS:
            value = actual.get(dim)
            if type(value) is not int or value not in (0, 1, 2):
                raise SystemExit(f"invalid {dim} row {index + 1}: {value!r}")
        if not isinstance(actual.get("owner_notes"), str):
            raise SystemExit(f"owner_notes must be string row {index + 1}")

    EVAL.mkdir(parents=True, exist_ok=True)
    AUDIT.mkdir(parents=True, exist_ok=True)
    frozen_path = EVAL / "phase7_owner_audit_26_COMPLETED.json"
    shutil.copyfile(source, frozen_path)

    distributions = {dim: dict(sorted(Counter(row[dim] for row in rows).items())) for dim in DIMS}
    means = {dim: sum(row[dim] for row in rows) / len(rows) for dim in DIMS}
    by_abstention: dict[str, dict] = {}
    grouped = defaultdict(list)
    for row in rows:
        grouped["abstained" if row["abstained"] else "answered"].append(row)
    for group, group_rows in grouped.items():
        by_abstention[group] = {
            "n": len(group_rows),
            "dimension_means": {
                dim: sum(row[dim] for row in group_rows) / len(group_rows) for dim in DIMS
            },
        }

    summary = {
        "schema_version": 1,
        "status": "owner_sample_audit_complete",
        "owner_labeled_n": 26,
        "score_n": 156,
        "blank_or_invalid_score_n": 0,
        "rubric": {
            "quality_dimensions": "2=good, 1=partial, 0=poor",
            "unsupported_claim_severity": "0=none, 1=minor, 2=central/major",
        },
        "abstained_n": sum(bool(row["abstained"]) for row in rows),
        "answered_n": sum(not bool(row["abstained"]) for row in rows),
        "dimension_distributions": distributions,
        "dimension_means": means,
        "by_generation_behavior": by_abstention,
        "interpretation_boundary": (
            "Descriptive results apply only to frozen 26-record owner-audit sample; "
            "they are not finalized labels for all 170 generated answers."
        ),
    }
    summary_path = EVAL / "owner_audit_summary.json"
    summary_path.write_bytes(canonical(summary))

    gate = {
        "schema_version": 1,
        "phase7_generation_complete": True,
        "mechanical_evaluation_complete": True,
        "owner_audit_sample_complete": True,
        "owner_audit_n": 26,
        "full_panel_quality_label_n": 26,
        "full_panel_generation_n": 170,
        "unlabeled_generation_n": 144,
        "all_34_queries_finalized": False,
        "h5_executed": False,
        "h5_gate": "BLOCKED_PENDING_FINALIZED_FULL_PANEL_QUALITY_LABELS",
        "reason": (
            "Frozen H5 protocol requires finalized quality labels and query-level analysis "
            "covering all 34 questions. Owner audit labels only frozen 26-record sample."
        ),
        "forbidden_shortcut": "Do not extrapolate 26 owner labels or invent labels for remaining 144 answers.",
    }
    gate_path = AUDIT / "h5_gate_after_owner_audit.json"
    gate_path.write_bytes(canonical(gate))

    artifacts = (frozen_path, summary_path, gate_path)
    manifest = {
        "schema_version": 1,
        "status": "frozen_owner_sample_complete_h5_blocked",
        "source_sha256": sha(source),
        "frozen_package_sha256": sha(package_path),
        "protected_mismatch_n": 0,
        "api_calls_n": 0,
        "ai_assigned_quality_labels_n": 0,
        "artifacts": {str(path.relative_to(ROOT)): sha(path) for path in artifacts},
    }
    (AUDIT / "owner_audit_freeze_manifest.json").write_bytes(canonical(manifest))
    print(json.dumps({"summary": summary, "gate": gate, "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
