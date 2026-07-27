"""Offline tests for Phase 5D V2 remaining-primary cost amendment."""

from __future__ import annotations



import json
from pathlib import Path

import pytest

from scripts import run_phase5d_v2_full_prompt_rag_claude as runner
from src.retrievers.prompt_rag_claude_v2 import MODEL, ClaudeContractError
from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]


def test_budget_recalculation_fits_raised_cap_with_reserve() -> None:
    assert runner.PRIOR_CUMULATIVE_SPEND_USD == 1.040028
    assert runner.FULL_COUNTED_INPUT_TOKENS == 771_768
    assert runner.OBSERVED_CORRECTION_TOKENS == 52
    assert runner.FULL_CORRECTED_INPUT_TOKENS == 771_820
    assert runner.INPUT_UNCERTAINTY_RESERVE_TOKENS == 21_000
    assert runner.FULL_BUDGETED_INPUT_TOKENS == 792_820
    assert runner.FULL_MAXIMUM_OUTPUT_TOKENS == 26 * 2048 == 53_248
    assert runner.FULL_CORRECTED_WORST_CASE_USD == 1.038060
    assert runner.FULL_BUDGETED_WORST_CASE_USD == 1.059060
    assert runner.CUMULATIVE_BUDGETED_WORST_CASE_USD == 2.099088
    assert runner.CUMULATIVE_BUDGETED_WORST_CASE_USD < runner.CUMULATIVE_HARD_CAP_USD == 2.10


def test_amendment_preserves_base_model_prompt_schema_and_ranking() -> None:
    amendment = json.loads(runner.AMENDMENT_CONFIG_PATH.read_text())
    base_path = ROOT / amendment["base_config_path"]
    base = json.loads(base_path.read_text())
    assert sha256_file(base_path) == amendment["base_config_sha256"]
    assert amendment["amendment_scope"] == "cost cap and remaining-primary execution only"
    assert amendment["frozen_contract"]["model"] == base["model"] == MODEL
    assert amendment["frozen_contract"]["prompt_sha256"] == base["prompt"]["sha256"]
    assert amendment["frozen_contract"]["candidate_count"] == base["candidate_count"] == 50
    assert amendment["frozen_contract"]["scoring"] == "unchanged integer scale 0..3"
    assert amendment["frozen_contract"]["ranking"] == "score descending then chunk ID ascending"
    assert base["output_contract"]["tie_break"] == "ascending chunk_id; BM25 rank never used"


def test_full_plan_contains_only_26_non_trace_primaries() -> None:
    queries = [f"v2q-{index:03d}" for index in range(1, 35)]
    traces = ["v2q-017", "v2q-016", "v2q-003", "v2q-023", "v2q-013", "v2q-025", "v2q-004", "v2q-027"]
    plan = runner.build_full_plan(queries, traces)
    assert len(plan) == runner.FULL_REQUEST_N == 26
    assert all(logical_id == f"{query_id}:primary" for logical_id, query_id in plan)
    assert {query_id for _, query_id in plan}.isdisjoint(traces)
    assert [query_id for _, query_id in plan] == [query_id for query_id in queries if query_id not in traces]


def test_preflight_rebuilds_same_requests_and_verifies_trace() -> None:
    frozen = runner.preflight()
    assert len(frozen["requests"]) == 34
    assert len(frozen["full_plan"]) == 26
    assert frozen["config"]["model"] == MODEL
    assert frozen["full_config"]["budget"]["cumulative_hard_cap_usd"] == 2.1


def test_trace_artifacts_remain_hash_identical() -> None:
    protected = json.loads(
        (ROOT / "audits/phase5d_v2_full/trace_preservation.json").read_text()
    )
    for relative, expected in protected["protected_hashes"].items():
        assert sha256_file(ROOT / relative) == expected
    runner._verify_trace_checkpoint()


def test_initial_projection_includes_full_input_reserve_and_max_output() -> None:
    plan = [(f"v2q-{index:03d}:primary", f"v2q-{index:03d}") for index in range(1, 27)]
    ledger = runner._initial_ledger(plan)
    assert runner.projected_cumulative_cost(ledger, 26) == pytest.approx(2.099088)
    ledger["actual_input_tokens"] = 100_000
    ledger["actual_output_tokens"] = 1_000
    assert runner.projected_cumulative_cost(ledger, 25) <= 2.10


def test_approval_is_pending_and_commit_bound() -> None:
    approval = json.loads(runner.APPROVAL_PATH.read_text())
    assert approval["status"] == "pending_owner_approval"
    with pytest.raises(ClaudeContractError, match="lacks owner approval"):
        runner._validate_approval()
    statement = runner.expected_approval_statement("b" * 40)
    assert "remaining 26-primary full run" in statement
    assert "b" * 40 in statement
    assert "$2.10" in statement and "$2.099088" in statement


def test_request_cap_blocks_attempt_27(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(runner, "FULL_ROOT", tmp_path / "full")
    monkeypatch.setattr(runner, "_validate_approval", lambda: {})
    frozen = runner.preflight()
    ledger = runner._initial_ledger(frozen["full_plan"])
    ledger["attempted_generation_request_n"] = 26
    control = runner.FULL_ROOT / "control"
    control.mkdir(parents=True)
    (control / "ledger.json").write_text(json.dumps(ledger))
    client = type("Client", (), {"messages": object()})()
    with pytest.raises(ClaudeContractError, match="hard request cap reached"):
        runner.run_full(frozen, client_factory=lambda: client)


def test_runner_has_no_retry_fallback_or_trace_write_path() -> None:
    source = (ROOT / "scripts/run_phase5d_v2_full_prompt_rag_claude.py").read_text()
    assert "make_live_sender" in source
    assert "max_retries=" not in source
    assert "time.sleep" not in source
    assert "fallback" not in source.lower()
    assert "backfill" not in source.lower()
    assert "OUTPUT_ROOT / \"trace" in source
    assert "write_json(TRACE" not in source


def test_no_full_output_or_api_call_during_amendment() -> None:
    assert not runner.FULL_ROOT.exists()
    manifest = json.loads(runner.AMENDMENT_MANIFEST_PATH.read_text())
    assert manifest["live_api_calls_during_amendment"] == 0
    assert manifest["generation_calls_during_amendment"] == 0
