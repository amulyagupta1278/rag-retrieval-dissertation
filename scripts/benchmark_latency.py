#!/usr/bin/env python3
"""Measure cold-start and steady-state retrieval latency with a fixed protocol."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.bm25_retriever import BM25Retriever
from src.retrievers.faiss_retriever import FAISSRetriever
from src.retrievers.graphrag_retriever import GraphRAGRetriever
from src.utils.io_utils import load_jsonl, load_yaml


DISPLAY = {
    "bm25": "BM25", "faiss": "FAISS",
    "graphrag": "Entity-Co-occurrence Graph Retrieval",
}


def _sync_device() -> None:
    try:
        import torch
        if torch.backends.mps.is_available():
            torch.mps.synchronize()
        elif torch.cuda.is_available():
            torch.cuda.synchronize()
    except (ImportError, RuntimeError):
        pass


def _timed(retriever, question: str, top_k: int) -> float:
    _sync_device()
    start = time.perf_counter_ns()
    retriever.retrieve(question, top_k=top_k)
    _sync_device()
    return (time.perf_counter_ns() - start) / 1_000_000


def _load(system: str, args: argparse.Namespace, config: dict):
    start = time.perf_counter_ns()
    if system == "bm25":
        cfg = config["bm25"]
        retriever = BM25Retriever(cfg.get("k1", 1.5), cfg.get("b", 0.75), args.bm25_index)
    elif system == "faiss":
        cfg = config["faiss"]
        retriever = FAISSRetriever(
            index_dir=args.faiss_index, chunks_path=args.chunks,
            model_name=cfg["model_name"], model_revision=cfg.get("model_revision"),
            similarity_metric=cfg.get("similarity_metric", "l2"),
            normalize_embeddings=cfg.get("normalize_embeddings", False),
            query_prefix=cfg.get("query_prefix", ""), passage_prefix=cfg.get("passage_prefix", ""),
        )
    else:
        cfg = config["graphrag"]
        graph_dir = Path(args.graph_index)
        retriever = GraphRAGRetriever(
            entity_model=cfg.get("entity_model", "en_core_web_sm"),
            max_hop=cfg.get("max_hop", 2), relation_window=cfg.get("relation_window", 2),
            min_entity_freq=cfg.get("min_entity_freq", 2),
            graph_path=graph_dir / "graph.gpickle", nodes_path=graph_dir / "nodes.jsonl",
            edges_path=graph_dir / "edges.jsonl",
        )
    retriever.load_index()
    _sync_device()
    return retriever, (time.perf_counter_ns() - start) / 1_000_000


def _p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)] if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--bm25-index", required=True)
    parser.add_argument("--faiss-index", required=True)
    parser.add_argument("--graph-index", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--warmups", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.warmups < 1 or args.repetitions < 1:
        raise ValueError("warmups and repetitions must be positive")
    qa = load_jsonl(args.qa)
    chunks = load_jsonl(args.chunks)
    config = load_yaml(args.config)
    records: list[dict] = []
    summary: dict[str, dict] = {}
    for system in ("bm25", "faiss", "graphrag"):
        retriever, load_ms = _load(system, args, config)
        cardinality = (
            len(retriever._meta) if system == "bm25" else
            int(retriever.index.ntotal) if system == "faiss" else
            len(retriever._chunk_meta)
        )
        if cardinality != len(chunks):
            raise RuntimeError(f"{system} index cardinality mismatch")
        first_query_ms = _timed(retriever, qa[0]["question"], args.top_k)
        for index in range(args.warmups):
            _timed(retriever, qa[index % len(qa)]["question"], args.top_k)
        values: list[float] = []
        for repetition in range(args.repetitions):
            order = list(qa)
            random.Random(args.seed + repetition).shuffle(order)
            for item in order:
                latency = _timed(retriever, item["question"], args.top_k)
                values.append(latency)
                records.append({
                    "system": system, "query_id": item["question_id"],
                    "repetition": repetition + 1, "latency_ms": latency,
                })
        summary[system] = {
            "display_name": DISPLAY[system], "index_cardinality": cardinality,
            "cold_load_ms": load_ms, "cold_first_query_ms": first_query_ms,
            "warmup_queries_excluded": args.warmups, "timed_repetitions": args.repetitions,
            "timed_observations": len(values), "mean_ms": statistics.mean(values),
            "median_ms": statistics.median(values), "p95_ms": _p95(values),
            "stddev_ms": statistics.pstdev(values),
        }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "latency_observations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("system", "query_id", "repetition", "latency_ms"), lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    report = {
        "protocol": {"warmups": args.warmups, "repetitions": args.repetitions, "seed": args.seed, "top_k": args.top_k},
        "systems": summary,
    }
    (output / "latency_summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
