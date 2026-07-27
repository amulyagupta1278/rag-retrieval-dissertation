"""Offline tests for Phase 5D V3 transport-recovery freeze."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import run_phase5d_v3_transport_recovery as runner
from src.retrievers.prompt_rag_claude_v2 import MODEL, ClaudeContractError
from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]


def test_ambiguous_billing_reserve_and_cap_math() -> None:
    assert runner.RECORDED_PRIOR_SPEND_USD == 1.040028
    assert runner.AMBIGUOUS_INPUT_RESERVE_TOKENS == 40_000
    assert runner.AMBIGUOUS_MAX_OUTPUT_TOKENS == 2_048
    assert runner.AMBIGUOUS_RESERVE_USD == 0.050240
    assert runner.RESERVED_PRIOR_EXPOSURE_USD == 1.090268
    assert runner.RECOVERY_INPUT_BUDGET_TOKENS == 792_820
    assert runner.RECOVERY_MAX_OUTPUT_TOKENS == 53_248
    assert runner.RECOVERY_BUDGETED_WORST_CASE_USD == 1.059060
    assert runner.CUMULATIVE_BUDGETED_WORST_CASE_USD == 2.149328
    assert runner.CUMULATIVE_BUDGETED_WORST_CASE_USD < runner.CUMULATIVE_HARD_CAP_USD == 2.15


def test_config_preserves_retrieval_contract_and_uses_separate_output() -> None:
    config = json.loads(runner.CONFIG_PATH.read_text())
    contract = config["frozen_contract"]
    base = json.loads((ROOT / contract["base_v2_config_path"]).read_text())
    assert sha256_file(ROOT / contract["base_v2_config_path"]) == contract["base_v2_config_sha256"]
    assert contract["model"] == base["model"] == MODEL
    assert contract["prompt_sha256"] == base["prompt"]["sha256"]
    assert contract["candidate_count"] == base["candidate_count"] == 50
    assert config["execution"]["output_root"] == "runs/v2/phase5d_prompt_rag_claude_v3_recovery/full"
    assert config["execution"]["v2_failed_output_reuse"] is False


def test_preflight_rebuilds_unchanged_26_primary_payloads() -> None:
    frozen = runner.preflight()
    assert len(frozen["requests"]) == 34
    assert len(frozen["full_plan"]) == runner.REQUEST_N == 26
    assert all(logical_id == f"{query_id}:primary" for logical_id, query_id in frozen["full_plan"])
    assert set(query_id for _, query_id in frozen["full_plan"]).isdisjoint(frozen["trace_ids"])


def test_failed_v2_and_trace_evidence_hashes_remain_frozen() -> None:
    evidence = json.loads(
        (ROOT / "audits/phase5d_v3_recovery/evidence_preservation.json").read_text()
    )
    for relative, expected in evidence["protected_hashes"].items():
        assert sha256_file(ROOT / relative) == expected
    runner._verify_failed_v2()


def test_v2_has_no_valid_full_output_for_selection() -> None:
    raw = runner.V2_FULL_ROOT / "raw"
    assert not raw.exists() or not list(raw.glob("*.json"))
    ledger = json.loads((runner.V2_FULL_ROOT / "control/ledger.json").read_text())
    assert ledger["completed_logical_request_ids"] == []


def test_initial_projection_includes_ambiguous_reserve_and_recovery_maximum() -> None:
    frozen = runner.preflight()
    ledger = runner._initial_ledger(frozen["full_plan"])
    assert runner.projected_budgeted_exposure(ledger, 26) == pytest.approx(2.149328)
    assert ledger["cumulative_recorded_observed_cost_usd"] == 1.040028
    assert ledger["cumulative_budgeted_exposure_usd"] == 1.090268


def test_live_approval_is_pending_and_commit_bound() -> None:
    approval = json.loads(runner.APPROVAL_PATH.read_text())
    assert approval["status"] == "pending_owner_live_approval"
    with pytest.raises(ClaudeContractError, match="lacks owner live approval"):
        runner._validate_approval()
    statement = runner.expected_approval_statement("c" * 40)
    assert "V3 26-primary transport recovery" in statement
    assert "$2.15" in statement and "$0.050240" in statement


def test_request_cap_refuses_attempt_27(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frozen = runner.preflight()
    output = tmp_path / "v3"
    monkeypatch.setattr(runner, "OUTPUT_ROOT", output)
    monkeypatch.setattr(runner, "_validate_approval", lambda: {})
    ledger = runner._initial_ledger(frozen["full_plan"])
    ledger["attempted_generation_request_n"] = 26
    control = output / "control"
    control.mkdir(parents=True)
    (control / "ledger.json").write_text(json.dumps(ledger))
    client = type("Client", (), {"messages": object()})()
    with pytest.raises(ClaudeContractError, match="hard request cap reached"):
        runner.run_recovery(frozen, client_factory=lambda: client)


def test_runner_contains_no_retry_backfill_or_v2_raw_read() -> None:
    source = (ROOT / "scripts/run_phase5d_v3_transport_recovery.py").read_text()
    assert "max_retries=" not in source
    assert "time.sleep" not in source
    assert "backfill" not in source.lower()
    assert "V2_FULL_ROOT / \"raw\"" in source
    assert "read_text" not in source.split('raw_dir = V2_FULL_ROOT / "raw"', 1)[1].split("def preflight", 1)[0]


def test_no_v3_output_or_live_call_during_freeze() -> None:
    assert not runner.OUTPUT_ROOT.exists()
    manifest = json.loads(runner.MANIFEST_PATH.read_text())
    assert manifest["live_api_calls_during_freeze"] == 0
    assert manifest["generation_calls_during_freeze"] == 0
