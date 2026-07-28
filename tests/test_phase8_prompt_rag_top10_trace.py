"""Completed cost-adapted Prompt-RAG trace contracts."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRACE = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_top10_trace"


def test_top10_trace_complete_and_under_cap() -> None:
    summary = json.loads((TRACE / "trace_summary.json").read_text())
    assert summary["status"] == "trace_complete"
    assert summary["request_n"] == summary["valid_n"] == 5
    assert summary["retry_n"] == 0
    assert summary["observed_cost_usd"] == 0.049936
    assert summary["observed_cost_usd"] < summary["hard_cap_usd"] == 0.15


def test_top10_trace_hashes_verify() -> None:
    summary = json.loads((TRACE / "trace_summary.json").read_text())
    for relative, expected in summary["artifacts"].items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_stop_gate_preserved() -> None:
    checkpoint = json.loads(
        (ROOT / "audits/phase8_exploratory/cost_safe_prompt_rag_trace_success.json").read_text()
    )
    assert checkpoint["full_run_authorized"] is False
    assert checkpoint["generation_authorized"] is False
    assert checkpoint["projected_100_request_observed_rate_cost_usd"] < 1.0
