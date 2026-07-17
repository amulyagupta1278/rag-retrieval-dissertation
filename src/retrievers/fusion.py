"""Deterministic equal-weight Reciprocal Rank Fusion."""

from __future__ import annotations


def reciprocal_rank_fusion(
    runs_by_system: dict[str, list[dict]], *, rrf_k: int = 60,
    input_depth: int = 50, output_depth: int = 50,
) -> list[dict]:
    if len(runs_by_system) < 2:
        raise ValueError("RRF requires at least two component systems")
    indexed = {
        system: {run["query_id"]: run for run in runs}
        for system, runs in runs_by_system.items()
    }
    query_sets = [set(runs) for runs in indexed.values()]
    if any(values != query_sets[0] for values in query_sets[1:]):
        raise ValueError("RRF component runs must cover identical query IDs")
    fused_runs: list[dict] = []
    for query_id in sorted(query_sets[0]):
        scores: dict[str, float] = {}
        representatives: dict[str, dict] = {}
        contributions: dict[str, dict[str, int]] = {}
        question = ""
        for system in sorted(indexed):
            run = indexed[system][query_id]
            question = question or run.get("question", "")
            for rank, result in enumerate(run.get("results", [])[:input_depth], 1):
                chunk_id = result["chunk_id"]
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
                contributions.setdefault(chunk_id, {})[system] = rank
                representatives.setdefault(chunk_id, result)
        ranked = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:output_depth]
        results = []
        for rank, chunk_id in enumerate(ranked, 1):
            source = representatives[chunk_id]
            results.append({
                **source, "chunk_id": chunk_id, "rank": rank, "score": scores[chunk_id],
                "retriever": "rrf", "latency_ms": 0.0,
                "extra": {"component_ranks": contributions[chunk_id], "rrf_k": rrf_k},
            })
        fused_runs.append({
            "query_id": query_id, "question": question, "retriever": "rrf",
            "top_k": output_depth, "total_latency_ms": sum(
                float(indexed[system][query_id].get("total_latency_ms", 0.0)) for system in indexed
            ),
            "results": results,
            "config": {"systems": sorted(indexed), "rrf_k": rrf_k, "input_depth": input_depth},
        })
    return fused_runs
