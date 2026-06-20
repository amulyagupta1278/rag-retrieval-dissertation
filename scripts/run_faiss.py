#!/usr/bin/env python3
"""
Run FAISS Retrieval
===================
Loads a pre-built FAISS index and runs retrieval on a set of queries.
Outputs a TREC-format run file and (optionally) a RetrievalRun JSONL.
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrievers.faiss_retriever import FAISSRetriever
from src.retrievers.base_retriever import RetrievalRun

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_queries(queries_path: Path) -> list[dict]:
    """Load queries from JSONL file."""
    queries = []
    with open(queries_path) as f:
        for line in f:
            if line.strip():
                queries.append(json.loads(line))
    return queries


def main():
    # Setup paths
    project_root = Path(__file__).parent.parent
    chunks_path = project_root / "data" / "chunks" / "chunks_v1.jsonl"
    index_dir = project_root / "indexes" / "faiss"
    queries_path = project_root / "data" / "queries" / "qa_dataset_v1.jsonl"
    output_run_path = project_root / "runs" / "retrieval" / "faiss_run.tsv"
    output_jsonl_path = project_root / "runs" / "retrieval" / "faiss_run.jsonl"

    # Create output directories
    output_run_path.parent.mkdir(parents=True, exist_ok=True)
    output_jsonl_path.parent.mkdir(parents=True, exist_ok=True)

    # Fallback: try alternate query file names
    if not queries_path.exists():
        alt_path = project_root / "data" / "queries" / "qa_dataset.jsonl"
        if alt_path.exists():
            queries_path = alt_path
            logger.info(f"Using alternate queries file: {queries_path}")
        else:
            logger.error(f"Queries file not found: {queries_path}")
            sys.exit(1)

    if not index_dir.exists():
        logger.error(f"Index directory not found: {index_dir}")
        logger.error("Run: python scripts/build_faiss_index.py")
        sys.exit(1)

    # Load queries
    logger.info(f"Loading queries from {queries_path}...")
    queries = load_queries(queries_path)
    logger.info(f"Loaded {len(queries)} queries")

    # Create retriever and load index
    retriever = FAISSRetriever(
        index_dir=index_dir,
        chunks_path=chunks_path,
        model_name="all-MiniLM-L6-v2",
    )

    logger.info("Loading FAISS index...")
    retriever.load_index()

    # Run benchmark
    top_k = 5
    config_snapshot = {
        "retriever": "faiss",
        "model": "all-MiniLM-L6-v2",
        "index_type": "IndexFlatL2",
        "top_k": top_k,
    }

    logger.info(f"Running retrieval on {len(queries)} queries (top_k={top_k})...")
    t0 = time.time()
    runs = retriever.run_benchmark(queries, top_k=top_k, config_snapshot=config_snapshot)
    elapsed = time.time() - t0

    # Save JSONL format (RetrievalRun objects)
    logger.info(f"Saving runs to {output_jsonl_path}...")
    RetrievalRun.save_run_file(runs, output_jsonl_path)

    # Save TREC format
    logger.info(f"Saving TREC run file to {output_run_path}...")
    retriever.write_run_file(queries, top_k=top_k, output_path=output_run_path)

    # Summary
    total_results = sum(len(run.results) for run in runs)
    avg_latency = sum(run.total_latency_ms for run in runs) / len(runs) if runs else 0

    print("\n" + "=" * 70)
    print("FAISS RETRIEVAL SUMMARY")
    print("=" * 70)
    print(f"Queries processed: {len(queries)}")
    print(f"Total results returned: {total_results}")
    print(f"Average latency per query: {avg_latency:.2f}ms")
    print(f"Total time: {elapsed:.2f}s")
    print(f"\nOutput files:")
    print(f"  • TREC format: {output_run_path}")
    print(f"  • JSONL format: {output_jsonl_path}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
