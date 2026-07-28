"""Deterministic equal-weight RRF for frozen BM25 and Entity Graph v3.2 rankings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


COMPONENTS = ("bm25", "entity_graph_v3_2")
EXPECTED_CONFIG = {
    "system": "hybrid_bm25_graph_rrf",
    "components": ["bm25", "entity_graph_v3_2"],
    "rrf_k": 60,
    "weights": {"bm25": 1.0, "entity_graph_v3_2": 1.0},
    "input_depth": 50,
    "output_depth": 50,
    "rank_origin": 1,
    "tie_break": "score descending then chunk ID ascending",
    "missing_component_policy": "use available component contribution",
    "duplicate_chunk_policy": "one contribution per system",
    "status": "frozen_before_hybrid_results",
}


def validate_config(config: Mapping[str, Any]) -> None:
    """Reject any deviation from preregistered primary RRF configuration."""
    if dict(config) != EXPECTED_CONFIG:
        raise ValueError("Hybrid RRF configuration differs from frozen v1 specification")


def validate_component_names(names: Sequence[str]) -> None:
    """Allow only BM25 plus corrected Entity Graph v3.2."""
    if tuple(names) != COMPONENTS:
        raise ValueError(f"components must be exactly {COMPONENTS}; got {tuple(names)}")


def validate_ranking(
    ranking: Sequence[Mapping[str, Any]], *, component: str, known_chunk_ids: set[str], input_depth: int,
) -> None:
    """Validate one component ranking; empty Graph or BM25 results remain valid."""
    if component not in COMPONENTS:
        raise ValueError(f"unsupported Hybrid component: {component}")
    if input_depth != 50:
        raise ValueError("input depth is frozen at 50")
    if len(ranking) > input_depth:
        raise ValueError(f"{component} ranking exceeds input depth 50")
    chunk_ids = [str(row.get("chunk_id", "")) for row in ranking]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError(f"duplicate chunk in {component} ranking")
    if any(chunk_id not in known_chunk_ids for chunk_id in chunk_ids):
        unknown = sorted(set(chunk_ids) - known_chunk_ids)
        raise ValueError(f"unknown chunk in {component} ranking: {unknown}")
    ranks = [row.get("rank") for row in ranking]
    if ranks != list(range(1, len(ranking) + 1)):
        raise ValueError(f"{component} ranks must be one-based and contiguous")


def validate_query_rows(
    rows: Sequence[Mapping[str, Any]], *, component: str, known_chunk_ids: set[str], expected_query_ids: set[str],
) -> dict[str, list[dict[str, Any]]]:
    """Validate query set and return deterministic query-to-ranking mapping."""
    query_ids = [str(row.get("query_id", "")) for row in rows]
    if len(query_ids) != len(set(query_ids)):
        raise ValueError(f"duplicate query in {component} rankings")
    if set(query_ids) != expected_query_ids:
        raise ValueError(f"{component} query-ID set differs from frozen R5 set")
    output: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        query_id = str(row["query_id"])
        ranking = [dict(item) for item in row.get("ranking", [])]
        validate_ranking(ranking, component=component, known_chunk_ids=known_chunk_ids, input_depth=50)
        output[query_id] = ranking
    return output


def fuse_rankings(
    bm25: Sequence[Mapping[str, Any]], graph: Sequence[Mapping[str, Any]],
    *, config: Mapping[str, Any], known_chunk_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fuse two validated rankings using rank-only Reciprocal Rank Fusion."""
    validate_config(config)
    validate_component_names(config["components"])
    validate_ranking(bm25, component="bm25", known_chunk_ids=known_chunk_ids, input_depth=config["input_depth"])
    validate_ranking(graph, component="entity_graph_v3_2", known_chunk_ids=known_chunk_ids, input_depth=config["input_depth"])
    ranks = {
        "bm25": {str(row["chunk_id"]): int(row["rank"]) for row in bm25},
        "entity_graph_v3_2": {str(row["chunk_id"]): int(row["rank"]) for row in graph},
    }
    k = int(config["rrf_k"])
    scores: dict[str, tuple[float, float, float]] = {}
    for chunk_id in sorted(set(ranks["bm25"]) | set(ranks["entity_graph_v3_2"])):
        bm25_contribution = 1.0 / (k + ranks["bm25"][chunk_id]) if chunk_id in ranks["bm25"] else 0.0
        graph_contribution = 1.0 / (k + ranks["entity_graph_v3_2"][chunk_id]) if chunk_id in ranks["entity_graph_v3_2"] else 0.0
        scores[chunk_id] = (bm25_contribution + graph_contribution, bm25_contribution, graph_contribution)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id][0], chunk_id))[: config["output_depth"]]
    score_groups: dict[float, list[str]] = {}
    for chunk_id in ordered:
        score_groups.setdefault(scores[chunk_id][0], []).append(chunk_id)
    ranking = [
        {"chunk_id": chunk_id, "rank": rank, "score": scores[chunk_id][0]}
        for rank, chunk_id in enumerate(ordered, 1)
    ]
    trace = []
    for rank, chunk_id in enumerate(ordered, 1):
        total, bm25_contribution, graph_contribution = scores[chunk_id]
        tied = sorted(score_groups[total])
        trace.append({
            "chunk_id": chunk_id,
            "bm25_rank": ranks["bm25"].get(chunk_id),
            "graph_rank": ranks["entity_graph_v3_2"].get(chunk_id),
            "bm25_rrf_contribution": bm25_contribution,
            "graph_rrf_contribution": graph_contribution,
            "total_rrf_score": total,
            "final_hybrid_rank": rank,
            "tie_break": "chunk_id_ascending" if len(tied) > 1 else "not_required",
            "tied_chunk_ids": tied,
        })
    return ranking, trace
