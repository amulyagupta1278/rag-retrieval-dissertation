#!/usr/bin/env python3
"""Publish the frozen serialized-JSON baseline as an explicit legacy release.

This script copies only already archived historical artifacts.  It does not
reconstruct or relabel missing raw documents as if they were original files.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.utils.io_utils import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--publish-versioned", action="store_true")
    args = parser.parse_args()
    version = "v2_serialized"
    release_root = ROOT / "releases"
    work = release_root / f".{version}-{uuid.uuid4().hex}"
    target = release_root / version
    source_data = ROOT / "data/baselines/serialized_json_baseline"
    source_indexes = ROOT / "indexes/baselines/serialized_json_baseline"
    source_runs = ROOT / "runs/baselines/serialized_json_baseline"
    try:
        shutil.copytree(source_data, work / "data", ignore=shutil.ignore_patterns(
            "release_manifest.jsonl", "BASELINE_SHA256SUMS", "SHA256SUMS",
        ))
        shutil.copytree(source_indexes, work / "indexes")
        shutil.copytree(source_runs, work / "runs")
        shutil.copy2(ROOT / "data/metadata/corpus_statistics_v2.json", work / "data/metadata/corpus_statistics_v2.json")
        shutil.copy2(ROOT / "data/metadata/corpus_statistics_v2.md", work / "data/metadata/corpus_statistics_v2.md")
        qa_items = load_jsonl(work / "data/queries/qa_dataset.jsonl")
        chunk_lookup = {item["chunk_id"]: item for item in load_jsonl(work / "data/chunks/chunks.jsonl")}
        audit = []
        for item in qa_items:
            if item.get("category") not in {"entity_relation", "multi_hop"}:
                continue
            meta = item.get("extra_meta", {})
            audit.append({
                "question_id": item["question_id"], "category": item["category"],
                "schemes": meta.get("scheme_names", []), "bridge_entity": meta.get("bridge_entity"),
                "relationship_type": meta.get("relationship_type"),
                "gold_chunk_ids": item["gold_evidence_ids"], "source_doc_ids": item["source_doc_ids"],
                "evidence_snippets": [
                    chunk_lookup.get(chunk_id, {}).get("text", "")[:300]
                    for chunk_id in item["gold_evidence_ids"]
                ],
                "distinct_schemes": len(set(meta.get("scheme_names", []))) == 2,
                "distinct_documents": len(set(item["source_doc_ids"])) == 2,
                "validation_result": meta.get("validation_result", "historically_accepted"),
                "audit_provenance": "reconstructed_losslessly_from_archived_QA_and_chunks",
            })
        if len(audit) != 40:
            raise RuntimeError(f"Expected 40 historical cross-scheme records, found {len(audit)}")
        audit_path = work / "data/metadata/cross_scheme_audit_v2.jsonl"
        with audit_path.open("w", encoding="utf-8") as handle:
            for record in audit:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        lines = [
            "# Cross-Scheme Audit v2_serialized", "",
            "Reconstructed losslessly from the archived QA and chunk evidence.", "",
            "| ID | Category | Scheme A | Scheme B | Bridge |", "|---|---|---|---|---|",
        ]
        for record in audit:
            lines.append(
                f"| {record['question_id']} | {record['category']} | {record['schemes'][0]} | "
                f"{record['schemes'][1]} | {record['bridge_entity']} |"
            )
        (work / "data/metadata/cross_scheme_audit_v2.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        configs = work / "configs"
        configs.mkdir(parents=True)
        historical_contract = {
            "corpus_version": version,
            "status": "historical_artifact_contract_recovered_from_archived_metadata",
            "documents": 120,
            "chunks": 1074,
            "queries": 100,
            "qrels": 140,
            "chunk_size": 512,
            "chunk_overlap": 64,
            "bm25": {"k1": 1.5, "b": 0.75},
            "faiss": {
                "model_name": "sentence-transformers/all-MiniLM-L6-v2",
                "index_type": "IndexFlatL2",
                "normalization": "not_recorded_in_historical_config",
                "model_revision": "not_recorded_in_historical_config",
            },
            "entity_graph": {"legacy_machine_key": "graphrag", "human_name": "Entity-Co-occurrence Graph Retrieval"},
            "limitations": [
                "Original raw documents and exact historical YAML snapshots were not present in the archive.",
                "Unknown configuration fields remain explicit instead of being inferred.",
            ],
        }
        (configs / "historical_contract.json").write_text(
            json.dumps(historical_contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        chunks = load_jsonl(work / "data/chunks/chunks.jsonl")
        qa = load_jsonl(work / "data/queries/qa_dataset.jsonl")
        qrels = QRelsBuilder.load_qrels_tsv(work / "data/qrels/qrels.tsv")
        judgments = sum(len(value) for value in qrels.values())
        if (len(chunks), len(qa), judgments) != (1074, 100, 140):
            raise RuntimeError("Historical release cardinality gate failed")
        with (work / "indexes/bm25/bm25_index.pkl").open("rb") as handle:
            if len(pickle.load(handle)["meta"]) != 1074:
                raise RuntimeError("Historical BM25 index cardinality mismatch")
        import faiss
        if faiss.read_index(str(work / "indexes/faiss/faiss.index")).ntotal != 1074:
            raise RuntimeError("Historical FAISS index cardinality mismatch")
        graph_dir = work / "indexes/entity_graph"
        with (graph_dir / "graph.gpickle").open("rb") as handle:
            graph = pickle.load(handle)
        if len(graph.get("chunk_meta", {})) != 1074:
            raise RuntimeError("Historical entity graph cardinality mismatch")

        manifests = work / "manifests"
        manifests.mkdir()
        release_record = {
            "corpus_version": version,
            "documents": 120, "chunks": 1074, "queries": 100, "qrels": 140,
            "artifact_status": "immutable_historical_baseline",
            "config_provenance": "partially recovered; unknowns preserved explicitly",
        }
        (manifests / "release.json").write_text(
            json.dumps(release_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        command = [
            sys.executable, "scripts/release_manifest.py", "--base-dir", str(work),
            "--include-root", str(work / "data"), "--include-root", str(work / "indexes"),
            "--include-root", str(work / "runs"), "--include-root", str(work / "configs"),
            "--include-root", str(work / "manifests"),
            "--manifest", str(manifests / "release_manifest.jsonl"),
            "--sums", str(manifests / "SHA256SUMS"), "--version", version,
            "--chunk-count", "1074", "--query-count", "100",
            "--creation-command", "python scripts/archive_v2_release.py",
            "--config", str(configs / "historical_contract.json"),
        ]
        subprocess.run(command, cwd=ROOT, check=True)
        subprocess.run([*command, "--verify"], cwd=ROOT, check=True)
        if target.exists() and not args.replace:
            raise FileExistsError(f"Release already exists: {target}")
        backup = target.with_name(target.name + ".previous")
        shutil.rmtree(backup, ignore_errors=True)
        if target.exists():
            os.replace(target, backup)
        os.replace(work, target)
        shutil.rmtree(backup, ignore_errors=True)
        if args.publish_versioned:
            for name in ("cross_scheme_audit_v2.jsonl", "cross_scheme_audit_v2.md", "qa_validation_stats_v2.json"):
                source = target / "data/metadata" / name
                destination = ROOT / "data/metadata" / name
                temporary = destination.with_name(destination.name + ".archive-new")
                shutil.copy2(source, temporary)
                os.replace(temporary, destination)
        print(json.dumps({"published": str(target), **release_record}, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
