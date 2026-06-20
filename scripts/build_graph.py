#!/usr/bin/env python3
"""
Build Knowledge Graph
======================
Extracts entities from chunks using spaCy NER and domain patterns,
builds a NetworkX graph with entity co-occurrence and chunk references.
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrievers.graph_retriever import GraphRAGRetriever

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def load_chunks(chunks_path: Path) -> list[dict]:
    """Load chunks from JSONL file."""
    chunks = []
    with open(chunks_path) as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))
    return chunks


def count_nodes_by_type(retriever: GraphRAGRetriever) -> dict[str, int]:
    """Count nodes by entity type."""
    if retriever.graph is None:
        return {}

    counts = {}
    for node_id, node_data in retriever.graph.nodes(data=True):
        node_type = node_data.get("type", "UNKNOWN")
        counts[node_type] = counts.get(node_type, 0) + 1

    return counts


def main():
    chunks_path = Path(__file__).parent.parent / "data" / "chunks" / "chunks_v1.jsonl"
    graph_dir = Path(__file__).parent.parent / "indexes" / "graphrag"

    if not chunks_path.exists():
        logger.error(f"Chunks file not found: {chunks_path}")
        sys.exit(1)

    logger.info(f"Loading chunks from {chunks_path}...")
    chunks = load_chunks(chunks_path)
    logger.info(f"Loaded {len(chunks)} chunks")

    # Create retriever and build graph
    retriever = GraphRAGRetriever(
        graph_dir=graph_dir,
        chunks_path=chunks_path,
        model_name="en_core_web_sm",
    )

    t0 = time.time()
    retriever.build_graph()
    elapsed = time.time() - t0

    # Report statistics
    node_counts = count_nodes_by_type(retriever)
    entity_nodes = sum(count for ntype, count in node_counts.items() if ntype != "CHUNK")
    chunk_nodes = node_counts.get("CHUNK", 0)
    total_edges = retriever.graph.number_of_edges()
    graph_density = 2 * total_edges / (retriever.graph.number_of_nodes() * (retriever.graph.number_of_nodes() - 1)) if retriever.graph.number_of_nodes() > 1 else 0

    print("\n" + "=" * 70)
    print("KNOWLEDGE GRAPH BUILD SUMMARY")
    print("=" * 70)
    print(f"\nChunks processed: {len(chunks)}")
    print(f"Build time: {elapsed:.2f}s")
    print(f"\nGraph Statistics:")
    print(f"  Total nodes: {retriever.graph.number_of_nodes()}")
    print(f"    • Entity nodes: {entity_nodes}")
    print(f"    • Chunk nodes: {chunk_nodes}")
    print(f"  Total edges: {total_edges}")
    print(f"  Graph density: {graph_density:.4f}")

    print(f"\nEntity Nodes by Type:")
    for node_type in sorted(node_counts.keys()):
        if node_type != "CHUNK":
            print(f"  • {node_type:20s}: {node_counts[node_type]:4d}")

    print(f"\nGraph saved to: {graph_dir}")
    print(f"  • graph.json         ({retriever.graph.number_of_nodes()} nodes, {total_edges} edges)")
    print(f"  • chunk_lookup.json  ({len(retriever.chunk_lookup)} chunks)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
