#!/usr/bin/env python3
"""Build frozen corpus-only entity-registry/Graph v3.1."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_phase3_graph_v2 import load_source_metadata, parse_jsonl, validate_inputs  # noqa: E402
from src.retrievers.entity_graph_v3 import (  # noqa: E402
    build_entity_registry,
    build_graph,
    canonicalize_organization_entities,
    graph_adjacency,
    normalize_text,
)
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_bytes, sha256_file  # noqa: E402


APPROVED_CONFIG = (ROOT / "configs/entity_graph_v3_1_frozen.json").resolve()
APPROVED_REGISTRY = (ROOT / "data/v2/pilot/graph/entity_registry_v3_1.jsonl").resolve()
APPROVED_OUTPUT = (ROOT / "runs/v2/phase3_graph_v3_1").resolve()
APPROVED_AUDIT = (ROOT / "audits/phase3_graph_v3_1").resolve()
FORBIDDEN_TERMS = {"qa", "qrels", "question", "gold", "reference_answer", "graph_path", "category", "ranking"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--registry-output", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = {
        name: getattr(args, name).resolve()
        for name in ("config", "chunks", "documents", "source_manifest", "registry_output", "output", "audit")
    }
    if paths["config"] != APPROVED_CONFIG:
        raise ValueError("v3.1 build requires frozen v3.1 configuration")
    if paths["registry_output"] != APPROVED_REGISTRY or paths["output"] != APPROVED_OUTPUT or paths["audit"] != APPROVED_AUDIT:
        raise ValueError("v3.1 outputs must use approved new paths")
    for path in paths.values():
        if path != ROOT and ROOT not in path.parents:
            raise ValueError(f"path outside repository: {path}")
    if not args.overwrite:
        collisions = [path for path in (paths["registry_output"], paths["output"], paths["audit"]) if path.exists()]
        if collisions:
            raise FileExistsError(f"output collision; pass --overwrite explicitly: {collisions}")

    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    if config.get("registry_version") != "entity-registry-v3.1" or config.get("graph_version") != "entity-graph-v3.1":
        raise ValueError("configuration version mismatch")
    if config.get("status") != "frozen_pre_retrieval" or config.get("tuning_after_results") is not False:
        raise ValueError("configuration is not frozen before retrieval")
    chunks = parse_jsonl(paths["chunks"])
    documents = parse_jsonl(paths["documents"])
    source_manifest = parse_jsonl(paths["source_manifest"])
    validate_inputs(config, paths["chunks"], paths["documents"], paths["source_manifest"], chunks, documents, source_manifest)
    source_metadata, source_evidence = load_source_metadata(paths["source_manifest"])

    start = time.perf_counter()
    base_registry, base_registry_audit = build_entity_registry(
        chunks=chunks, documents=documents, source_metadata=source_metadata, config=config,
    )
    registry, organization_audit = canonicalize_organization_entities(
        registry=base_registry,
        documents=documents,
        equivalences=config["organization_canonicalization"]["equivalences"],
    )
    nodes, edges, chunk_entities, graph_audit = build_graph(chunks=chunks, registry=registry)
    build_seconds = time.perf_counter() - start

    banned = {normalize_text(value) for value in config["banned_entity_labels"]}
    accepted_names = {
        normalize_text(name)
        for row in registry if row["status"] == "accepted"
        for name in [row["canonical_label"], *row["aliases"]]
    }
    surviving_banned = sorted(accepted_names & banned)
    if surviving_banned:
        raise ValueError(f"banned entities survived v3.1 registry: {surviving_banned}")
    banned_audit = {
        "configured_banned_labels": sorted(banned),
        "surviving_accepted": surviving_banned,
        "passed": not surviving_banned,
    }

    write_jsonl(paths["registry_output"], registry, key="entity_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "index/nodes.jsonl", nodes, key="node_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "index/edges.jsonl", edges, key="edge_id", overwrite=args.overwrite)
    write_json(paths["output"] / "index/chunk_entities.json", chunk_entities, overwrite=args.overwrite)
    reloaded_nodes = parse_jsonl(paths["output"] / "index/nodes.jsonl")
    reloaded_edges = parse_jsonl(paths["output"] / "index/edges.jsonl")
    reloaded_chunk_entities = json.loads((paths["output"] / "index/chunk_entities.json").read_text(encoding="utf-8"))
    if (reloaded_nodes, reloaded_edges, reloaded_chunk_entities) != (nodes, edges, chunk_entities):
        raise RuntimeError("v3.1 Graph serialization/reload mismatch")
    graph_adjacency(reloaded_edges)

    write_json(paths["audit"] / "base_registry_audit.json", base_registry_audit, overwrite=args.overwrite)
    write_json(paths["audit"] / "organization_duplicate_audit.json", organization_audit, overwrite=args.overwrite)
    write_json(paths["audit"] / "banned_token_audit.json", banned_audit, overwrite=args.overwrite)
    write_json(paths["audit"] / "graph_structure_audit.json", graph_audit, overwrite=args.overwrite)
    write_json(paths["audit"] / "source_metadata_evidence.json", source_evidence, overwrite=args.overwrite)

    builder_parameters = sorted(inspect.signature(canonicalize_organization_entities).parameters)
    forbidden_parameters = sorted(set(builder_parameters) & FORBIDDEN_TERMS)
    if forbidden_parameters:
        raise RuntimeError(f"forbidden canonicalizer parameters: {forbidden_parameters}")
    boundary = {
        "index_builder_cli_inputs": ["config", "chunks", "documents", "source-manifest"],
        "canonicalizer_parameters": builder_parameters,
        "forbidden_parameters_present": forbidden_parameters,
        "qa_qrels_gold_reference_rankings_read": False,
        "input_hashes": {
            str(paths["chunks"].relative_to(ROOT)): sha256_file(paths["chunks"]),
            str(paths["documents"].relative_to(ROOT)): sha256_file(paths["documents"]),
            str(paths["source_manifest"].relative_to(ROOT)): sha256_file(paths["source_manifest"]),
        },
    }
    write_json(paths["audit"] / "index_build_boundary.json", boundary, overwrite=args.overwrite)

    artifact_paths = [
        paths["registry_output"],
        paths["output"] / "index/nodes.jsonl",
        paths["output"] / "index/edges.jsonl",
        paths["output"] / "index/chunk_entities.json",
    ]
    artifact_hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in artifact_paths}
    graph_hashes = {key: value for key, value in artifact_hashes.items() if key != str(paths["registry_output"].relative_to(ROOT))}
    graph_hash = sha256_bytes(stable_json(graph_hashes).encode("utf-8"))
    freeze = {
        "status": "entity_graph_v3.1_frozen_before_queries",
        "registry_version": "entity-registry-v3.1",
        "graph_version": "entity-graph-v3.1",
        "benchmark_queries_run": 0,
        "retrieval_metrics_present": False,
        "build_seconds": build_seconds,
        "configuration_path": str(paths["config"].relative_to(ROOT)),
        "configuration_sha256": sha256_file(paths["config"]),
        "registry_sha256": sha256_file(paths["registry_output"]),
        "graph_sha256": graph_hash,
        "artifact_hashes": artifact_hashes,
        "input_hashes": boundary["input_hashes"],
        "code_hashes": {
            "src/retrievers/entity_graph_v3.py": sha256_file(ROOT / "src/retrievers/entity_graph_v3.py"),
            "scripts/build_phase3_graph_v3_1.py": sha256_file(ROOT / "scripts/build_phase3_graph_v3_1.py"),
        },
        "index_counts": {
            "registry_rows": len(registry),
            "accepted_entities": sum(row["status"] == "accepted" for row in registry),
            "rejected_entities": sum(row["status"] == "rejected" for row in registry),
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "forbidden_output_directories_before_retrieval": ["metrics", "rankings", "traces", "pool"],
    }
    write_json(paths["output"] / "index_freeze_manifest.json", freeze, overwrite=args.overwrite)
    audit_files = [
        paths["audit"] / "base_registry_audit.json",
        paths["audit"] / "organization_duplicate_audit.json",
        paths["audit"] / "banned_token_audit.json",
        paths["audit"] / "graph_structure_audit.json",
        paths["audit"] / "source_metadata_evidence.json",
        paths["audit"] / "index_build_boundary.json",
    ]
    write_json(paths["audit"] / "hashes.json", {str(path.relative_to(ROOT)): sha256_file(path) for path in audit_files}, overwrite=args.overwrite)
    print(stable_json({
        "status": freeze["status"],
        "accepted_entities": freeze["index_counts"]["accepted_entities"],
        "merge_count": organization_audit["new_merged_entity_count"],
        "graph_sha256": graph_hash,
        "graph_counts": graph_audit,
    }))


if __name__ == "__main__":
    main()
