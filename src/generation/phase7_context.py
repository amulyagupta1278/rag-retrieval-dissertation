"""Deterministic, provider-neutral Phase 7 context serialization."""

from __future__ import annotations

import json
from typing import Iterable, Mapping, Sequence


ALLOWED_CONTEXT_DEPTHS = {3, 5, 10}


class Phase7ContextError(ValueError):
    """Raised when context inputs violate frozen structural contracts."""


def serialize_context(
    question: str,
    ranked_chunk_ids: Sequence[str],
    chunk_text_by_id: Mapping[str, str],
    context_depth: int,
) -> tuple[str, dict[str, str]]:
    """Serialize question and evidence without system identity, scores, or labels."""

    if context_depth not in ALLOWED_CONTEXT_DEPTHS:
        raise Phase7ContextError("context depth must be one of 3, 5, or 10")
    if not isinstance(question, str) or not question.strip():
        raise Phase7ContextError("question must be non-empty text")
    selected = list(ranked_chunk_ids[:context_depth])
    if len(selected) != len(set(selected)):
        raise Phase7ContextError("duplicate chunk ID in selected context")
    evidence: list[dict[str, str]] = []
    mapping: dict[str, str] = {}
    for index, chunk_id in enumerate(selected, start=1):
        if chunk_id not in chunk_text_by_id:
            raise Phase7ContextError(f"unknown chunk ID: {chunk_id}")
        evidence_id = f"E{index:02d}"
        mapping[evidence_id] = chunk_id
        evidence.append({"evidence_id": evidence_id, "text": chunk_text_by_id[chunk_id]})
    payload = {"question": question, "evidence": evidence}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), mapping


def evidence_ids(context_depth: int, available_n: int) -> set[str]:
    """Return legal anonymized citation IDs for a serialized context."""

    if context_depth not in ALLOWED_CONTEXT_DEPTHS:
        raise Phase7ContextError("context depth must be one of 3, 5, or 10")
    return {f"E{index:02d}" for index in range(1, min(context_depth, available_n) + 1)}

