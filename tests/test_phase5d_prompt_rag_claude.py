"""Offline contract tests for Claude provider recovery."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import evaluate_phase5d_claude_trace as evaluator
from scripts import run_phase5d_prompt_rag_claude as runner
from src.retrievers.prompt_rag_claude_v1 import (
    API_VERSION,
    HARD_COST_CAP_USD,
    MAX_OUTPUT_TOKENS,
    MODEL,
    SDK_VERSION,
    ClaudeContractError,
    ClaudeProviderError,
    build_request,
    build_response_schema,
    create_client_from_environment,
    make_live_sender,
    make_token_counter,
    maximum_cost_usd,
    observed_cost_usd,
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
        candidates=[{"chunk_id": chunk_id, "text": f"Text {chunk_id}"} for chunk_id in ids()],
        system_instruction="Score only.",
    )


def scored_text(score: int = 2) -> str:
    return json.dumps(
        {"candidate_scores": [{"chunk_id": chunk_id, "score": score} for chunk_id in ids()]}
    )


def response(*, model: str = MODEL, stop_reason: str = "end_turn") -> dict:
    return {
        "content": [{"text": scored_text(), "type": "text"}],
        "id": "msg_test",
        "model": model,
        "role": "assistant",
        "stop_reason": stop_reason,
        "type": "message",
        "usage": {
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "input_tokens": 25000,
            "output_tokens": 900,
        },
    }


def test_frozen_provider_model_sdk_prompt_and_cost() -> None:
    config = json.loads((ROOT / "configs/prompt_rag_claude_v1_frozen.json").read_text())
    assert config["provider"] == "Anthropic Claude API"
    assert config["model"] == MODEL == "claude-haiku-4-5-20251001"
    assert config["api_version"] == API_VERSION == "2023-06-01"
    assert config["sdk"] == {"name": "anthropic", "version": SDK_VERSION}
    assert config["prompt"]["sha256"] == sha256_file(ROOT / config["prompt"]["path"])
    assert config["cost_control"]["hard_total_cost_cap_usd"] == HARD_COST_CAP_USD


def test_request_exact_controls_and_no_hidden_inputs() -> None:
    payload = request()
    assert payload["model"] == MODEL
    assert payload["max_tokens"] == MAX_OUTPUT_TOKENS == 2048
    assert payload["temperature"] == 0
    assert payload["service_tier"] == "standard_only"
    assert payload["stream"] is False
    assert payload["tools"] == []
    assert "thinking" not in payload and "cache_control" not in payload
    assert set(payload["messages"][0]) == {"content", "role"}
    exposed = json.loads(payload["messages"][0]["content"])
    assert set(exposed) == {"candidates", "query_id", "question"}
    assert all(set(row) == {"chunk_id", "text"} for row in exposed["candidates"])
    serialized = json.dumps(payload).lower()
    for forbidden in (
        "qrels",
        "reference_answer",
        "category",
        "gold_evidence",
        "owner_judgments",
        "first_stage_score",
        "first_stage_rank",
    ):
        assert forbidden not in serialized


def test_schema_and_ranking_are_strict_and_deterministic() -> None:
    schema = build_response_schema(ids())
    assert schema["additionalProperties"] is False
    item = schema["properties"]["candidate_scores"]["items"]
    assert item["properties"]["chunk_id"]["enum"] == sorted(ids())
    scores = [{"chunk_id": chunk_id, "score": index % 4} for index, chunk_id in enumerate(ids())]
    ranking = parse_scored_response(json.dumps({"candidate_scores": scores}), ids())
    assert ranking == sorted(ranking, key=lambda row: (-row["score"], row["chunk_id"]))
    assert [row["rank"] for row in ranking] == list(range(1, 51))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda body: body["candidate_scores"].pop(), "exactly 50"),
        (
            lambda body: body["candidate_scores"].__setitem__(
                1, copy.deepcopy(body["candidate_scores"][0])
            ),
            "duplicate",
        ),
        (lambda body: body["candidate_scores"][0].update(score=4), "outside 0..3"),
        (lambda body: body["candidate_scores"][0].update(score=1.0), "integer"),
        (lambda body: body.update(extra=True), "only candidate_scores"),
    ],
)
def test_malformed_scores_fail_closed(mutate, message: str) -> None:
    body = json.loads(scored_text())
    mutate(body)
    with pytest.raises(ClaudeContractError, match=message):
        parse_scored_response(json.dumps(body), ids())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda body: body.update(model="claude-haiku-4-5"), "model mismatch"),
        (lambda body: body.update(stop_reason="max_tokens"), "non-complete"),
        (lambda body: body.update(stop_reason="refusal"), "non-complete"),
        (lambda body: body.update(content=[]), "exactly one content"),
        (lambda body: body["content"][0].update(type="tool_use"), "non-text"),
        (lambda body: body.pop("usage"), "missing usage"),
    ],
)
def test_bad_provider_responses_fail_closed(mutate, message: str) -> None:
    body = response()
    mutate(body)
    with pytest.raises(ClaudeContractError, match=message):
        validate_response(body, expected_chunk_ids=ids())


def test_valid_response_preserves_usage_and_exact_model() -> None:
    result = validate_response(response(), expected_chunk_ids=ids())
    assert result["model"] == MODEL
    assert result["response_id"] == "msg_test"
    assert result["usage"] == {"input_tokens": 25000, "output_tokens": 900}
    assert len(result["ranking"]) == 50


def test_client_requires_environment_key_and_disables_sdk_retries() -> None:
    with pytest.raises(ClaudeProviderError, match="ANTHROPIC_API_KEY is missing"):
        create_client_from_environment(environ={})
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return object()

    client = create_client_from_environment(
        environ={"ANTHROPIC_API_KEY": "secret-test-value"}, client_factory=factory
    )
    assert client is not None
    assert captured == {
        "api_key": "secret-test-value",
        "max_retries": 0,
        "timeout": 120.0,
    }
    assert "secret-test-value" not in request_sha256(request())


def test_live_sender_and_counter_are_injectable_and_do_not_retry() -> None:
    class Messages:
        def __init__(self) -> None:
            self.create_n = 0
            self.count_n = 0

        def create(self, **payload):
            self.create_n += 1
            assert payload == request()
            return response()

        def count_tokens(self, **payload):
            self.count_n += 1
            assert set(payload) == {"messages", "model", "output_config", "system", "tools"}
            return type("Count", (), {"input_tokens": 1234})()

    client = type("Client", (), {"messages": Messages()})()
    assert make_live_sender(client)(request()) == response()
    assert make_token_counter(client)(request()) == 1234
    assert client.messages.create_n == 1 and client.messages.count_n == 1


def test_cost_math_and_cap_use_max_output_for_all_calls() -> None:
    assert observed_cost_usd(1_000_000, 1_000_000) == 6.0
    assert maximum_cost_usd(1_264_948, 50) == pytest.approx(1.776948)
    assert maximum_cost_usd(1_264_948, 50) < HARD_COST_CAP_USD


def test_offline_preflight_rebuilds_all_34_exact_requests() -> None:
    frozen = runner.preflight()
    assert frozen["query_ids"] == [f"v2q-{index:03d}" for index in range(1, 35)]
    assert len(frozen["requests"]) == 34
    assert all(len(frozen["rankings"][query_id]) == 50 for query_id in frozen["query_ids"])
    assert frozen["trace_ids"] == [
        "v2q-017",
        "v2q-016",
        "v2q-003",
        "v2q-023",
        "v2q-013",
        "v2q-025",
        "v2q-004",
        "v2q-027",
    ]


def test_trace_and_full_plans_are_disjoint_primary_scopes() -> None:
    query_ids = [f"v2q-{index:03d}" for index in range(1, 35)]
    trace_ids = runner.preflight()["trace_ids"]
    trace = runner.build_logical_plan("trace", query_ids, trace_ids)
    full = runner.build_logical_plan("full", query_ids, trace_ids)
    assert len(trace) == 24 and len(full) == 26
    assert {query_id for logical, query_id in trace if logical.endswith(":primary")} == set(trace_ids)
    assert {query_id for _, query_id in full}.isdisjoint(trace_ids)


def test_execution_lock_blocks_concurrent_runner(tmp_path: Path) -> None:
    path = tmp_path / "execution.lock"
    with runner.ExecutionLock(path):
        assert path.is_file()
        with pytest.raises(ClaudeContractError, match="holds execution lock"):
            with runner.ExecutionLock(path):
                pass
    assert not path.exists()


def test_repeatability_comparison_detects_identical_and_changed_rankings() -> None:
    first = validate_response(response(), expected_chunk_ids=ids())["ranking"]
    assert all(value == 1.0 for value in evaluator.compare(first, first).values())
    second = copy.deepcopy(first)
    second[0]["score"] = 0
    changed = sorted(second, key=lambda row: (-row["score"], row["chunk_id"]))
    for rank, row in enumerate(changed, 1):
        row["rank"] = rank
    assert evaluator.compare(first, changed)["ranking_position_agreement"] < 1.0


def test_no_live_api_call_or_runtime_output_exists_in_offline_freeze() -> None:
    assert not (ROOT / "runs/v2/phase5d_prompt_rag_claude_v1").exists()
    source = (ROOT / "scripts/evaluate_phase5d_claude_trace.py").read_text()
    for forbidden in ("qrels", "reference_answer", "owner_judgments", "category"):
        assert forbidden not in source
