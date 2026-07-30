"""Cost-adapted Phase 8 Prompt-RAG contract over frozen BM25 top 10."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterable, Mapping
from typing import Any

from src.retrievers.prompt_rag_claude_v2 import (
    MODEL,
    ClaudeContractError,
    extract_usage,
    response_mapping,
)
from src.utils.atomic_io import stable_json


CANDIDATE_N = 10
MAX_OUTPUT_TOKENS = 512


def build_response_schema(chunk_ids: Iterable[str]) -> dict[str, Any]:
    values = sorted(chunk_ids)
    if len(values) != CANDIDATE_N or len(set(values)) != CANDIDATE_N:
        raise ClaudeContractError("Phase 8 top-10 schema requires 10 unique chunk IDs")
    return {
        "additionalProperties": False,
        "properties": {"candidate_scores": {
            "additionalProperties": False,
            "properties": {chunk_id: {"type": "integer"} for chunk_id in values},
            "required": values,
            "type": "object",
        }},
        "required": ["candidate_scores"],
        "type": "object",
    }


def build_request(*, query: Mapping[str, str], candidates: Iterable[Mapping[str, str]], system_instruction: str) -> dict[str, Any]:
    rows = [dict(row) for row in candidates]
    if set(query) != {"query_id", "question"} or not all(query.values()):
        raise ClaudeContractError("query contract differs")
    if len(rows) != CANDIDATE_N or any(set(row) != {"chunk_id", "text"} for row in rows):
        raise ClaudeContractError("exactly 10 chunk_id/text candidates required")
    chunk_ids = [row["chunk_id"] for row in rows]
    if len(set(chunk_ids)) != CANDIDATE_N or any(not row["text"].strip() for row in rows):
        raise ClaudeContractError("candidate IDs/text invalid")
    content = stable_json({"candidates": rows, **dict(query)})
    return {
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{"content": content, "role": "user"}],
        "model": MODEL,
        "output_config": {"format": {"schema": build_response_schema(chunk_ids), "type": "json_schema"}},
        "service_tier": "standard_only",
        "stream": False,
        "system": system_instruction,
        "temperature": 0,
        "tools": [],
    }


def parse_ranking(raw_text: str, expected_ids: Iterable[str]) -> list[dict[str, Any]]:
    expected = set(expected_ids)
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ClaudeContractError("malformed top-10 response") from exc
    if not isinstance(payload, dict) or set(payload) != {"candidate_scores"}:
        raise ClaudeContractError("response must contain only candidate_scores")
    scores = payload["candidate_scores"]
    if not isinstance(scores, dict) or set(scores) != expected:
        raise ClaudeContractError("response candidate set differs")
    if any(isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 3 for score in scores.values()):
        raise ClaudeContractError("candidate score outside integer 0..3")
    return [
        {"chunk_id": chunk_id, "rank": rank, "score": score}
        for rank, (chunk_id, score) in enumerate(sorted(scores.items(), key=lambda row: (-row[1], row[0])), 1)
    ]


def validate_response(response: Any, expected_ids: Iterable[str]) -> dict[str, Any]:
    raw = response_mapping(response)
    if raw.get("model") != MODEL or raw.get("type") != "message" or raw.get("role") != "assistant":
        raise ClaudeContractError("response envelope/model differs")
    if raw.get("stop_reason") != "end_turn" or raw.get("stop_details") not in (None, {}):
        raise ClaudeContractError("response truncated/refused")
    content = raw.get("content")
    if not isinstance(content, list) or len(content) != 1 or content[0].get("type") != "text":
        raise ClaudeContractError("response content differs")
    usage = extract_usage(raw)
    return {
        "raw_response": copy.deepcopy(raw),
        "ranking": parse_ranking(content[0].get("text", ""), expected_ids),
        "usage": usage,
    }
