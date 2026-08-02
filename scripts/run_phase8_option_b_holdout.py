#!/usr/bin/env python3
"""Run frozen Phase 8 Option B holdout through four local retrieval systems."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from src.retrievers.bm25_retriever import BM25Retriever  # noqa: E402
from src.retrievers.graphrag_retriever import GraphRAGRetriever  # noqa: E402

BASE = ROOT / "runs/phase8_option_b_holdout"
FREEZE = BASE / "freeze"
OUT = BASE / "retrieval"
R4 = ROOT / "runs/phase8_r4_improvements"
CHUNKS = R4 / "corpus/chunks_section_aware_450w.jsonl"
QA = FREEZE / "qa_holdout_12.jsonl"
QRELS = FREEZE / "qrels_holdout_12.tsv"
FAISS_INDEX = R4 / "retrieval/faiss_cosine/index"
EMBED_SCRIPT = ROOT / "scripts/embed_phase8_option_b_holdout.py"
FAISS_SEARCH_SCRIPT = ROOT / "scripts/search_phase8_option_b_holdout_faiss.py"
GRAPH_INDEX = R4 / "retrieval/graph_hybrid_v4/index"
BM25_INDEX = OUT / "bm25/index/bm25_r4_holdout.pkl"
HYBRID_CONFIG = {"k": 10, "bm25_weight": 1.0, "faiss_weight": 0.25, "graph_weight": 0.1, "graph_only_factor": 0.0}


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, values: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in values), encoding="utf-8")


def qrels() -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for line in QRELS.read_text(encoding="utf-8").splitlines():
        query_id, _, chunk_id, relevance = line.split("\t")
        if int(relevance) > 0:
            result.setdefault(query_id, set()).add(chunk_id)
    return result


def compact(result) -> dict:
    return {
        "chunk_id": result.chunk_id,
        "doc_id": result.doc_id,
        "latency_ms": result.latency_ms,
        "rank": result.rank,
        "retriever": result.retriever,
        "score": result.score,
    }


def metrics(ranking: list[str], gold: set[str], k: int = 10) -> dict[str, float]:
    top = ranking[:k]
    relevant_ranks = [rank for rank, chunk_id in enumerate(top, 1) if chunk_id in gold]
    mrr = 1.0 / relevant_ranks[0] if relevant_ranks else 0.0
    recall = len(relevant_ranks) / len(gold) if gold else 0.0
    precision = len(relevant_ranks) / k
    dcg = sum(1.0 / math.log2(rank + 1) for rank in relevant_ranks)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), k) + 1))
    return {
        "hit@10": float(bool(relevant_ranks)),
        "mrr@10": mrr,
        "ndcg@10": dcg / ideal if ideal else 0.0,
        "precision@10": precision,
        "recall@10": recall,
    }


def aggregate(per_query: list[dict]) -> dict[str, float]:
    keys = ["mrr@10", "recall@10", "precision@10", "ndcg@10", "hit@10"]
    return {key: sum(row[key] for row in per_query) / len(per_query) for key in keys}


def weighted_hybrid(component_rows: list[tuple[dict, float]], chunk_by_id: dict[str, dict]) -> list[dict]:
    scores: dict[str, float] = {}
    memberships: dict[str, int] = {}
    graph_members: set[str] = set()
    for component_index, (run, weight) in enumerate(component_rows):
        for result in run["results"][:50]:
            chunk_id = result["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (HYBRID_CONFIG["k"] + result["rank"])
            memberships[chunk_id] = memberships.get(chunk_id, 0) + 1
            if component_index == len(component_rows) - 1:
                graph_members.add(chunk_id)
    for chunk_id in graph_members:
        if memberships[chunk_id] == 1:
            scores[chunk_id] *= HYBRID_CONFIG["graph_only_factor"]
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))[:50]
    return [
        {
            "chunk_id": chunk_id,
            "doc_id": chunk_by_id[chunk_id]["doc_id"],
            "latency_ms": 0.0,
            "rank": rank,
            "retriever": "hybrid_r4_weighted_frozen",
            "score": scores[chunk_id],
        }
        for rank, chunk_id in enumerate(ordered, 1)
    ]


def main() -> int:
    execution_manifest = OUT / "execution_manifest.json"
    if execution_manifest.exists():
        raise RuntimeError(f"Completed holdout output exists; refuse overwrite: {OUT}")
    if OUT.exists():
        allowed_partial = {
            BM25_INDEX,
            BM25_INDEX.with_suffix(BM25_INDEX.suffix + ".config.json"),
            OUT / "faiss_cosine/query_embeddings.npy",
            OUT / "faiss_cosine/query_embeddings_manifest.json",
            OUT / "faiss_cosine/run.jsonl",
        }
        unexpected = [
            path for path in OUT.rglob("*")
            if path.is_file() and path not in allowed_partial
        ]
        if unexpected:
            raise RuntimeError(f"Unexpected partial holdout outputs; refuse resume: {unexpected}")
    manifest = json.loads((FREEZE / "freeze_manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "owner_approved_frozen_ready_for_single_execution":
        raise RuntimeError("Freeze status does not authorize execution")
    if sha(QA) != manifest["outputs"]["qa_holdout_sha256"] or sha(QRELS) != manifest["outputs"]["qrels_holdout_sha256"]:
        raise RuntimeError("Frozen QA/qrels hash mismatch")

    chunks = rows(CHUNKS)
    questions = rows(QA)
    gold = qrels()
    chunk_by_id = {row["chunk_id"]: row for row in chunks}
    OUT.mkdir(parents=True, exist_ok=True)

    bm25 = BM25Retriever(k1=1.2, b=0.75, index_path=BM25_INDEX, chunks_path=CHUNKS)
    bm25.build_index(chunks)

    subprocess.run([sys.executable, str(EMBED_SCRIPT)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(FAISS_SEARCH_SCRIPT)], cwd=ROOT, check=True)

    graph = GraphRAGRetriever(
        entity_model="en_core_web_sm",
        max_hop=2,
        relation_window=2,
        min_entity_freq=2,
        graph_path=GRAPH_INDEX / "graph.gpickle",
        nodes_path=GRAPH_INDEX / "nodes.jsonl",
        edges_path=GRAPH_INDEX / "edges.jsonl",
        chunks_path=CHUNKS,
        seed_filtering=True,
        use_aliases=True,
        hub_penalty=True,
        dual_entity_coverage=True,
        lexical_fallback=True,
        max_seeds=5,
        hop_decay=0.5,
    )
    graph.load_index()
    graph.validate_provenance(chunks, require_complete=True)

    runs: dict[str, list[dict]] = {"bm25": [], "faiss_cosine": rows(OUT / "faiss_cosine/run.jsonl"), "graph_v4": []}
    for question in questions:
        for system, retriever in (("bm25", bm25), ("graph_v4", graph)):
            started = time.perf_counter()
            results = retriever.retrieve(question["question"], top_k=50)
            elapsed = time.perf_counter() - started
            runs[system].append({
                "query_id": question["question_id"],
                "query_text": question["question"],
                "retriever": system,
                "top_k": 50,
                "latency_seconds": elapsed,
                "results": [compact(result) for result in results],
            })

    indexed = {system: {row["query_id"]: row for row in values} for system, values in runs.items()}
    hybrid_rows = []
    for question in questions:
        qid = question["question_id"]
        results = weighted_hybrid([
            (indexed["bm25"][qid], HYBRID_CONFIG["bm25_weight"]),
            (indexed["faiss_cosine"][qid], HYBRID_CONFIG["faiss_weight"]),
            (indexed["graph_v4"][qid], HYBRID_CONFIG["graph_weight"]),
        ], chunk_by_id)
        hybrid_rows.append({
            "query_id": qid,
            "query_text": question["question"],
            "retriever": "hybrid_r4",
            "top_k": 50,
            "latency_seconds": 0.0,
            "results": results,
            "config_snapshot": HYBRID_CONFIG,
        })
    runs["hybrid_r4"] = hybrid_rows

    all_metrics = {}
    per_query_rows = []
    question_by_id = {row["question_id"]: row for row in questions}
    for system, values in runs.items():
        write_jsonl(OUT / system / "run.jsonl", values)
        system_metrics = []
        for row in values:
            scores = metrics([result["chunk_id"] for result in row["results"]], gold[row["query_id"]])
            item = {
                "category": question_by_id[row["query_id"]]["category"],
                "query_id": row["query_id"],
                "system": system,
                **scores,
            }
            system_metrics.append(item)
            per_query_rows.append(item)
        all_metrics[system] = aggregate(system_metrics)

    write_jsonl(OUT / "per_query.jsonl", per_query_rows)
    write_json(OUT / "metrics.json", {
        "benchmark": "phase8_option_b_holdout_v1",
        "metrics": all_metrics,
        "query_n": len(questions),
        "status": "four_local_systems_complete_prompt_rag_pending",
    })
    outputs = {str(path.relative_to(ROOT)): sha(path) for path in sorted(OUT.rglob("*")) if path.is_file()}
    write_json(OUT / "execution_manifest.json", {
        "benchmark": "phase8_option_b_holdout_v1",
        "frozen_inputs": {
            "freeze_manifest": sha(FREEZE / "freeze_manifest.json"),
            "qa": sha(QA),
            "qrels": sha(QRELS),
            "chunks": sha(CHUNKS),
        },
        "hybrid_config": HYBRID_CONFIG,
        "outputs_before_manifest": outputs,
        "status": "four_local_systems_complete_prompt_rag_pending",
    })
    print(json.dumps(all_metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
