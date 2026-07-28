"""Tests for Phase 8 draft-only planning artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates/phase8"


def _load(name: str) -> dict[str, object]:
    return json.loads((TEMPLATES / name).read_text(encoding="utf-8"))


def test_acquisition_template_is_blank_and_has_required_fields() -> None:
    rows = list(csv.DictReader((TEMPLATES / "official_source_acquisition_log.csv").open()))
    assert rows == []
    headers = (TEMPLATES / "official_source_acquisition_log.csv").read_text().splitlines()[0].split(",")
    assert set(headers) == {
        "url", "publisher", "document_title", "retrieval_date", "file_sha256",
        "scheme", "version_or_date", "inclusion_rationale", "exclusion_rationale", "status",
    }


def test_holdout_template_has_no_authored_question_or_final_label() -> None:
    record = _load("holdout_question_record.json")
    required = {
        "question_id", "category", "scheme", "question", "reference_answer",
        "supporting_chunks", "multi_hop", "synthesis", "lexical_confound_notes", "reviewer_status",
    }
    assert set(record) == required
    assert record["question"] is None
    assert record["reference_answer"] is None
    assert record["reviewer_status"] == "draft_not_reviewed"


def test_review_and_verdict_templates_remain_unresolved() -> None:
    review = _load("benchmark_review_checklist.json")
    assert review["review_status"] == "not_started"
    assert all(value is None for key, value in review.items() if key != "review_status")
    verdict = _load("final_hypothesis_verdict_record.json")
    assert verdict["verdict"] is None
    assert verdict["effect"] is None


def test_release_template_is_not_ready() -> None:
    checklist = _load("dissertation_release_checklist.json")
    assert checklist["release_status"] == "not_ready"
    assert not any(value is True for value in checklist.values())


def test_phase8_audits_make_no_selection_or_execution_claim() -> None:
    decisions = json.loads((ROOT / "audits/phase8/owner_decisions_required.json").read_text())
    coverage = json.loads((ROOT / "audits/phase8/current_coverage_audit.json").read_text())
    assert decisions["final_scale_strategy"] is None
    assert coverage["system_execution_performed"] is False
    assert coverage["question_n"] == 34
    assert sum(coverage["category_counts"].values()) == 34

