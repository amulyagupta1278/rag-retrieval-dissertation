"""Integrity tests for terminal Phase 7 trace V1 checkpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.generation.phase7_freeze import (
    MODEL,
    Phase7ExecutionFailure,
    validate_provider_response,
)
from src.utils.hashing import sha256_file


ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "runs/v2/phase7_generation_claude_top3/trace_v1"
AUDIT = ROOT / "audits/phase7_generation/trace_v1_failure_checkpoint.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_trace_checkpoint_hashes_and_terminal_counts() -> None:
    audit = load(AUDIT)
    paths = {
        "failure_record": TRACE / "sealed/failures/P7B002.json",
        "ledger": TRACE / "sealed/ledger.json",
        "raw_response_P7B001": TRACE / "blinded/raw_responses/P7B001.json",
        "raw_response_P7B002": TRACE / "blinded/raw_responses/P7B002.json",
        "trace_manifest": TRACE / "trace_manifest.json",
    }
    assert {name: sha256_file(path) for name, path in paths.items()} == audit["hashes"]
    ledger = load(paths["ledger"])
    assert ledger["status"] == "failed"
    assert ledger["attempted_request_n"] == 2
    assert len(ledger["completed_blinded_request_ids"]) == 1
    assert ledger["retry_n"] == 0
    assert ledger["full_panel_authorized"] is False
    assert audit["full_panel_executed"] is False


def test_first_response_valid_and_second_terminal_truncation() -> None:
    first = load(TRACE / "blinded/raw_responses/P7B001.json")
    second = load(TRACE / "blinded/raw_responses/P7B002.json")
    assert first["model"] == second["model"] == MODEL
    validated = validate_provider_response(
        first, available_evidence_ids={"E01", "E02", "E03"}
    )
    assert validated["response_id"] == first["id"]
    with pytest.raises(Phase7ExecutionFailure) as terminal:
        validate_provider_response(
            second, available_evidence_ids={"E01", "E02", "E03"}
        )
    assert terminal.value.failure_class == "truncation"


def test_trace_manifest_maps_every_preserved_execution_file() -> None:
    manifest = load(TRACE / "trace_manifest.json")
    actual = {
        str(path.relative_to(TRACE)): sha256_file(path)
        for path in TRACE.rglob("*")
        if path.is_file() and path.name != "trace_manifest.json"
    }
    assert manifest["artifacts"] == actual
    assert not (TRACE / "operational_summary.json").exists()
    assert not (TRACE / "blinded/validated_answers.jsonl").exists()
