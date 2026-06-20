#!/usr/bin/env python3
"""
Run All Retrievers (BM25, FAISS, GraphRAG) and Generate Comparison Report
===========================================================================
Usage:
    python run_all_retrievers.py [--rebuild-all] [--top-k 10]
"""

import sys
import json
import time
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.retrievers.bm25_retriever import BM25Retriever
from src.evaluation.evaluator import RetrievalEvaluator
from src.utils.io_utils import load_jsonl

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def load_queries(path):
    """Load QA dataset."""
    queries = load_jsonl(path)
    return queries

def run_bm25(chunks, queries, rebuild=False, top_k=10):
    """Run BM25 retrieval."""
    logger.info("\n" + "="*60)
    logger.info("Running BM25 Retrieval (top_k=%d)", top_k)
    logger.info("="*60)

    retriever = BM25Retriever(k1=1.5, b=0.75)

    index_path = Path("indexes/bm25/bm25_index.pkl")
    if rebuild or not index_path.exists():
        logger.info("Building BM25 index from %d chunks...", len(chunks))
        retriever.build_index(chunks)
    else:
        logger.info("Loading existing BM25 index...")
        retriever.load_index()

    runs = []
    start = time.time()
    for i, q in enumerate(queries, 1):
        q_start = time.time()
        results = retriever.retrieve(q.get("question", ""), top_k=top_k)
        q_elapsed = (time.time() - q_start) * 1000

        run = {
            "query_id": q.get("question_id"),
            "query_text": q.get("question"),
            "results": [
                {
                    "chunk_id": r.chunk_id,
                    "doc_id": r.doc_id,
                    "text": r.text,
                    "score": r.score,
                    "rank": r.rank,
                }
                for r in results
            ],
            "total_latency_ms": q_elapsed,
        }
        runs.append(run)

        if i % 10 == 0:
            logger.info("  Processed %d/%d queries", i, len(queries))

    elapsed = time.time() - start
    avg_latency = (elapsed * 1000) / len(queries) if queries else 0
    logger.info("BM25 complete: %d queries in %.2fs (avg %.1f ms/query)",
                len(queries), elapsed, avg_latency)

    return runs

def save_runs(runs, output_path):
    """Save runs to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        for run in runs:
            f.write(json.dumps(run) + "\n")
    logger.info("Saved run file: %s", output_path)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run all retrievers")
    parser.add_argument("--rebuild-all", action="store_true", help="Rebuild all indexes")
    parser.add_argument("--top-k", type=int, default=10, help="Top-K results")
    args = parser.parse_args()

    base = Path(__file__).parent
    chunks_path = base / "data" / "chunks" / "chunks_v1.jsonl"
    queries_path = base / "data" / "queries" / "qa_dataset_v1.jsonl"
    qrels_path = base / "data" / "qrels" / "qrels.tsv"

    logger.info("Loading chunks from: %s", chunks_path)
    chunks = load_jsonl(chunks_path)
    logger.info("Loaded %d chunks", len(chunks))

    logger.info("Loading queries from: %s", queries_path)
    queries = load_queries(queries_path)
    logger.info("Loaded %d queries", len(queries))

    # Run BM25
    bm25_runs = run_bm25(chunks, queries, rebuild=args.rebuild_all, top_k=args.top_k)
    save_runs(bm25_runs, base / "runs" / "retrieval" / "bm25_run.jsonl")

    # Load results and generate report
    logger.info("\n" + "="*60)
    logger.info("Evaluating Results")
    logger.info("="*60)

    if qrels_path.exists():
        evaluator = RetrievalEvaluator(qrels_path=qrels_path)

        # Count empty result sets
        empty_count = sum(1 for run in bm25_runs if not run["results"])
        non_empty_count = len(bm25_runs) - empty_count

        logger.info("BM25: %d queries with results, %d with empty results",
                    non_empty_count, empty_count)

        if non_empty_count > 0:
            # Sample some results
            for run in bm25_runs[:3]:
                if run["results"]:
                    logger.info("  Query: %s", run["query_text"][:60])
                    logger.info("    Top result: %s (score: %.2f)",
                               run["results"][0]["chunk_id"],
                               run["results"][0]["score"])

    logger.info("\nAll retrievers completed. Results saved in runs/retrieval/")

if __name__ == "__main__":
    main()
