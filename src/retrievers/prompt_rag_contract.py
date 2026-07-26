"""Architecture-neutral safety contract for a prospective Prompt-RAG reranker.

This module performs no retrieval and makes no network calls.  It exists so the
Phase 5A leakage, parsing, failure, and deterministic-order rules can be tested
before an owner selects and freezes an executable architecture.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from typing import Any


ALLOWED_QUERY_FIELDS = frozenset({"query_id", "question"})
ALLOWED_CANDIDATE_FIELDS = frozenset({"chunk_id", "text", "source_title"})
FORBIDDEN_INPUT_FIELDS = frozenset(
    {
        "answer",
        "category",
        "gold_chunk_ids",
        "gold_evidence",
        "metrics",
        "owner_judgment",
        "owner_judgments",
        "qrel",
        "qrels",
        "reference_answer",
        "relevance",
        "relevance_judgment",
        "sealed_provenance",
        "system",
    }
)


def _validate_exposed_fields(
    record: Mapping[str, Any], *, allowed: frozenset[str], record_name: str
) -> None:
    """Reject hidden-gold fields and every field outside the explicit allowlist."""

    keys = set(record)
    forbidden = sorted(keys & FORBIDDEN_INPUT_FIELDS)
    if forbidden:
        raise ValueError(f"{record_name} contains forbidden fields: {forbidden}")
    unexpected = sorted(keys - allowed)
    if unexpected:
        raise ValueError(f"{record_name} contains non-allowlisted fields: {unexpected}")


def validate_model_inputs(
    query: Mapping[str, Any], candidates: Iterable[Mapping[str, Any]]
) -> None:
    """Validate the only query and chunk fields that a future model may receive."""

    _validate_exposed_fields(query, allowed=ALLOWED_QUERY_FIELDS, record_name="query")
    if not isinstance(query.get("query_id"), str) or not query["query_id"].strip():
        raise ValueError("query_id must be a non-empty string")
    if not isinstance(query.get("question"), str) or not query["question"].strip():
        raise ValueError("question must be a non-empty string")

    seen: set[str] = set()
    candidate_count = 0
    for index, candidate in enumerate(candidates):
        candidate_count += 1
        _validate_exposed_fields(
            candidate,
            allowed=ALLOWED_CANDIDATE_FIELDS,
            record_name=f"candidate[{index}]",
        )
        chunk_id = candidate.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError(f"candidate[{index}] chunk_id must be a non-empty string")
        if chunk_id in seen:
            raise ValueError(f"duplicate candidate chunk_id: {chunk_id}")
        seen.add(chunk_id)
        if not isinstance(candidate.get("text"), str) or not candidate["text"].strip():
            raise ValueError(f"candidate[{index}] text must be a non-empty string")
        if not isinstance(candidate.get("source_title"), str):
            raise ValueError(f"candidate[{index}] source_title must be a string")
    if candidate_count == 0:
        raise ValueError("candidate set must not be empty")


def parse_and_rank_response(raw_response: str, expected_chunk_ids: Iterable[str]) -> list[dict[str, Any]]:
    """Strictly parse candidate scores and rank by score then ascending chunk ID.

    Missing, extra, duplicate, malformed, or non-finite scores are failures.  The
    function intentionally has no fallback path.
    """

    expected = list(expected_chunk_ids)
    if not expected:
        raise ValueError("expected candidate set must not be empty")
    if len(expected) != len(set(expected)):
        raise ValueError("expected candidate IDs contain duplicates")

    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON response: {exc.msg}") from exc
    if not isinstance(payload, dict) or set(payload) != {"candidate_scores"}:
        raise ValueError("response must contain only candidate_scores")
    rows = payload["candidate_scores"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("candidate_scores must be a non-empty array")

    scores: dict[str, float] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != {"chunk_id", "score"}:
            raise ValueError(f"candidate_scores[{index}] must contain only chunk_id and score")
        chunk_id = row["chunk_id"]
        score = row["score"]
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ValueError(f"candidate_scores[{index}] chunk_id must be a non-empty string")
        if chunk_id in scores:
            raise ValueError(f"duplicate response chunk_id: {chunk_id}")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"candidate_scores[{index}] score must be numeric")
        numeric_score = float(score)
        if not math.isfinite(numeric_score):
            raise ValueError(f"candidate_scores[{index}] score must be finite")
        scores[chunk_id] = numeric_score

    expected_set = set(expected)
    actual_set = set(scores)
    if actual_set != expected_set:
        missing = sorted(expected_set - actual_set)
        extra = sorted(actual_set - expected_set)
        raise ValueError(f"response candidate set mismatch; missing={missing}, extra={extra}")

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"chunk_id": chunk_id, "score": score, "rank": rank}
        for rank, (chunk_id, score) in enumerate(ordered, start=1)
    ]
