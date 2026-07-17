#!/usr/bin/env python3
"""Generate corpus v2 statistics after GraphRAG artifacts exist."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.ingestion.corpus_quality import build_statistics, write_statistics
from src.utils.io_utils import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v2")
    args = parser.parse_args()
    documents = load_jsonl("data/processed/documents.jsonl")
    chunks = load_jsonl("data/chunks/chunks.jsonl")
    catalog = load_jsonl("data/sources/source_catalog_v2.jsonl")
    acquisition = load_jsonl("data/metadata/acquisition_audit_v2.jsonl")
    duplicates = load_jsonl("data/metadata/deduplication_report_v2.jsonl")
    nodes = load_jsonl("indexes/graphrag/nodes.jsonl")
    edges = load_jsonl("indexes/graphrag/edges.jsonl")
    stats = build_statistics(
        documents, chunks, corpus_version=args.version, catalog_entries=len(catalog),
        acquisition=acquisition, duplicate_count=sum(d.get("method") != "extraction_quality" for d in duplicates),
        graph_nodes=nodes, graph_edges=edges,
    )
    write_statistics(
        stats, f"data/metadata/corpus_statistics_{args.version}.json",
        f"data/metadata/corpus_statistics_{args.version}.md",
    )
    print(json.dumps({key: stats[key] for key in ("accepted_documents", "total_chunks", "unique_entities_extracted", "graph_nodes", "graph_edges")}, indent=2))


if __name__ == "__main__":
    main()
