"""Freeze contracts for Phase 8 automated exploratory R3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "audits/phase8_exploratory/automated_r3_freeze.json"


def test_r3_is_contract_clean_but_not_human_approved() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert freeze["questions"] == 100
    assert freeze["qrels"] == 140
    assert freeze["questions_repaired"] == 32
    assert all(value == 0 for value in freeze["automatic_failures"].values())
    assert freeze["status"] == "exploratory_automated_only_pending_human_validation"
    assert freeze["human_review_complete"] is False
    assert freeze["owner_approved"] is False
    assert freeze["final_dissertation_evidence"] is False
    assert freeze["api_calls"] == 0


def test_r3_manifest_verifies_every_frozen_file() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    manifest = ROOT / freeze["manifest"]["path"]
    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == freeze["manifest"]["sha256"]
    records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert len(records) == freeze["manifest"]["files"]
    for record in records:
        path = ROOT / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_r3_claims_only_available_systems() -> None:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert freeze["systems"] == ["bm25", "faiss", "graphrag"]
    assert set(freeze["aggregate_metrics"]) == set(freeze["systems"])
