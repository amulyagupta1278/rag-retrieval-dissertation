"""Fail-closed Claude contract for Phase 5 Prompt-RAG provider recovery.

This module never calls network during import. Live transport is created only by
``create_client_from_environment`` and remains injectable for offline tests.
"""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Callable, Iterable, Mapping
from importlib import metadata
from typing import Any

import anthropic

from src.utils.atomic_io import stable_json
from src.utils.hashing import sha256_text


MODEL = "claude-haiku-4-5-20251001"
SDK_VERSION = "0.116.0"
API_VERSION = "2023-06-01"
CANDIDATE_N = 50
SCORE_MIN = 0
SCORE_MAX = 3
MAX_OUTPUT_TOKENS = 2048
TIMEOUT_SECONDS = 120.0
INPUT_USD_PER_MILLION = 1.0
OUTPUT_USD_PER_MILLION = 5.0
HARD_COST_CAP_USD = 1.90


class ClaudeContractError(ValueError):
    """Frozen request, response, or budget contract violation."""


class ClaudeProviderError(RuntimeError):
    """Sanitized terminal provider failure; provider body is never retained."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def build_response_schema(expected_chunk_ids: Iterable[str]) -> dict[str, Any]:
    """Build strict schema bound to exactly 50 supplied chunk IDs."""

    chunk_ids = list(expected_chunk_ids)
    if len(chunk_ids) != CANDIDATE_N or len(set(chunk_ids)) != CANDIDATE_N:
        raise ClaudeContractError("response schema requires 50 unique chunk IDs")
    if any(not isinstance(chunk_id, str) or not chunk_id for chunk_id in chunk_ids):
        raise ClaudeContractError("chunk IDs must be non-empty strings")
    return {
        "additionalProperties": False,
        "properties": {
            "candidate_scores": {
                "items": {
                    "additionalProperties": False,
                    "properties": {
                        "chunk_id": {"enum": sorted(chunk_ids), "type": "string"},
                        "score": {
                            "maximum": SCORE_MAX,
                            "minimum": SCORE_MIN,
                            "type": "integer",
                        },
                    },
                    "required": ["chunk_id", "score"],
                    "type": "object",
                },
                "maxItems": CANDIDATE_N,
                "minItems": CANDIDATE_N,
                "type": "array",
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
    """Build one stateless Messages API request without hidden benchmark data."""

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
    """Parse exact 0..3 integer scores and rank score-desc/chunk-ID-asc."""

    expected = list(expected_chunk_ids)
    if len(expected) != CANDIDATE_N or len(set(expected)) != CANDIDATE_N:
        raise ClaudeContractError("expected candidate set must contain 50 unique IDs")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ClaudeContractError(f"malformed JSON: {exc.msg}") from exc
    if not isinstance(payload, dict) or set(payload) != {"candidate_scores"}:
        raise ClaudeContractError("response must contain only candidate_scores")
    rows = payload["candidate_scores"]
    if not isinstance(rows, list) or len(rows) != CANDIDATE_N:
        raise ClaudeContractError("response must contain exactly 50 scores")

    scores: dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"chunk_id", "score"}:
            raise ClaudeContractError(
                f"candidate_scores[{index}] must contain only chunk_id and score"
            )
        chunk_id, score = row["chunk_id"], row["score"]
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ClaudeContractError(f"candidate_scores[{index}] chunk_id is invalid")
        if chunk_id in scores:
            raise ClaudeContractError(f"duplicate response chunk_id: {chunk_id}")
        if isinstance(score, bool) or not isinstance(score, int):
            raise ClaudeContractError(f"score for {chunk_id} must be an integer")
        if not SCORE_MIN <= score <= SCORE_MAX:
            raise ClaudeContractError(f"score for {chunk_id} is outside 0..3")
        scores[chunk_id] = score
    if set(scores) != set(expected):
        missing = sorted(set(expected) - set(scores))
        extra = sorted(set(scores) - set(expected))
        raise ClaudeContractError(
            f"response candidate set mismatch; missing={missing}, extra={extra}"
        )
    return [
        {"chunk_id": chunk_id, "rank": rank, "score": score}
        for rank, (chunk_id, score) in enumerate(
            sorted(scores.items(), key=lambda item: (-item[1], item[0])), start=1
        )
    ]


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return copy.deepcopy(dict(value))
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=True)
    raise ClaudeContractError("response is not serializable")


def validate_response(
    response: Any, *, expected_chunk_ids: Iterable[str]
) -> dict[str, Any]:
    """Reject model drift, refusal, truncation, tools, or malformed JSON."""

    raw = _mapping(response)
    response_id = raw.get("id")
    returned_model = raw.get("model")
    if not isinstance(response_id, str) or not response_id:
        raise ClaudeContractError("missing response id")
    if returned_model != MODEL:
        raise ClaudeContractError(
            f"returned model mismatch: expected {MODEL}, got {returned_model}"
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
    ranking = parse_scored_response(text, expected_chunk_ids)

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
    return {
        "model": returned_model,
        "ranking": ranking,
        "raw_response": raw,
        "response_id": response_id,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


def enforce_sdk_version() -> None:
    """Reject runtime SDK drift from exact frozen version."""

    try:
        installed = metadata.version("anthropic")
    except metadata.PackageNotFoundError:
        raise ClaudeProviderError("required anthropic SDK is not installed") from None
    if installed != SDK_VERSION:
        raise ClaudeProviderError(
            f"anthropic version mismatch: expected {SDK_VERSION}, got {installed}"
        )


def create_client_from_environment(
    *,
    environ: Mapping[str, str] | None = None,
    client_factory: Callable[..., Any] = anthropic.Anthropic,
) -> Any:
    """Create no-auto-retry client from environment without exposing key."""

    enforce_sdk_version()
    environment = os.environ if environ is None else environ
    api_key = environment.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ClaudeProviderError("ANTHROPIC_API_KEY is missing")
    return client_factory(
        api_key=api_key,
        max_retries=0,
        timeout=TIMEOUT_SECONDS,
    )


def make_live_sender(client: Any) -> Callable[[dict[str, Any]], Any]:
    """Create explicit sender; no request occurs until returned function runs."""

    def send(request: dict[str, Any]) -> Any:
        try:
            return client.messages.create(**copy.deepcopy(request))
        except anthropic.APIStatusError as exc:
            raise ClaudeProviderError(
                "terminal Claude API status error", status_code=exc.status_code
            ) from None
        except anthropic.APITimeoutError:
            raise ClaudeProviderError("terminal Claude API timeout", status_code=408) from None
        except anthropic.APIConnectionError:
            raise ClaudeProviderError("terminal Claude API connection error") from None

    return send


def make_token_counter(client: Any) -> Callable[[dict[str, Any]], int]:
    """Create count-tokens sender using exact request fields accepted by endpoint."""

    def count(request: dict[str, Any]) -> int:
        fields = {
            key: copy.deepcopy(request[key])
            for key in ("messages", "model", "output_config", "system", "tools")
        }
        try:
            result = client.messages.count_tokens(**fields)
        except anthropic.APIStatusError as exc:
            raise ClaudeProviderError(
                "Claude token-count status error", status_code=exc.status_code
            ) from None
        except (anthropic.APIConnectionError, anthropic.APITimeoutError):
            raise ClaudeProviderError("Claude token-count transport error") from None
        value = getattr(result, "input_tokens", None)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ClaudeContractError("token-count endpoint returned invalid count")
        return value

    return count


def request_sha256(request: Mapping[str, Any]) -> str:
    """Return canonical request hash."""

    return sha256_text(stable_json(dict(request)))


def maximum_cost_usd(input_tokens: int, request_n: int) -> float:
    """Calculate worst case at exact input counts and frozen max output."""

    if input_tokens < 0 or request_n < 0:
        raise ClaudeContractError("token and request counts cannot be negative")
    return (
        input_tokens * INPUT_USD_PER_MILLION
        + request_n * MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def observed_cost_usd(input_tokens: int, output_tokens: int) -> float:
    """Calculate provider-list-price cost from authoritative observed usage."""

    if input_tokens < 0 or output_tokens < 0:
        raise ClaudeContractError("observed token counts cannot be negative")
    return (
        input_tokens * INPUT_USD_PER_MILLION
        + output_tokens * OUTPUT_USD_PER_MILLION
    ) / 1_000_000
