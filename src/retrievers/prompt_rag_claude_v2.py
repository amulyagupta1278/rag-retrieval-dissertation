"""Phase 5D V2 fixed-key Claude Prompt-RAG contract.

V1 array-schema failure remains preserved. V2 changes only response
serialization: ``candidate_scores`` maps each exact chunk ID to one integer.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any

from src.retrievers.prompt_rag_claude_v1 import (
    API_VERSION,
    CANDIDATE_N,
    HARD_COST_CAP_USD,
    INPUT_USD_PER_MILLION,
    MAX_OUTPUT_TOKENS,
    MODEL,
    OUTPUT_USD_PER_MILLION,
    SCORE_MAX,
    SCORE_MIN,
    SDK_VERSION,
    TIMEOUT_SECONDS,
    ClaudeContractError,
    ClaudeProviderError,
    create_client_from_environment,
    enforce_sdk_version,
    make_live_sender,
    maximum_cost_usd,
    observed_cost_usd,
)
from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_text


PRIOR_SPENT_USD = 0.177402
REMAINING_CAP_USD = 1.722598
TRACE_INPUT_TOKEN_ENVELOPE = 705_963
TRACE_REQUEST_N = 24
TRACE_WORST_CASE_COST_USD = 0.951723
CUMULATIVE_TRACE_WORST_CASE_USD = 1.129125


def build_response_schema(expected_chunk_ids: Iterable[str]) -> dict[str, Any]:
    """Require exactly one integer property for every supplied chunk ID."""

    chunk_ids = list(expected_chunk_ids)
    if len(chunk_ids) != CANDIDATE_N or len(set(chunk_ids)) != CANDIDATE_N:
        raise ClaudeContractError("response schema requires 50 unique chunk IDs")
    if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids):
        raise ClaudeContractError("chunk IDs must be non-empty strings")
    ordered = sorted(chunk_ids)
    return {
        "additionalProperties": False,
        "properties": {
            "candidate_scores": {
                "additionalProperties": False,
                "properties": {
                    chunk_id: {"type": "integer"} for chunk_id in ordered
                },
                "required": ordered,
                "type": "object",
            }
        },
        "required": ["candidate_scores"],
        "type": "object",
    }


def build_request(
    *,
    query: Mapping[str, Any],
    candidates: Iterable[Mapping[str, Any]],
    system_instruction: str,
) -> dict[str, Any]:
    """Build one stateless request using unchanged query/candidate exposure."""

    if set(query) != {"query_id", "question"}:
        raise ClaudeContractError("query must contain only query_id and question")
    if not isinstance(query["query_id"], str) or not query["query_id"]:
        raise ClaudeContractError("query_id must be a non-empty string")
    if not isinstance(query["question"], str) or not query["question"].strip():
        raise ClaudeContractError("question must be a non-empty string")
    if not isinstance(system_instruction, str) or not system_instruction.strip():
        raise ClaudeContractError("system instruction must be non-empty")

    rows = [dict(candidate) for candidate in candidates]
    if len(rows) != CANDIDATE_N:
        raise ClaudeContractError("exactly 50 candidates required")
    chunk_ids: list[str] = []
    for index, row in enumerate(rows):
        if set(row) != {"chunk_id", "text"}:
            raise ClaudeContractError(
                f"candidate[{index}] must contain only chunk_id and text"
            )
        chunk_id, text = row["chunk_id"], row["text"]
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ClaudeContractError(f"candidate[{index}] chunk_id is invalid")
        if not isinstance(text, str) or not text.strip():
            raise ClaudeContractError(f"candidate[{index}] text is invalid")
        chunk_ids.append(chunk_id)
    if len(set(chunk_ids)) != CANDIDATE_N:
        raise ClaudeContractError("duplicate candidate chunk_id")

    content = stable_json(
        {
            "candidates": rows,
            "query_id": query["query_id"],
            "question": query["question"],
        }
    )
    return {
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{"content": content, "role": "user"}],
        "model": MODEL,
        "output_config": {
            "format": {
                "schema": build_response_schema(chunk_ids),
                "type": "json_schema",
            }
        },
        "service_tier": "standard_only",
        "stream": False,
        "system": system_instruction,
        "temperature": 0,
        "tools": [],
    }


def parse_scored_response(
    raw_text: str, expected_chunk_ids: Iterable[str]
) -> list[dict[str, Any]]:
    """Parse fixed-key object and rank score-desc/chunk-ID-asc."""

    expected = list(expected_chunk_ids)
    if len(expected) != CANDIDATE_N or len(set(expected)) != CANDIDATE_N:
        raise ClaudeContractError("expected candidate set must contain 50 unique IDs")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ClaudeContractError(f"malformed JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or set(payload) != {"candidate_scores"}:
        raise ClaudeContractError("response must contain only candidate_scores")
    scores = payload["candidate_scores"]
    if not isinstance(scores, dict):
        raise ClaudeContractError("candidate_scores must be an object")
    expected_set = set(expected)
    actual_set = set(scores)
    if actual_set != expected_set:
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        raise ClaudeContractError(
            f"response candidate set mismatch; missing={missing}, extra={extra}"
        )
    for chunk_id, score in scores.items():
        if isinstance(score, bool) or not isinstance(score, int):
            raise ClaudeContractError(f"score for {chunk_id} must be an integer")
        if not SCORE_MIN <= score <= SCORE_MAX:
            raise ClaudeContractError(f"score for {chunk_id} is outside 0..3")
    return [
        {"chunk_id": chunk_id, "rank": rank, "score": score}
        for rank, (chunk_id, score) in enumerate(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])), start=1
        )
    ]


def response_mapping(value: Any) -> dict[str, Any]:
    """Return credential-free JSON mapping for provider response."""

    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise ClaudeContractError("response is not serializable")


def extract_usage(raw: Mapping[str, Any]) -> dict[str, int]:
    """Extract billable usage even when response contract later fails."""

    usage = raw.get("usage")
    if not isinstance(usage, Mapping):
        raise ClaudeContractError("missing usage metadata")
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if (
        isinstance(input_tokens, bool)
        or not isinstance(input_tokens, int)
        or input_tokens <= 0
        or isinstance(output_tokens, bool)
        or not isinstance(output_tokens, int)
        or output_tokens <= 0
    ):
        raise ClaudeContractError("invalid usage token counts")
    if int(usage.get("cache_creation_input_tokens") or 0) != 0:
        raise ClaudeContractError("unexpected cache creation usage")
    if int(usage.get("cache_read_input_tokens") or 0) != 0:
        raise ClaudeContractError("unexpected cache read usage")
    return {"input_tokens": input_tokens, "output_tokens": output_tokens}


def validate_response(
    response: Any, *, expected_chunk_ids: Iterable[str]
) -> dict[str, Any]:
    """Reject model drift, refusal, truncation, tools, or malformed scores."""

    raw = response_mapping(response)
    response_id = raw.get("id")
    if not isinstance(response_id, str) or not response_id:
        raise ClaudeContractError("missing response id")
    if raw.get("model") != MODEL:
        raise ClaudeContractError(
            f"returned model mismatch: expected {MODEL}, got {raw.get('model')}"
        )
    if raw.get("type") != "message" or raw.get("role") != "assistant":
        raise ClaudeContractError("incomplete message envelope")
    if raw.get("stop_reason") != "end_turn":
        raise ClaudeContractError(f"non-complete stop reason: {raw.get('stop_reason')}")
    if raw.get("stop_details") not in (None, {}):
        raise ClaudeContractError("refusal or unexpected stop details")
    content = raw.get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise ClaudeContractError("response must contain exactly one content block")
    block = content[0]
    if not isinstance(block, Mapping) or block.get("type") != "text":
        raise ClaudeContractError("unexpected tool or non-text content block")
    if set(block) - {"citations", "text", "type"}:
        raise ClaudeContractError("unexpected text-block fields")
    if block.get("citations") not in (None, []):
        raise ClaudeContractError("unexpected citations")
    text = block.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ClaudeContractError("empty response text")
    usage = extract_usage(raw)
    return {
        "model": MODEL,
        "ranking": parse_scored_response(text, expected_chunk_ids),
        "raw_response": raw,
        "response_id": response_id,
        "usage": usage,
    }


def request_sha256(request: Mapping[str, Any]) -> str:
    """Return canonical request hash."""

    return sha256_text(stable_json(dict(request)))


__all__ = [
    "API_VERSION",
    "CANDIDATE_N",
    "CUMULATIVE_TRACE_WORST_CASE_USD",
    "HARD_COST_CAP_USD",
    "INPUT_USD_PER_MILLION",
    "MAX_OUTPUT_TOKENS",
    "MODEL",
    "OUTPUT_USD_PER_MILLION",
    "PRIOR_SPENT_USD",
    "REMAINING_CAP_USD",
    "SDK_VERSION",
    "TIMEOUT_SECONDS",
    "TRACE_INPUT_TOKEN_ENVELOPE",
    "TRACE_REQUEST_N",
    "TRACE_WORST_CASE_COST_USD",
    "ClaudeContractError",
    "ClaudeProviderError",
    "build_request",
    "build_response_schema",
    "create_client_from_environment",
    "enforce_sdk_version",
    "extract_usage",
    "make_live_sender",
    "maximum_cost_usd",
    "observed_cost_usd",
    "parse_scored_response",
    "request_sha256",
    "response_mapping",
    "validate_response",
]
