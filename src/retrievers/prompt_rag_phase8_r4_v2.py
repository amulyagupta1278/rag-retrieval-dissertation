"""Phase 8 R4 V2 recovery contract: V1 unchanged except 1024 output tokens."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from src.retrievers.prompt_rag_phase8_r4 import (
    build_request as _build_v1_request,
    validate_response,
)

MAX_OUTPUT_TOKENS = 1024


def build_request(*, query: Mapping[str, str], candidates: Iterable[Mapping[str, str]], system_instruction: str) -> dict[str, Any]:
    request = _build_v1_request(query=query, candidates=candidates, system_instruction=system_instruction)
    request["max_tokens"] = MAX_OUTPUT_TOKENS
    return request


__all__ = ["MAX_OUTPUT_TOKENS", "build_request", "validate_response"]
