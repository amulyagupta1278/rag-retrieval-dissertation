#!/usr/bin/env python3
"""Build and freeze the corrected corpus-only Phase 3 Graph index."""

from __future__ import annotations

import argparse
import inspect
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.entity_graph_v3 import (  # noqa: E402
    ALLOWED_ENTITY_TYPES,
    build_entity_registry,
    build_graph,
    graph_adjacency,
)
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_bytes, sha256_file  # noqa: E402


APPROVED_REGISTRY = (ROOT / "data/v2/pilot/graph/entity_registry_v3.jsonl").resolve()
APPROVED_OUTPUT = (ROOT / "runs/v2/phase3_graph_v2").resolve()
APPROVED_AUDIT = (ROOT / "audits/phase3_graph_v2").resolve()
FORBIDDEN_BUILD_TERMS = {"qa", "qrels", "question", "reference_answer", "gold", "graph_path", "category", "ranking"}


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read non-empty JSONL records with actionable line errors."""
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row must be an object at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise ValueError(f"input is empty: {path}")
    return rows


def _plain(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def load_source_metadata(manifest_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load only structured basicDetails fields from corpus raw snapshots."""
    metadata: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for row in sorted(parse_jsonl(manifest_path), key=lambda item: str(item["source_id"])):
        raw_path = (ROOT / str(row["raw_snapshot_path"])).resolve()
        if ROOT not in raw_path.parents or not raw_path.is_file():
            raise ValueError(f"source snapshot is missing or outside repository: {raw_path}")
        if sha256_file(raw_path) != row["raw_sha256"]:
            raise ValueError(f"source snapshot hash mismatch: {raw_path}")
        item = {
            "source_id": str(row["source_id"]),
            "document_id": f"doc-{row['scheme_id']}",
            "scheme_short_title": "",
            "implementing_agency": "",
            "target_beneficiaries": [],
        }
        if raw_path.suffix == ".json":
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            basic = (((payload.get("data") or {}).get("en") or {}).get("basicDetails") or {})
            if not isinstance(basic, dict):
                raise ValueError(f"structured source basicDetails malformed: {raw_path}")
            item["scheme_short_title"] = _plain(basic.get("schemeShortTitle"))
            item["implementing_agency"] = _plain(basic.get("implementingAgency"))
            targets = basic.get("targetBeneficiaries") or []
            item["target_beneficiaries"] = sorted({
                _plain(target.get("label"))
                for target in targets
                if isinstance(target, dict) and _plain(target.get("label"))
            })
        metadata.append(item)
        evidence.append({
            "source_id": item["source_id"],
            "raw_snapshot_path": str(raw_path.relative_to(ROOT)),
            "raw_sha256": sha256_file(raw_path),
            "fields_read": ["schemeShortTitle", "implementingAgency", "targetBeneficiaries.label"] if raw_path.suffix == ".json" else [],
        })
    return metadata, evidence


def validate_inputs(
    config: dict[str, Any], chunks_path: Path, documents_path: Path, source_manifest_path: Path,
    chunks: list[dict[str, Any]], documents: list[dict[str, Any]], source_manifest: list[dict[str, Any]],
) -> None:
    """Fail closed unless exact preregistered corpus inputs are supplied."""
    expected = config["expected_inputs"]
    checks = (
        ("chunk", len(chunks), expected["chunk_count"], sha256_file(chunks_path), expected["chunks_sha256"]),
        ("document", len(documents), expected["document_count"], sha256_file(documents_path), expected["documents_sha256"]),
        ("source manifest", len(source_manifest), expected["source_manifest_count"], sha256_file(source_manifest_path), expected["source_manifest_sha256"]),
    )
    for label, actual_count, expected_count, actual_hash, expected_hash in checks:
        if actual_count != expected_count:
            raise ValueError(f"{label} count mismatch: expected {expected_count}, got {actual_count}")
        if actual_hash != expected_hash:
            raise ValueError(f"{label} SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")
    if set(config["allowed_entity_types"]) != ALLOWED_ENTITY_TYPES:
        raise ValueError("configuration allowed entity types disagree with implementation")
    chunk_ids = [str(row["chunk_id"]) for row in chunks]
    document_ids = [str(row["document_id"]) for row in documents]
    source_ids = [str(row["source_id"]) for row in source_manifest]
    for label, values in (("chunk IDs", chunk_ids), ("document IDs", document_ids), ("source IDs", source_ids)):
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label}")
    known_documents = set(document_ids)
    unknown = sorted({str(row["document_id"]) for row in chunks} - known_documents)
    if unknown:
        raise ValueError(f"chunks reference unknown documents: {unknown}")


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

    paths = {name: getattr(args, name).resolve() for name in ("config", "chunks", "documents", "source_manifest", "registry_output", "output", "audit")}
    if paths["registry_output"] != APPROVED_REGISTRY or paths["output"] != APPROVED_OUTPUT or paths["audit"] != APPROVED_AUDIT:
        raise ValueError("corrected Graph outputs must use the approved Phase 3 V2 paths")
    for path in paths.values():
        if path != ROOT and ROOT not in path.parents:
            raise ValueError(f"path outside repository is forbidden: {path}")
    if not args.overwrite:
        collisions = [path for path in (paths["registry_output"], paths["output"], paths["audit"]) if path.exists()]
        if collisions:
            raise FileExistsError(f"output collision; pass --overwrite explicitly: {collisions}")

    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    if config.get("status") != "candidate_frozen_pre_run" or config.get("tuning_after_results") is not False:
        raise ValueError("Graph configuration is not a frozen pre-run candidate")
    chunks = parse_jsonl(paths["chunks"])
    documents = parse_jsonl(paths["documents"])
    source_manifest = parse_jsonl(paths["source_manifest"])
    validate_inputs(config, paths["chunks"], paths["documents"], paths["source_manifest"], chunks, documents, source_manifest)
    source_metadata, source_evidence = load_source_metadata(paths["source_manifest"])

    registry, registry_audit = build_entity_registry(
        chunks=chunks, documents=documents, source_metadata=source_metadata, config=config,
    )
    nodes, edges, chunk_entities, graph_audit = build_graph(chunks=chunks, registry=registry)
    write_jsonl(paths["registry_output"], registry, key="entity_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "index/nodes.jsonl", nodes, key="node_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "index/edges.jsonl", edges, key="edge_id", overwrite=args.overwrite)
    write_json(paths["output"] / "index/chunk_entities.json", chunk_entities, overwrite=args.overwrite)

    # Prove deterministic serialization can be loaded without semantic changes.
    reloaded_nodes = parse_jsonl(paths["output"] / "index/nodes.jsonl")
    reloaded_edges = parse_jsonl(paths["output"] / "index/edges.jsonl")
    reloaded_chunks = json.loads((paths["output"] / "index/chunk_entities.json").read_text(encoding="utf-8"))
    if reloaded_nodes != nodes or reloaded_edges != edges or reloaded_chunks != chunk_entities:
        raise RuntimeError("serialized Graph does not reload identically")
    graph_adjacency(reloaded_edges)

    write_json(paths["audit"] / "entity_registry_audit.json", registry_audit, overwrite=args.overwrite)
    write_json(paths["audit"] / "graph_structure_audit.json", graph_audit, overwrite=args.overwrite)
    write_json(paths["audit"] / "source_metadata_evidence.json", source_evidence, overwrite=args.overwrite)

    builder_parameters = sorted(inspect.signature(build_entity_registry).parameters)
    forbidden_parameters = sorted(set(builder_parameters) & FORBIDDEN_BUILD_TERMS)
    build_boundary = {
        "builder_function": "src.retrievers.entity_graph_v3.build_entity_registry",
        "builder_parameters": builder_parameters,
        "forbidden_parameters_present": forbidden_parameters,
        "cli_inputs": ["config", "chunks", "documents", "source-manifest"],
        "forbidden_cli_inputs": [],
        "qa_qrels_previous_rankings_read": False,
        "proof": "Builder API and CLI expose no QA, qrels, gold, graph_path, category, or ranking argument.",
        "input_hashes": {
            str(paths["chunks"].relative_to(ROOT)): sha256_file(paths["chunks"]),
            str(paths["documents"].relative_to(ROOT)): sha256_file(paths["documents"]),
            str(paths["source_manifest"].relative_to(ROOT)): sha256_file(paths["source_manifest"]),
        },
    }
    if forbidden_parameters:
        raise RuntimeError(f"forbidden builder parameters: {forbidden_parameters}")
    write_json(paths["audit"] / "benchmark_leakage_boundary.json", build_boundary, overwrite=args.overwrite)

    artifact_paths = [
        paths["registry_output"],
        paths["output"] / "index/nodes.jsonl",
        paths["output"] / "index/edges.jsonl",
        paths["output"] / "index/chunk_entities.json",
    ]
    artifact_hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in artifact_paths}
    graph_hash = sha256_bytes(stable_json({key: value for key, value in artifact_hashes.items() if key != str(paths["registry_output"].relative_to(ROOT))}).encode("utf-8"))
    freeze = {
        "status": "candidate_frozen_pre_run_owner_approval_required",
        "retrieval_metrics_present": False,
        "benchmark_queries_run": 0,
        "configuration_path": str(paths["config"].relative_to(ROOT)),
        "configuration_sha256": sha256_file(paths["config"]),
        "registry_sha256": sha256_file(paths["registry_output"]),
        "graph_sha256": graph_hash,
        "code_paths": ["src/retrievers/entity_graph_v3.py", "scripts/build_phase3_graph_v2.py"],
        "code_hashes": {
            "src/retrievers/entity_graph_v3.py": sha256_file(ROOT / "src/retrievers/entity_graph_v3.py"),
            "scripts/build_phase3_graph_v2.py": sha256_file(ROOT / "scripts/build_phase3_graph_v2.py"),
        },
        "artifact_hashes": artifact_hashes,
        "input_hashes": build_boundary["input_hashes"],
        "index_counts": {
            "registry_rows": len(registry),
            "accepted_entities": registry_audit["accepted_entity_count"],
            "rejected_entities": registry_audit["rejected_entity_count"],
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "forbidden_output_directories": ["metrics", "rankings", "traces", "pool"],
    }
    write_json(paths["output"] / "freeze_manifest.json", freeze, overwrite=args.overwrite)
    audit_files = sorted(path for path in paths["audit"].rglob("*") if path.is_file() and path.name != "hashes.json")
    write_json(paths["audit"] / "hashes.json", {str(path.relative_to(ROOT)): sha256_file(path) for path in audit_files}, overwrite=args.overwrite)
    print(stable_json({
        "accepted_entities": registry_audit["accepted_entity_count"],
        "rejected_entities": registry_audit["rejected_entity_count"],
        "graph": graph_audit,
        "status": freeze["status"],
    }))


if __name__ == "__main__":
    main()
