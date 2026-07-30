"""Validate completed Phase 8 Prompt-RAG trace and stop gate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_trace"


def test_trace_completed_under_cap_without_retries() -> None:
    summary = json.loads((TRACE / "trace_summary.json").read_text())
    assert summary["status"] == "trace_complete"
    assert summary["request_n"] == summary["valid_n"] == 5
    assert summary["retry_n"] == 0
    assert summary["observed_cost_usd"] == 0.224985
    assert summary["observed_cost_usd"] < summary["hard_cap_usd"] == 0.62
    assert summary["input_tokens"] == 211380
    assert summary["output_tokens"] == 2721


def test_trace_artifact_hashes_verify() -> None:
    summary = json.loads((TRACE / "trace_summary.json").read_text())
    for relative, expected in summary["artifacts"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_checkpoint_stops_before_unaffordable_full_run() -> None:
    checkpoint = json.loads(
        (ROOT / "audits/phase8_exploratory/prompt_rag_trace_success_checkpoint.json").read_text()
    )
    assert checkpoint["full_run_authorized"] is False
    assert checkpoint["generation_authorized"] is False
    assert checkpoint["projected_remaining_95_observed_rate_cost_usd"] < checkpoint["estimated_balance_after_trace_usd"]
    assert checkpoint["estimated_headroom_after_same_design_full_run_usd"] < 1.0
