"""Phase 8 R4 generation validation with frozen 1024-token V2 ceiling."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from src.generation import phase7_freeze as v1
from src.generation.phase7_v2_freeze import MODEL

MAX_OUTPUT_TOKENS = 1024


def validate_provider_response(response: Any, *, available_evidence_ids: Iterable[str]) -> dict[str, Any]:
    if not isinstance(response, Mapping) or not isinstance(response.get("id"), str) or not response["id"]:
        raise v1.Phase7ExecutionFailure("missing_response")
    if response.get("model") != MODEL:
        raise v1.Phase7ExecutionFailure("model_drift")
    usage = response.get("usage")
    if not isinstance(usage, Mapping) or not {"input_tokens", "output_tokens"}.issubset(usage):
        raise v1.Phase7ExecutionFailure("missing_usage")
    input_tokens, output_tokens = usage["input_tokens"], usage["output_tokens"]
    if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in (input_tokens, output_tokens)) or output_tokens > MAX_OUTPUT_TOKENS:
        raise v1.Phase7ExecutionFailure("missing_usage")
    if int(usage.get("cache_creation_input_tokens") or 0) or int(usage.get("cache_read_input_tokens") or 0):
        raise v1.Phase7ExecutionFailure("cost_cap_breach")
    if response.get("stop_reason") == "max_tokens":
        raise v1.Phase7ExecutionFailure("truncation")
    if response.get("stop_reason") != "end_turn":
        raise v1.Phase7ExecutionFailure("missing_response")
    content = response.get("content")
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], Mapping) or content[0].get("type") != "text":
        raise v1.Phase7ExecutionFailure("missing_response")
    try:
        payload = json.loads(content[0].get("text", ""))
    except json.JSONDecodeError as exc:
        raise v1.Phase7ExecutionFailure("malformed_response") from exc
    return {
        "answer": v1.validate_answer_payload(payload, available_evidence_ids=available_evidence_ids),
        "model": response["model"], "response_id": response["id"],
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }
