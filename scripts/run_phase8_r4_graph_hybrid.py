#!/usr/bin/env python3
"""Reindex Phase 8 R4 Graph and build matching R4 Hybrid runs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_phase8_r4_improvements import aggregate, fuse  # noqa: E402
from src.retrievers.fusion import reciprocal_rank_fusion  # noqa: E402
from src.retrievers.graphrag_retriever import GraphRAGRetriever  # noqa: E402


RUN = ROOT / "runs/phase8_r4_improvements"
CHUNKS = RUN / "corpus/chunks_section_aware_450w.jsonl"
QA = RUN / "benchmark/qa_dev_test.jsonl"
SYNTHESIS = RUN / "benchmark/synthesis_candidates_20.jsonl"
CROSSWALK = RUN / "corpus/gold_chunk_crosswalk.jsonl"
BM25 = RUN / "retrieval/bm25_section_aware_run.jsonl"
FAISS = RUN / "retrieval/faiss_cosine/faiss_run.jsonl"
OUT = RUN / "retrieval/graph_hybrid_v4"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in values))


def compact_result(result) -> dict:
    return {
        "chunk_id": result.chunk_id,
        "doc_id": result.doc_id,
        "score": result.score,
        "rank": result.rank,
        "latency_ms": result.latency_ms,
        "retriever": result.retriever,
        "extra": result.extra,
    }


def index(values: list[dict]) -> dict[str, dict]:
    return {row["query_id"]: row for row in values}


def weighted_score(chunk_id: str, component_rows: list[tuple[dict, float]], k: int, graph_only_factor: float) -> float:
    score = 0.0
    memberships = 0
    graph_member = False
    for position, (run, weight) in enumerate(component_rows):
        ranks = {result["chunk_id"]: result["rank"] for result in run["results"][:50]}
        if chunk_id in ranks:
            score += weight / (k + ranks[chunk_id])
            memberships += 1
            graph_member = position == len(component_rows) - 1 or graph_member
    if graph_member and memberships == 1:
        score *= graph_only_factor
    return score


def main() -> int:
    if OUT.exists():
        raise RuntimeError("R4 Graph/Hybrid output exists; refuse overwrite")
    chunks, qa, synthesis, crosswalk = rows(CHUNKS), rows(QA), rows(SYNTHESIS), rows(CROSSWALK)
    mapped: dict[str, set[str]] = {}
    for row in crosswalk:
        mapped.setdefault(row["query_id"], set()).add(row["new_chunk_id"])
    synthesis_gold = {
        row["question_id"]: set().union(*(mapped[qid] for qid in row["component_query_ids"]))
        for row in synthesis
    }
    dev = sorted(row["question_id"] for row in qa if row["split"] == "dev")
    test = sorted(row["question_id"] for row in qa if row["split"] == "test")
    synth_ids = sorted(synthesis_gold)

    retriever = GraphRAGRetriever(
        entity_model="en_core_web_sm",
        max_hop=2,
        relation_window=2,
        min_entity_freq=2,
        graph_path=OUT / "index/graph.gpickle",
        nodes_path=OUT / "index/nodes.jsonl",
        edges_path=OUT / "index/edges.jsonl",
        chunks_path=CHUNKS,
        seed_filtering=True,
        use_aliases=True,
        hub_penalty=True,
        dual_entity_coverage=True,
        lexical_fallback=True,
        max_seeds=5,
        hop_decay=0.5,
    )
    retriever.build_index(chunks)
    write_json(
        OUT / "retrieval_config.json",
        {
            "dual_entity_coverage": True,
            "entity_model": "en_core_web_sm",
            "hop_decay": 0.5,
            "hub_penalty": True,
            "lexical_fallback": True,
            "max_hop": 2,
            "max_seeds": 5,
            "min_entity_freq": 2,
            "relation_window": 2,
            "seed_filtering": True,
            "use_aliases": True,
        },
    )
    graph_rows, traces, graph_rankings = [], [], {}
    for row in [*qa, *synthesis]:
        query_id, question = row["question_id"], row["question"]
        results = retriever.retrieve(question, top_k=50)
        graph_rankings[query_id] = [result.chunk_id for result in results]
        graph_rows.append({
            "query_id": query_id,
            "query_text": question,
            "retriever": "graph_v4_section_aware",
            "top_k": 50,
            "results": [compact_result(result) for result in results],
            "config_snapshot": {
                "max_hop": 2,
                "min_entity_freq": 2,
                "seed_filtering": True,
                "use_aliases": True,
                "hub_penalty": True,
                "dual_entity_coverage": True,
                "lexical_fallback": True,
                "max_seeds": 5,
                "hop_decay": 0.5,
            },
        })
        traces.append({"query_id": query_id, **retriever.last_trace})
    write_jsonl(OUT / "graph_run.jsonl", graph_rows)
    write_jsonl(OUT / "graph_traces.jsonl", traces)

    bm25_rows, faiss_rows = rows(BM25), rows(FAISS)
    bm25, faiss, graph = index(bm25_rows), index(faiss_rows), index(graph_rows)
    equal_hybrid_rows = reciprocal_rank_fusion(
        {"bm25_r4": bm25_rows, "graph_v4": graph_rows},
        rrf_k=60,
        input_depth=50,
        output_depth=50,
    )
    equal_rankings = {row["query_id"]: [result["chunk_id"] for result in row["results"]] for row in equal_hybrid_rows}

    candidates = []
    all_ids = sorted(bm25)
    for k in (10, 30, 60):
        for faiss_weight in (0.1, 0.25, 0.5):
            for graph_weight in (0.05, 0.1, 0.25):
                for graph_only_factor in (0.0, 0.1):
                    rankings = {
                        qid: fuse(
                            [(bm25[qid], 1.0), (faiss[qid], faiss_weight), (graph[qid], graph_weight)],
                            k,
                            graph_only_factor=graph_only_factor,
                        )
                        for qid in all_ids
                    }
                    candidates.append({
                        "k": k,
                        "faiss_weight": faiss_weight,
                        "graph_weight": graph_weight,
                        "graph_only_factor": graph_only_factor,
                        "dev": aggregate(rankings, mapped, dev),
                        "rankings": rankings,
                    })
    best = max(
        candidates,
        key=lambda row: (
            row["dev"]["ndcg@10"],
            row["dev"]["mrr@10"],
            -row["graph_weight"],
            -row["faiss_weight"],
            -row["graph_only_factor"],
        ),
    )
    chunk_by_id = {row["chunk_id"]: row for row in chunks}
    improved_rows = []
    for qid in all_ids:
        question = bm25[qid]["query_text"]
        components = [(bm25[qid], 1.0), (faiss[qid], best["faiss_weight"]), (graph[qid], best["graph_weight"])]
        improved_rows.append({
            "query_id": qid,
            "query_text": question,
            "retriever": "hybrid_r4_weighted",
            "top_k": 50,
            "results": [
                {
                    "chunk_id": chunk_id,
                    "doc_id": chunk_by_id[chunk_id]["doc_id"],
                    "score": weighted_score(chunk_id, components, best["k"], best["graph_only_factor"]),
                    "rank": rank,
                    "latency_ms": 0.0,
                    "retriever": "hybrid_r4_weighted",
                }
                for rank, chunk_id in enumerate(best["rankings"][qid], 1)
            ],
            "config_snapshot": {key: best[key] for key in ("k", "faiss_weight", "graph_weight", "graph_only_factor")},
        })
    write_jsonl(OUT / "hybrid_equal_bm25_graph_run.jsonl", equal_hybrid_rows)
    write_jsonl(OUT / "hybrid_weighted_run.jsonl", improved_rows)

    metrics = {
        "status": "offline_automatic_candidate_pending_human_validation",
        "graph": {
            "dev": aggregate(graph_rankings, mapped, dev),
            "test": aggregate(graph_rankings, mapped, test),
            "synthesis_candidate_metrics": aggregate(graph_rankings, synthesis_gold, synth_ids),
            "empty_result_query_n": sum(not values for values in graph_rankings.values()),
        },
        "hybrid_equal_bm25_graph": {
            "config": {"systems": ["bm25_r4", "graph_v4"], "rrf_k": 60},
            "dev": aggregate(equal_rankings, mapped, dev),
            "test": aggregate(equal_rankings, mapped, test),
            "synthesis_candidate_metrics": aggregate(equal_rankings, synthesis_gold, synth_ids),
        },
        "hybrid_weighted_bm25_faiss_graph": {
            "selection": {key: best[key] for key in ("k", "faiss_weight", "graph_weight", "graph_only_factor", "dev")},
            "test": aggregate(best["rankings"], mapped, test),
            "synthesis_candidate_metrics": aggregate(best["rankings"], synthesis_gold, synth_ids),
        },
        "selection_policy": "Weights selected on 60-query dev split only; 40-query test remained untouched until selection.",
        "warning": "R4 qrel crosswalk and synthesis candidates remain automatic pending human validation.",
    }
    write_json(OUT / "metrics.json", metrics)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
