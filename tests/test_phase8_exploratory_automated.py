"""Contracts for automated-only Phase 8 expansion audit."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audits/phase8_exploratory/automated_audit.json"


def _audit() -> dict:
    return json.loads(AUDIT.read_text(encoding="utf-8"))


def test_expansion_counts_and_integrity_are_frozen() -> None:
    audit = _audit()
    assert audit["release"]["documents"] == 130
    assert audit["release"]["chunks"] == 856
    assert audit["release"]["questions"] == 100
    assert audit["release"]["qrels"] == 140
    assert audit["hard_integrity_failures"] == 0
    assert audit["automated_integrity_result"] == "pass"


def test_audit_cannot_be_misrepresented_as_human_approved() -> None:
    audit = _audit()
    scope = audit["claim_scope"]
    assert audit["status"] == "exploratory_automated_only_pending_human_validation"
    assert scope["automated_expansion_verified"] is True
    assert scope["final_dissertation_evidence"] is False
    assert scope["owner_approved"] is False
    assert scope["human_benchmark_review_complete"] is False
    assert scope["api_calls_performed"] == 0


def test_known_benchmark_validity_failure_remains_visible() -> None:
    audit = _audit()
    validity = audit["benchmark_validity"]
    assert validity["upstream_audit_status"] == "pending_human_review"
    assert validity["automatic_failures"]["category_contract_passes"] == 32
    assert "diagnostic_only" in validity["pool_status"]


def test_only_three_expanded_retrieval_systems_are_claimed() -> None:
    assert set(_audit()["exploratory_three_system_metrics"]) == {"bm25", "faiss", "graphrag"}
