"""Fail-closed Prompt-RAG contract for Phase 8 R4 mixed candidate unions."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any

from src.retrievers.prompt_rag_claude_v2 import (
    MODEL, ClaudeContractError, extract_usage, response_mapping,
)
from src.utils.atomic_io import stable_json

MIN_CANDIDATES = 25
MAX_CANDIDATES = 50
MAX_OUTPUT_TOKENS = 512


def _ids(chunk_ids: Iterable[str]) -> list[str]:
    values = list(chunk_ids)
    if not MIN_CANDIDATES <= len(values) <= MAX_CANDIDATES:
        raise ClaudeContractError("R4 schema requires 25..50 candidates")
    if len(set(values)) != len(values) or any(not isinstance(v, str) or not v for v in values):
        raise ClaudeContractError("R4 candidate IDs invalid")
    return values


def build_response_schema(chunk_ids: Iterable[str]) -> dict[str, Any]:
    ordered = sorted(_ids(chunk_ids))
    return {
        "additionalProperties": False,
        "properties": {"candidate_scores": {
            "additionalProperties": False,
            "properties": {chunk_id: {"type": "integer"} for chunk_id in ordered},
            "required": ordered,
            "type": "object",
        }},
        "required": ["candidate_scores"],
        "type": "object",
    }


def build_request(*, query: Mapping[str, str], candidates: Iterable[Mapping[str, str]], system_instruction: str) -> dict[str, Any]:
    rows = [dict(row) for row in candidates]
    if set(query) != {"query_id", "question"} or not all(isinstance(v, str) and v.strip() for v in query.values()):
        raise ClaudeContractError("R4 query contract differs")
    if any(set(row) != {"chunk_id", "text"} for row in rows):
        raise ClaudeContractError("R4 candidates require only chunk_id/text")
    ids = _ids(row["chunk_id"] for row in rows)
    if any(not isinstance(row["text"], str) or not row["text"].strip() for row in rows):
        raise ClaudeContractError("R4 candidate text invalid")
    return {
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{"content": stable_json({"candidates": rows, **dict(query)}), "role": "user"}],
        "model": MODEL,
        "output_config": {"format": {"schema": build_response_schema(ids), "type": "json_schema"}},
        "service_tier": "standard_only",
        "stream": False,
        "system": system_instruction,
        "temperature": 0,
        "tools": [],
    }


def parse_ranking(raw_text: str, expected_ids: Iterable[str]) -> list[dict[str, Any]]:
    expected = set(_ids(expected_ids))
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ClaudeContractError("malformed R4 response") from exc
    if not isinstance(payload, dict) or set(payload) != {"candidate_scores"}:
        raise ClaudeContractError("R4 response envelope differs")
    scores = payload["candidate_scores"]
    if not isinstance(scores, dict) or set(scores) != expected:
        raise ClaudeContractError("R4 response candidate set differs")
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 3 for v in scores.values()):
        raise ClaudeContractError("R4 score outside integer 0..3")
    return [
        {"chunk_id": chunk_id, "rank": rank, "score": score}
        for rank, (chunk_id, score) in enumerate(sorted(scores.items(), key=lambda x: (-x[1], x[0])), 1)
    ]


def validate_response(response: Any, expected_ids: Iterable[str]) -> dict[str, Any]:
    raw = response_mapping(response)
    if raw.get("model") != MODEL or raw.get("type") != "message" or raw.get("role") != "assistant":
        raise ClaudeContractError("R4 response envelope/model differs")
    if raw.get("stop_reason") != "end_turn" or raw.get("stop_details") not in (None, {}):
        raise ClaudeContractError("R4 response truncated/refused")
    content = raw.get("content")
    if not isinstance(content, list) or len(content) != 1 or content[0].get("type") != "text":
        raise ClaudeContractError("R4 response content differs")
    return {"raw_response": copy.deepcopy(raw), "ranking": parse_ranking(content[0].get("text", ""), expected_ids), "usage": extract_usage(raw)}
