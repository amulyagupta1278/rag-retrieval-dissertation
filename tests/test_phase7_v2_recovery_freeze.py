"""Offline integrity tests for Phase 7 V2 512-token recovery freeze."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.generation.phase7_freeze import Phase7ExecutionFailure
from src.generation.phase7_v2_freeze import (
    HARD_COST_CAP_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    V1_MAX_OUTPUT_TOKENS,
    V1_SPENT_USD,
    Phase7V2ContractError,
    assert_v2_output_path,
    dispatch_once_after_cap_gate,
    projected_cumulative_exposure_usd,
    validate_provider_response,
    validate_trace_reuse,
)
from src.utils.hashing import sha256_file


ROOT = Path(__file__).resolve().parents[1]
V1 = ROOT / "runs/v2/phase7_generation_claude_top3"
V2 = ROOT / "runs/v2/phase7_generation_claude_top3_v2"
AUDIT = ROOT / "audits/phase7_generation/v2"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def valid_response(*, stop_reason: str = "end_turn", output_tokens: int = 20) -> dict:
    payload = {
        "abstained": False,
        "abstention_reason": "",
        "answer": "Supported fact [E01].",
        "cited_evidence_ids": ["E01"],
    }
    return {
        "content": [{"text": json.dumps(payload), "type": "text"}],
        "id": "msg_phase7_v2_test",
        "model": MODEL,
        "stop_reason": stop_reason,
        "usage": {"input_tokens": 100, "output_tokens": output_tokens},
    }


def test_v2_changes_only_request_output_cap() -> None:
    v1_rows = {row["blinded_request_id"]: row for row in jsonl(V1 / "blinded/request_payloads.jsonl")}
    v2_rows = {row["blinded_request_id"]: row for row in jsonl(V2 / "blinded/request_payloads.jsonl")}
    assert len(v1_rows) == len(v2_rows) == 170
    assert set(v1_rows) == set(v2_rows)
    for blinded_id in v1_rows:
        v1_request = copy.deepcopy(v1_rows[blinded_id]["request"])
        v2_request = copy.deepcopy(v2_rows[blinded_id]["request"])
        assert v1_request.pop("max_tokens") == V1_MAX_OUTPUT_TOKENS == 256
        assert v2_request.pop("max_tokens") == MAX_OUTPUT_TOKENS == 512
        assert v1_request == v2_request
        assert v1_rows[blinded_id]["request_sha256"] != v2_rows[blinded_id][
            "request_sha256"
        ]


def test_v1_bytes_and_commits_are_preserved() -> None:
    preservation = load(AUDIT / "v1_preservation.json")
    assert preservation["v1_evidence"] == {
        "attempted_request_n": 2,
        "completed_valid_request_n": 1,
        "failure_blinded_request_id": "P7B002",
        "failure_class": "truncation",
        "full_panel_executed": False,
        "model_matched": True,
        "retry_n": 0,
        "spent_usd": 0.005847,
    }
    for relative, expected in preservation["v1_artifact_hashes"].items():
        assert sha256_file(ROOT / relative) == expected


def test_unchanged_context_prompt_schema_and_protocols() -> None:
    byte_identical = [
        "blinded/serialized_contexts.jsonl",
        "prompt.txt",
        "response_schema.json",
        "evaluator_protocol.json",
        "h5_protocol.json",
        "sealed/trace_plan.json",
    ]
    for relative in byte_identical:
        assert (V1 / relative).read_bytes() == (V2 / relative).read_bytes()
    assert load(V1 / "failure_contract.json")["failure_classes"] == load(
        V2 / "failure_contract.json"
    )["failure_classes"]
    assert load(V2 / "execution_config.json")["generation"]["max_output_tokens"] == 512


def test_same_deterministic_trace_ids() -> None:
    v1_ids = [row["logical_request_id"] for row in load(V1 / "sealed/trace_plan.json")["selected"]]
    v2_ids = [row["logical_request_id"] for row in load(V2 / "sealed/trace_plan.json")["selected"]]
    assert v2_ids == v1_ids == load(V2 / "freeze_manifest.json")["trace_logical_request_ids"]


def test_token_limit_finish_fails_closed_at_512() -> None:
    response = valid_response(stop_reason="max_tokens", output_tokens=512)
    with pytest.raises(Phase7ExecutionFailure) as truncated:
        validate_provider_response(response, available_evidence_ids={"E01", "E02", "E03"})
    assert truncated.value.failure_class == "truncation"
    response["stop_reason"] = "end_turn"
    assert validate_provider_response(
        response, available_evidence_ids={"E01", "E02", "E03"}
    )["usage"]["output_tokens"] == 512


def test_v2_output_path_cannot_overlap_v1() -> None:
    target = V2 / "trace_v2/blinded/P7B001.json"
    assert assert_v2_output_path(target, v2_root=V2, v1_root=V1) == target.resolve()
    with pytest.raises(Phase7V2ContractError):
        assert_v2_output_path(
            V1 / "trace_v1/blinded/raw_responses/P7B001.json",
            v2_root=V2,
            v1_root=V1,
        )


def test_trace_reuse_requires_exact_v2_panel_request() -> None:
    request = jsonl(V2 / "blinded/request_payloads.jsonl")[0]["request"]
    digest = validate_trace_reuse(
        trace_request=request,
        frozen_panel_request=request,
        response_valid=True,
        already_has_panel_output=False,
    )
    assert isinstance(digest, str) and len(digest) == 64
    changed = copy.deepcopy(request)
    changed["max_tokens"] = 256
    with pytest.raises(Phase7V2ContractError, match="hash differs"):
        validate_trace_reuse(
            trace_request=changed,
            frozen_panel_request=request,
            response_valid=True,
            already_has_panel_output=False,
        )
    with pytest.raises(Phase7V2ContractError, match="invalid"):
        validate_trace_reuse(
            trace_request=request,
            frozen_panel_request=request,
            response_valid=False,
            already_has_panel_output=False,
        )
    with pytest.raises(Phase7V2ContractError, match="duplicate billing"):
        validate_trace_reuse(
            trace_request=request,
            frozen_panel_request=request,
            response_valid=True,
            already_has_panel_output=True,
        )


def test_dispatch_has_no_hidden_retry() -> None:
    calls = 0

    def fail(_request: dict) -> None:
        nonlocal calls
        calls += 1
        raise ConnectionError("terminal")

    request = jsonl(V2 / "blinded/request_payloads.jsonl")[0]["request"]
    with pytest.raises(ConnectionError, match="terminal"):
        dispatch_once_after_cap_gate(
            projected_cumulative_usd=1.2,
            request=request,
            sender=fail,
        )
    assert calls == 1


def test_cumulative_cost_includes_v1_and_cap_precedes_dispatch() -> None:
    cost = load(V2 / "cost_plan.json")
    projected = projected_cumulative_exposure_usd(
        v2_observed_input_tokens=0,
        v2_observed_output_tokens=0,
        unexecuted_input_token_envelope=cost["full_panel"]["input_token_envelope"],
        unexecuted_request_n=170,
        ambiguous_dispatch_reserve_usd=cost["ambiguous_dispatch_reserve"]["usd"],
    )
    assert projected == pytest.approx(1.119437)
    assert projected == cost["cumulative_worst_case_including_v1_usd"]
    assert cost["v1_spent_usd"] == V1_SPENT_USD
    assert cost["current_hard_cap_usd"] == HARD_COST_CAP_USD == 3.0
    assert cost["headroom_after_cumulative_worst_case_usd"] == pytest.approx(1.880563)

    calls = 0

    def sender(_request: dict) -> None:
        nonlocal calls
        calls += 1

    request = jsonl(V2 / "blinded/request_payloads.jsonl")[0]["request"]
    with pytest.raises(Phase7ExecutionFailure) as cap:
        dispatch_once_after_cap_gate(
            projected_cumulative_usd=3.000001,
            request=request,
            sender=sender,
        )
    assert cap.value.failure_class == "cost_cap_breach"
    assert calls == 0


def test_manifest_and_offline_readiness_verify() -> None:
    manifest = load(V2 / "freeze_manifest.json")
    for field in ("artifacts", "code"):
        for relative, expected in manifest[field].items():
            assert sha256_file(ROOT / relative) == expected
    assert manifest["hard_cap_pass"] is True
    assert manifest["live_api_calls_n"] == 0
    assert manifest["execution_authorized"] is False
    readiness = load(AUDIT / "freeze_readiness.json")
    assert readiness["api_calls_n"] == readiness["credential_access_n"] == 0
    assert readiness["status"] == "ready_for_commit_bound_owner_trace_approval"
