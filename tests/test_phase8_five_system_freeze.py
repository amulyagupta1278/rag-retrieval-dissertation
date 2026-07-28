"""Contracts for Phase 8 Hybrid and Prompt-RAG offline freeze."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_hybrid_uses_pilot_frozen_configuration() -> None:
    summary = json.loads(
        (ROOT / "runs/phase8_exploratory_five_system/hybrid_rrf/operational_summary.json").read_text()
    )
    assert summary["questions"] == 100
    assert summary["rrf_k"] == 60
    assert summary["input_depth"] == 50
    assert summary["configuration_selected_on_phase8"] is False
    assert summary["human_qrels"] is False


def test_prompt_rag_freeze_is_unexecuted_and_capped() -> None:
    audit = json.loads(
        (ROOT / "audits/phase8_exploratory/prompt_rag_trace_freeze.json").read_text()
    )
    assert audit["status"] == "offline_frozen_pending_owner_trace_approval"
    assert audit["request_n"] == 100
    assert audit["candidate_n"] == 50
    assert audit["trace_n"] == 5
    assert audit["execution_authorized"] is False
    assert audit["live_api_calls"] == 0
    assert audit["trace_worst_case_including_reserve_usd"] <= audit["trace_hard_cap_usd"]
    assert audit["full_worst_case_usd"] + audit["ambiguous_dispatch_reserve_usd"] <= audit["full_hard_cap_usd"]
    plan = ROOT / "runs/phase8_exploratory_five_system/prompt_rag_freeze/request_plan.jsonl"
    assert hashlib.sha256(plan.read_bytes()).hexdigest() == audit["request_plan_sha256"]
    assert len(plan.read_text().splitlines()) == 100
