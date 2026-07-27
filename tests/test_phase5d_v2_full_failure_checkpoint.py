"""Offline checks for terminal Phase 5D V2 full-run transport failure."""

from __future__ import annotations



import json
from pathlib import Path

import pytest

from scripts import run_phase5d_v2_full_prompt_rag_claude as runner
from src.retrievers.prompt_rag_claude_v2 import ClaudeContractError
from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]
CHECKPOINT = ROOT / "audits/phase5d_v2_full/full_transport_failure_checkpoint.json"
DIAGNOSIS = ROOT / "audits/phase5d_v2_full/offline_transport_diagnosis.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_terminal_ledger_records_one_attempt_zero_valid_and_ambiguous_billing() -> None:
    ledger = load(runner.FULL_ROOT / "control/ledger.json")
    assert ledger["status"] == "failed"
    assert ledger["attempted_generation_request_n"] == 1
    assert ledger["completed_logical_request_ids"] == []
    assert ledger["actual_input_tokens"] == ledger["actual_output_tokens"] == 0
    assert ledger["full_observed_cost_usd"] == 0.0
    assert ledger["cumulative_observed_cost_usd"] == 1.040028
    assert ledger["billing_ambiguous"] is True


def test_failure_is_sanitized_connection_class_without_http_status() -> None:
    failure = load(runner.FULL_ROOT / "failures/v2q-001__primary.json")
    assert failure == {
        "error_class": "ClaudeProviderError",
        "http_status": None,
        "logical_request_id": "v2q-001:primary",
        "provider_error_body_preserved": False,
        "request_sha256": "20297141054a74417f8a9c9f84f1415c9e62a0d1cebedb96c5eaad0f4cf94d43",
        "schema_version": 1,
    }


def test_checkpoint_requires_separate_recovery_and_no_resume() -> None:
    checkpoint = load(CHECKPOINT)
    assert checkpoint["status"] == "full_run_terminal_transport_failure_preserved"
    assert checkpoint["recovery_boundary"]["current_run_may_resume"] is False
    assert checkpoint["recovery_boundary"]["new_live_call_authorized"] is False
    assert checkpoint["execution"]["automatic_retry_n"] == 0
    assert checkpoint["integrity"]["trace_evidence_changed"] is False


def test_offline_diagnosis_does_not_overclaim_exact_root_cause() -> None:
    diagnosis = load(DIAGNOSIS)
    assert diagnosis["diagnosis"]["exact_root_cause"] == "unverified"
    assert diagnosis["network_activity_during_diagnosis"] == 0
    assert diagnosis["local_environment"]["credential_value_recorded"] is False
    assert diagnosis["runner_mapping"]["APIConnectionError"].endswith("null status")


def test_terminal_run_refuses_resume_before_client_creation() -> None:
    frozen = runner.preflight()
    called = False

    def client_factory():
        nonlocal called
        called = True
        raise AssertionError("client must not be created for terminal ledger")

    with pytest.raises(ClaudeContractError, match="ledger is terminal: failed"):
        runner.run_full(frozen, client_factory=client_factory)
    assert called is False


def test_trace_manifest_and_failure_evidence_hashes_are_stable() -> None:
    expected = {
        "runs/v2/phase5d_prompt_rag_claude_v2/trace/artifact_manifest.json": "0910c957081b4bb54b1e7ba08f20b29e1a8b3608ecfe9b8d06bac5a6f7693158",
        "runs/v2/phase5d_prompt_rag_claude_v2/full/control/ledger.json": "01d2a453bd57252ea23551cc6a9b4a625a6d0827dcb0018d89de03ae08b8b3d7",
        "runs/v2/phase5d_prompt_rag_claude_v2/full/failures/v2q-001__primary.json": "f75e9fd02fd603efc809570027707dc3a458502399eec545dd7c4305595b9e26",
    }
    for relative, digest in expected.items():
        assert sha256_file(ROOT / relative) == digest
