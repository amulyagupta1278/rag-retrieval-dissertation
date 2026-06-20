#!/usr/bin/env python3
"""
Build FAISS Index
==================
Loads chunks from chunks_v1.jsonl and builds a FAISS index using
SentenceTransformer embeddings. The index is saved to disk for reuse.
"""

import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrievers.faiss_retriever import FAISSRetriever

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


def main():
    chunks_path = Path(__file__).parent.parent / "data" / "chunks" / "chunks_v1.jsonl"
    index_dir = Path(__file__).parent.parent / "indexes" / "faiss"

    if not chunks_path.exists():
        logger.error(f"Chunks file not found: {chunks_path}")
        sys.exit(1)

    logger.info(f"Loading chunks from {chunks_path}...")
    chunks = load_chunks(chunks_path)
    logger.info(f"Loaded {len(chunks)} chunks")

    # Create retriever and build index
    retriever = FAISSRetriever(
        index_dir=index_dir,
        chunks_path=chunks_path,
        model_name="all-MiniLM-L6-v2",
    )

    t0 = time.time()
    retriever.build_index(chunks)
    elapsed = time.time() - t0

    # Report stats
    print("\n" + "=" * 70)
    print("FAISS INDEX BUILD SUMMARY")
    print("=" * 70)
    print(f"Total chunks indexed: {len(chunks)}")
    print(f"Embedding dimension: 384 (all-MiniLM-L6-v2)")
    print(f"Index type: IndexFlatL2 (exact L2-based search)")
    print(f"Build time: {elapsed:.2f}s")
    print(f"\nIndex saved to: {index_dir}")
    print(f"  • faiss.index")
    print(f"  • chunk_ids.json")
    print(f"  • config.json")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
