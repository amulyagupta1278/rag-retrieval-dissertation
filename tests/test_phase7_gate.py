"""Synthetic-only tests for Phase 7 dependency gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.generation.phase7_gate import Phase7GateError, assert_phase7_ready


def _write(root: Path, name: str, text: str) -> dict[str, str]:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"path": name, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def _ready_manifest(tmp_path: Path) -> Path:
    qrels = _write(tmp_path, "qrels.jsonl", "synthetic-qrels\n")
    metrics = _write(tmp_path, "metrics.json", "{}\n")
    freeze_text = json.dumps({"final_qrels_sha256": qrels["sha256"]}, sort_keys=True)
    freeze = _write(tmp_path, "freeze.json", freeze_text)
    rankings = {
        name: _write(tmp_path, f"{name}.jsonl", f"{name}\n")
        for name in (
            "bm25",
            "faiss_windowed_max",
            "graph_v3_2",
            "hybrid_rrf",
            "prompt_rag_claude",
        )
    }
    manifest = {
        "status": "ready_for_phase7_execution",
        "phase6": {
            "first_pass_structural_validation": True,
            "human_regrade_complete": True,
            "human_regrade_row_n": 114,
            "agreement_report_exists": True,
            "unresolved_disagreement_n": 0,
            "unresolved_u_n": 0,
        },
        "final_qrels": qrels,
        "phase6_retrieval_metrics": metrics,
        "phase7_freeze_manifest": freeze,
        "rankings": rankings,
    }
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_gate_accepts_complete_synthetic_dependencies(tmp_path: Path) -> None:
    result = assert_phase7_ready(_ready_manifest(tmp_path), tmp_path)
    assert result["ready"] is True
    assert result["verified_ranking_n"] == 5


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("human_regrade_complete", False),
        ("agreement_report_exists", False),
        ("unresolved_disagreement_n", 1),
        ("unresolved_u_n", 1),
    ],
)
def test_gate_fails_closed_on_phase6_gaps(tmp_path: Path, field: str, value: object) -> None:
    path = _ready_manifest(tmp_path)
    manifest = json.loads(path.read_text())
    manifest["phase6"][field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(Phase7GateError):
        assert_phase7_ready(path, tmp_path)


def test_gate_fails_without_final_qrels(tmp_path: Path) -> None:
    path = _ready_manifest(tmp_path)
    (tmp_path / "qrels.jsonl").unlink()
    with pytest.raises(Phase7GateError, match="missing artifact"):
        assert_phase7_ready(path, tmp_path)

