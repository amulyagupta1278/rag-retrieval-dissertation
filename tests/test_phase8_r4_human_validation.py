"""Contracts for frozen Phase 8 R4 owner validation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "runs/phase8_r4_human_validated"
AUDIT = ROOT / "audits/phase8_r4_human_validated"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_owner_qrels_preserve_intentional_zero() -> None:
    qrels = rows(BASE / "qrels/owner_qrels_140.jsonl")
    assert len(qrels) == 140
    assert len({(row["query_id"], row["chunk_id"]) for row in qrels}) == 140
    assert Counter(row["grade"] for row in qrels) == {2: 139, 0: 1}
    assert {row["owner_mapping_decision"] for row in qrels} == {"valid"}


def test_owner_generation_labels_replace_ai_for_final_r4() -> None:
    labels = rows(BASE / "generation_evaluation/human_quality_labels_100.jsonl")
    assert len(labels) == 100
    assert all(row["human_label"] is True for row in labels)
    assert {row["label_source"] for row in labels} == {"human_owner_phase8_r4"}
    h5 = json.loads((BASE / "generation_evaluation/h5_results.json").read_text())
    assert h5["label_sources"] == {"human_owner_phase8_r4": 100}
    assert h5["decision"] == "exploratory_descriptive_only"


def test_synthesis_remains_separate_after_owner_review() -> None:
    summary = json.loads((BASE / "synthesis_review/summary.json").read_text())
    assert summary["dispositions"] == {"accept": 12, "reject": 4, "revise": 4}
    assert summary["primary_metrics_included"] == 0
    assert len(summary["revision_required_ids"]) == 8


def test_owner_validated_status_and_manifest_are_consistent() -> None:
    status = json.loads((AUDIT / "canonical_status.json").read_text())
    assert status["status"] == "owner_validated_r4_complete"
    assert status["human_validation_complete"] is True
    assert status["owner_reviewed_mapping_rows"] == 140
    assert status["owner_reviewed_generation_rows"] == 100
    assert status["owner_reviewed_synthesis_rows"] == 20
    assert status["synthesis_primary_metrics_included"] is False
    manifest = json.loads((AUDIT / "manifest.json").read_text())
    assert manifest["protected_automated_artifacts_modified"] == 0
    for relative, expected in manifest["artifacts"].items():
        assert sha(ROOT / relative) == expected


def test_automated_r4_freeze_remains_preserved() -> None:
    historical = json.loads((ROOT / "audits/phase8_r4/canonical_status.json").read_text())
    assert historical["status"] == "automated_r4_complete_pending_human_validation"
    assert historical["human_validation_complete"] is False
    assert historical["ai_assigned_generation_labels"] == 100
