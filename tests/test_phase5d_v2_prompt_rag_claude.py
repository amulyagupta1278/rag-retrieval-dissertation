"""Offline tests for Phase 5D V2 fixed-key Claude contract."""

from __future__ import annotations

import pytest
pytest.importorskip(
    "sentence_transformers",
    reason=(
        "SKIPPED 2026-07-27: requires sentence_transformers (and faiss-cpu / "
        "torch) which are not installed in the evaluation sandbox. "
        "These tests exercise retriever inference and Phase 5 pipeline "
        "contracts that depend on ML inference libraries. Install the full "
        "requirements (pip install sentence-transformers faiss-cpu) to run."
    ),
)


import copy
import json
from pathlib import Path

import pytest

from scripts import evaluate_phase5d_v2_claude_trace as evaluator
from scripts import run_phase5d_v2_prompt_rag_claude as runner
from src.retrievers.prompt_rag_claude_v2 import (
    CUMULATIVE_TRACE_WORST_CASE_USD,
    HARD_COST_CAP_USD,
    MODEL,
    PRIOR_SPENT_USD,
    REMAINING_CAP_USD,
    TRACE_REQUEST_N,
    TRACE_WORST_CASE_COST_USD,
    ClaudeContractError,
    build_request,
    build_response_schema,
    parse_scored_response,
    request_sha256,
    validate_response,
)
from src.utils.hashing import sha256_file


ROOT = Path(__file__).parents[1]


def ids() -> list[str]:
    return [f"chunk-{index:02d}" for index in range(50)]


def request() -> dict:
    return build_request(
        query={"query_id": "v2q-001", "question": "Question?"},
        candidates=[
            {"chunk_id": chunk_id, "text": f"Text {chunk_id}"}
            for chunk_id in ids()
        ],
        system_instruction="Score only.",
    )


def scored_text(*, missing_last: bool = False, score: int = 2) -> str:
    chunk_ids = ids()[:-1] if missing_last else ids()
    return json.dumps(
        {"candidate_scores": {chunk_id: score for chunk_id in chunk_ids}}
    )


def response(*, missing_last: bool = False) -> dict:
    return {
        "content": [{"text": scored_text(missing_last=missing_last), "type": "text"}],
        "id": "msg_v2_test",
        "model": MODEL,
        "role": "assistant",
        "stop_reason": "end_turn",
        "type": "message",
        "usage": {
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "input_tokens": 25000,
            "output_tokens": 500,
        },
    }


def test_fixed_key_schema_requires_every_exact_id_and_rejects_extras() -> None:
    schema = build_response_schema(reversed(ids()))
    assert schema["additionalProperties"] is False
    scores = schema["properties"]["candidate_scores"]
    assert scores["type"] == "object"
    assert scores["additionalProperties"] is False
    assert scores["required"] == sorted(ids())
    assert scores["properties"] == {
        chunk_id: {"type": "integer"} for chunk_id in sorted(ids())
    }
    assert "items" not in scores


def test_request_preserves_frozen_model_prompt_candidates_and_controls() -> None:
    payload = request()
    assert payload["model"] == MODEL == "claude-haiku-4-5-20251001"
    assert payload["temperature"] == 0
    assert payload["max_tokens"] == 2048
    assert payload["service_tier"] == "standard_only"
    assert payload["stream"] is False and payload["tools"] == []
    exposed = json.loads(payload["messages"][0]["content"])
    assert list(row["chunk_id"] for row in exposed["candidates"]) == ids()
    assert set(exposed) == {"candidates", "query_id", "question"}
    serialized = json.dumps(payload).lower()
    for forbidden in (
        "qrels",
        "reference_answer",
        "category",
        "owner_judgments",
        "first_stage_rank",
        "first_stage_score",
    ):
        assert forbidden not in serialized


def test_parser_ranks_score_descending_then_chunk_id() -> None:
    scores = {chunk_id: index % 4 for index, chunk_id in enumerate(ids())}
    ranking = parse_scored_response(json.dumps({"candidate_scores": scores}), ids())
    assert ranking == sorted(ranking, key=lambda row: (-row["score"], row["chunk_id"]))
    assert [row["rank"] for row in ranking] == list(range(1, 51))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda body: body["candidate_scores"].pop(ids()[-1]), "mismatch"),
        (lambda body: body["candidate_scores"].update(extra=1), "mismatch"),
        (lambda body: body["candidate_scores"].update({ids()[0]: True}), "integer"),
        (lambda body: body["candidate_scores"].update({ids()[0]: 1.0}), "integer"),
        (lambda body: body["candidate_scores"].update({ids()[0]: 4}), "outside"),
        (lambda body: body.update(extra=True), "only candidate_scores"),
    ],
)
def test_malformed_fixed_key_output_fails_closed(mutate, message: str) -> None:
    body = json.loads(scored_text())
    mutate(body)
    with pytest.raises(ClaudeContractError, match=message):
        parse_scored_response(json.dumps(body), ids())


def test_valid_provider_response_preserves_usage_and_ranking() -> None:
    result = validate_response(response(), expected_chunk_ids=ids())
    assert result["usage"] == {"input_tokens": 25000, "output_tokens": 500}
    assert result["response_id"] == "msg_v2_test"
    assert len(result["ranking"]) == 50


def test_offline_serialization_rebuilds_exact_34_requests() -> None:
    frozen = runner.preflight()
    assert frozen["query_ids"] == [f"v2q-{index:03d}" for index in range(1, 35)]
    assert len(frozen["requests"]) == 34
    plan = runner.build_trace_plan(frozen["trace_ids"])
    assert len(plan) == TRACE_REQUEST_N == 24
    assert [role.split(":")[-1] for role, _ in plan[:8]] == ["primary"] * 8
    assert all(len(frozen["rankings"][query_id]) == 50 for query_id in frozen["query_ids"])


def test_v1_failure_evidence_is_hash_preserved_and_excluded_from_v2() -> None:
    preserved = json.loads((ROOT / "audits/phase5d_v2/v1_preservation.json").read_text())
    for relative, expected in preserved["v1_artifact_hashes"].items():
        assert sha256_file(ROOT / relative) == expected
    assert runner.OUTPUT_ROOT != ROOT / "runs/v2/phase5d_prompt_rag_claude_v1"
    source = (ROOT / "scripts/run_phase5d_v2_prompt_rag_claude.py").read_text()
    assert "phase5d_prompt_rag_claude_v1/trace/raw" not in source


def test_cumulative_cost_contract_retains_prior_spend() -> None:
    assert PRIOR_SPENT_USD == 0.177402
    assert REMAINING_CAP_USD == 1.722598
    assert TRACE_WORST_CASE_COST_USD == 0.951723
    assert CUMULATIVE_TRACE_WORST_CASE_USD == 1.129125
    assert PRIOR_SPENT_USD + REMAINING_CAP_USD == pytest.approx(HARD_COST_CAP_USD)
    ledger = runner._initial_ledger(runner.build_trace_plan(ids()[:8]))
    assert runner._projected_cumulative_cost(ledger, 24) == pytest.approx(1.129125)


def test_owner_approval_is_pending_and_exact_statement_is_commit_bound() -> None:
    approval = json.loads(runner.APPROVAL_PATH.read_text())
    assert approval["status"] == "pending_owner_approval"
    with pytest.raises(ClaudeContractError, match="lacks owner approval"):
        runner._validate_approval()
    statement = runner.expected_approval_statement("a" * 40)
    assert "24-call trace" in statement
    assert "a" * 40 in statement
    assert "$0.177402 spent" in statement and "$1.722598 remaining" in statement


def test_invalid_http_200_usage_is_accounted_before_schema_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "phase5d_v2"
    monkeypatch.setattr(runner, "OUTPUT_ROOT", output)
    monkeypatch.setattr(runner, "_validate_approval", lambda: {})
    frozen = {
        "trace_ids": ids()[:8],
        "rankings": {query_id: ids() for query_id in ids()[:8]},
        "requests": {query_id: request() for query_id in ids()[:8]},
    }

    class Messages:
        def create(self, **_payload):
            return response(missing_last=True)

    client = type("Client", (), {"messages": Messages()})()
    assert runner.run_trace(frozen, client_factory=lambda: client) == 76
    ledger = json.loads((output / "trace/control/ledger.json").read_text())
    assert ledger["attempted_generation_request_n"] == 1
    assert ledger["actual_input_tokens"] == 25000
    assert ledger["actual_output_tokens"] == 500
    assert ledger["v2_observed_cost_usd"] == pytest.approx(0.0275)
    assert ledger["cumulative_observed_cost_usd"] == pytest.approx(0.204902)
    assert ledger["status"] == "failed"


def test_hard_request_cap_refuses_attempt_25(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output = tmp_path / "phase5d_v2"
    monkeypatch.setattr(runner, "OUTPUT_ROOT", output)
    monkeypatch.setattr(runner, "_validate_approval", lambda: {})
    trace_ids = ids()[:8]
    plan = runner.build_trace_plan(trace_ids)
    ledger = runner._initial_ledger(plan)
    ledger["attempted_generation_request_n"] = 24
    control = output / "trace/control"
    control.mkdir(parents=True)
    (control / "ledger.json").write_text(json.dumps(ledger))
    frozen = {
        "trace_ids": trace_ids,
        "rankings": {query_id: ids() for query_id in trace_ids},
        "requests": {query_id: request() for query_id in trace_ids},
    }
    client = type("Client", (), {"messages": object()})()
    with pytest.raises(ClaudeContractError, match="hard request cap reached"):
        runner.run_trace(frozen, client_factory=lambda: client)


def test_repeatability_logic_remains_five_metric_panel() -> None:
    ranking = validate_response(response(), expected_chunk_ids=ids())["ranking"]
    assert evaluator.compare(ranking, copy.deepcopy(ranking)) == {
        "candidate_score_agreement": 1.0,
        "kendall_tau_b": 1.0,
        "ranking_position_agreement": 1.0,
        "spearman_rho": 1.0,
        "top_10_overlap": 1.0,
    }
    source = (ROOT / "scripts/evaluate_phase5d_v2_claude_trace.py").read_text()
    for forbidden in ("qrels", "reference_answer", "owner_judgments", "category"):
        assert forbidden not in source


def test_gemini_archive_hashes_and_inactive_paths() -> None:
    manifest = json.loads(
        (ROOT / "archive/phase5_gemini_failed/manifest.json").read_text()
    )
    assert manifest["artifact_n"] == len(manifest["artifacts"]) == 36
    for row in manifest["artifacts"]:
        archived = ROOT / row["archived_path"]
        assert archived.stat().st_size == row["byte_size"]
        assert sha256_file(archived) == row["sha256"]
        assert not (ROOT / row["original_path"]).exists()
    assert "google-genai" not in (ROOT / "requirements.txt").read_text()
    assert "google-genai" not in (ROOT / "pyproject.toml").read_text()


def test_no_live_call_or_v2_output_exists_during_freeze() -> None:
    assert not runner.OUTPUT_ROOT.exists()
    manifest = json.loads((ROOT / "audits/phase5d_v2/freeze_manifest.json").read_text())
    assert manifest["v2_generation_calls_during_freeze"] == 0
    assert manifest["live_api_calls_during_correction"] == 0
    assert request_sha256(request())
