"""Cost and scope contracts for Phase 8 cost-safe amendment."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_cost_safe_amendment_preserves_five_system_panels() -> None:
    audit = json.loads((ROOT / "audits/phase8_exploratory/cost_safe_amendment.json").read_text())
    assert audit["prompt_rag"]["candidate_depth"] == 10
    assert audit["prompt_rag"]["query_n"] == 100
    assert audit["generation"]["query_n"] == 20
    assert audit["generation"]["system_n"] == 5
    assert audit["generation"]["request_n"] == 100
    assert audit["within_owner_reported_balance"] is True
    assert audit["generation"]["execution_authorized"] is False


def test_cost_caps_cover_worst_cases_and_prior_trace() -> None:
    audit = json.loads((ROOT / "audits/phase8_exploratory/cost_safe_amendment.json").read_text())
    rerank = audit["prompt_rag"]
    generation = audit["generation"]
    assert rerank["trace_worst_case_including_reserve_usd"] <= rerank["trace_hard_cap_usd"]
    assert rerank["full_worst_case_usd"] + rerank["ambiguous_dispatch_reserve_usd"] <= rerank["full_hard_cap_usd"]
    assert generation["worst_case_usd"] + generation["ambiguous_dispatch_reserve_usd"] <= generation["hard_cap_usd"]
    assert audit["combined_with_prior_trace_usd"] <= audit["owner_reported_initial_balance_usd"]
