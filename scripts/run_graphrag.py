#!/usr/bin/env python3
"""
Run GraphRAG Retrieval
======================
Loads a pre-built knowledge graph and runs entity-aware retrieval
on a set of queries.
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrievers.graph_retriever import GraphRAGRetriever
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
    graph_dir = project_root / "indexes" / "graphrag"
    queries_path = project_root / "data" / "queries" / "qa_dataset_v1.jsonl"
    output_run_path = project_root / "runs" / "retrieval" / "graphrag_run.tsv"
    output_jsonl_path = project_root / "runs" / "retrieval" / "graphrag_run.jsonl"

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

    if not graph_dir.exists():
        logger.error(f"Graph directory not found: {graph_dir}")
        logger.error("Run: python scripts/build_graph.py")
        sys.exit(1)

    # Load queries
    logger.info(f"Loading queries from {queries_path}...")
    queries = load_queries(queries_path)
    logger.info(f"Loaded {len(queries)} queries")

    # Create retriever and load graph
    retriever = GraphRAGRetriever(
        graph_dir=graph_dir,
        chunks_path=chunks_path,
        model_name="en_core_web_sm",
    )

    logger.info("Loading knowledge graph...")
    retriever.load_graph()

    # Run benchmark
    top_k = 5
    config_snapshot = {
        "retriever": "graphrag",
        "entity_types": ["PERSON", "ORG", "GPE", "MONEY", "DATE", "LAW", "SCHEME_NAME", "AMOUNT", "BENEFICIARY", "ELIGIBILITY", "DOCUMENT"],
        "graph_traversal_hops": 2,
        "top_k": top_k,
    }

    logger.info(f"Running retrieval on {len(queries)} queries (top_k={top_k}, 2-hop traversal)...")
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
    print("GRAPHRAG RETRIEVAL SUMMARY")
    print("=" * 70)
    print(f"Queries processed: {len(queries)}")
    print(f"Total results returned: {total_results}")
    print(f"Average latency per query: {avg_latency:.2f}ms")
    print(f"Total time: {elapsed:.2f}s")

    print(f"\nPer-Query Breakdown:")
    for i, run in enumerate(runs[:3]):  # Show first 3
        num_seed_entities = run.results[0].extra.get("num_seed_matches", 0) if run.results else 0
        print(f"  Query {i + 1} ({run.query_id}): {run.query_text}")
        print(f"    • Seed entities matched: {num_seed_entities}")
        print(f"    • Results returned: {len(run.results)}")
        print(f"    • Latency: {run.total_latency_ms:.2f}ms")

    print(f"\nOutput files:")
    print(f"  • TREC format: {output_run_path}")
    print(f"  • JSONL format: {output_jsonl_path}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
