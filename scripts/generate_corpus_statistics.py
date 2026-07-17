#!/usr/bin/env python3
"""Generate versioned corpus statistics after entity-graph artifacts exist."""

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
    parser.add_argument("--version", default="v3_clean")
    parser.add_argument("--documents", default="data/processed/documents.jsonl")
    parser.add_argument("--chunks", default="data/chunks/chunks.jsonl")
    parser.add_argument("--catalog", default="data/sources/source_catalog_v2.jsonl")
    parser.add_argument("--acquisition", default="data/metadata/acquisition_audit_v2.jsonl")
    parser.add_argument("--deduplication", default=None)
    parser.add_argument("--nodes", default="indexes/graphrag/nodes.jsonl")
    parser.add_argument("--edges", default="indexes/graphrag/edges.jsonl")
    parser.add_argument("--output-dir", default="data/metadata")
    args = parser.parse_args()
    deduplication = args.deduplication or f"data/metadata/deduplication_report_{args.version}.jsonl"
    documents = load_jsonl(args.documents)
    chunks = load_jsonl(args.chunks)
    catalog = load_jsonl(args.catalog)
    acquisition = load_jsonl(args.acquisition)
    duplicates = load_jsonl(deduplication)
    nodes = load_jsonl(args.nodes)
    edges = load_jsonl(args.edges)
    stats = build_statistics(
        documents, chunks, corpus_version=args.version, catalog_entries=len(catalog),
        acquisition=acquisition, duplicate_count=sum(d.get("method") != "extraction_quality" for d in duplicates),
        graph_nodes=nodes, graph_edges=edges,
    )
    write_statistics(
        stats, f"{args.output_dir}/corpus_statistics_{args.version}.json",
        f"{args.output_dir}/corpus_statistics_{args.version}.md",
    )
    print(json.dumps({key: stats[key] for key in ("accepted_documents", "total_chunks", "unique_entities_extracted", "graph_nodes", "graph_edges")}, indent=2))


if __name__ == "__main__":
    main()
