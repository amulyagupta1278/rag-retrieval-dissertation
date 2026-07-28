"""Frozen-input validation and deterministic 170-item Phase 7 panel construction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SYSTEM_IDS = (
    "bm25",
    "faiss_windowed_max",
    "graph_v3_2",
    "hybrid_rrf",
    "prompt_rag_claude",
)


class Phase7PanelError(ValueError):
    """Raised when a frozen panel input is absent, duplicated, or inconsistent."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise Phase7PanelError(f"malformed JSONL at {path}:{line_n}") from exc
    return rows


def verify_hash(path: Path, expected: str) -> None:
    if sha256_file(path) != expected:
        raise Phase7PanelError(f"hash mismatch: {path}")


def load_questions(path: Path, expected_sha256: str) -> list[dict[str, str]]:
    verify_hash(path, expected_sha256)
    rows = read_jsonl(path)
    questions: list[dict[str, str]] = []
    for row in rows:
        query_id = row.get("query_id", row.get("question_id"))
        question = row.get("question")
        if not isinstance(query_id, str) or not isinstance(question, str) or not question.strip():
            raise Phase7PanelError("invalid query record")
        questions.append({"query_id": query_id, "question": question})
    ids = [row["query_id"] for row in questions]
    if len(ids) != len(set(ids)):
        raise Phase7PanelError("duplicate query ID")
    return sorted(questions, key=lambda row: row["query_id"])


def load_rankings(path: Path, expected_sha256: str, query_ids: set[str]) -> dict[str, list[str]]:
    verify_hash(path, expected_sha256)
    rows = read_jsonl(path)
    output: dict[str, list[str]] = {}
    for row in rows:
        query_id = row.get("query_id")
        if query_id in output:
            raise Phase7PanelError(f"duplicate ranking query: {query_id}")
        ranking = row.get("ranking")
        if not isinstance(query_id, str) or not isinstance(ranking, list):
            raise Phase7PanelError("invalid ranking record")
        chunk_ids = [item.get("chunk_id") for item in ranking]
        if any(not isinstance(chunk_id, str) for chunk_id in chunk_ids):
            raise Phase7PanelError(f"invalid chunk ID for {query_id}")
        if len(chunk_ids) != len(set(chunk_ids)):
            raise Phase7PanelError(f"duplicate chunk ID for {query_id}")
        output[query_id] = chunk_ids
    if set(output) != query_ids:
        raise Phase7PanelError("ranking query coverage mismatch")
    return output


def build_panel(
    questions: Sequence[Mapping[str, str]],
    rankings_by_system: Mapping[str, Mapping[str, Sequence[str]]],
) -> list[dict[str, Any]]:
    """Return one panel record per exact query/system pair."""

    if set(rankings_by_system) != set(SYSTEM_IDS):
        raise Phase7PanelError("missing or unexpected retrieval system")
    query_ids = [row["query_id"] for row in questions]
    if len(query_ids) != len(set(query_ids)):
        raise Phase7PanelError("duplicate query ID")
    panel: list[dict[str, Any]] = []
    for question in sorted(questions, key=lambda row: row["query_id"]):
        query_id = question["query_id"]
        for system_id in SYSTEM_IDS:
            if query_id not in rankings_by_system[system_id]:
                raise Phase7PanelError(f"missing ranking for {query_id}/{system_id}")
            panel.append(
                {
                    "logical_request_id": f"phase7:{query_id}:{system_id}",
                    "query_id": query_id,
                    "retrieval_system": system_id,
                    "question": question["question"],
                    "ranked_chunk_ids": list(rankings_by_system[system_id][query_id]),
                }
            )
    logical_ids = [row["logical_request_id"] for row in panel]
    if len(logical_ids) != len(set(logical_ids)):
        raise Phase7PanelError("duplicate logical request ID")
    return panel

