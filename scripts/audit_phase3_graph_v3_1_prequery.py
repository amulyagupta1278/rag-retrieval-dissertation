#!/usr/bin/env python3
"""Post-freeze checks that cannot influence v3.1 index or ranking."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.hashing import sha256_bytes, sha256_file  # noqa: E402


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tree_digest(path: Path) -> str:
    hashes = {str(file.relative_to(path)): sha256_file(file) for file in sorted(path.rglob("*")) if file.is_file()}
    return sha256_bytes(stable_json(hashes).encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qrels", type=Path, required=True)
    parser.add_argument("--chunk-entities", type=Path, required=True)
    parser.add_argument("--index-freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    qrels, chunk_entities_path, freeze_path, output = (path.resolve() for path in (args.qrels, args.chunk_entities, args.index_freeze, args.output))
    approved = (
        (ROOT / "data/v2/pilot/qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl").resolve(),
        (ROOT / "runs/v2/phase3_graph_v3_1/index/chunk_entities.json").resolve(),
        (ROOT / "runs/v2/phase3_graph_v3_1/index_freeze_manifest.json").resolve(),
        (ROOT / "audits/phase3_graph_v3_1/prequery_protected_and_gold_isolation.json").resolve(),
    )
    if (qrels, chunk_entities_path, freeze_path, output) != approved:
        raise ValueError("prequery audit requires approved frozen paths")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze["benchmark_queries_run"] != 0 or freeze["retrieval_metrics_present"] is not False:
        raise ValueError("index was not frozen before query use")
    chunk_entities = json.loads(chunk_entities_path.read_text(encoding="utf-8"))
    relevant_rows = [row for row in parse_jsonl(qrels) if int(row["relevance"]) > 0]
    gold_ids = sorted({str(row["chunk_id"]) for row in relevant_rows})
    missing = sorted(chunk_id for chunk_id in gold_ids if chunk_id not in chunk_entities)
    isolated = sorted(chunk_id for chunk_id in gold_ids if chunk_id in chunk_entities and not chunk_entities[chunk_id])
    if missing or isolated:
        raise RuntimeError(f"gold chunk isolation check failed; missing={missing}, isolated={isolated}")

    v1 = ROOT / "runs/v2/phase3_graph"
    v1_copy = ROOT / "runs/v2/phase3_graph_invalid_v1"
    v1_digest, copy_digest = tree_digest(v1), tree_digest(v1_copy)
    if v1_digest != copy_digest:
        raise RuntimeError("invalid V1 preserved trees differ")
    owner_path = ROOT / "audits/phase2b/owner_judgments.csv"
    with owner_path.open(newline="", encoding="utf-8") as handle:
        owner_rows = list(csv.DictReader(handle))
    owner_labels = sum(bool(row.get("owner_grade_2_1_0_U")) for row in owner_rows)
    if len(owner_rows) != 504 or owner_labels:
        raise RuntimeError("Phase2B owner package is not preserved blank")
    phase3f_freeze = json.loads((ROOT / "runs/v2/phase3_graph_v2/freeze_manifest.json").read_text(encoding="utf-8"))
    phase3f_actual = {
        "config": sha256_file(ROOT / "configs/entity_graph_v3_candidate.json"),
        "registry": sha256_file(ROOT / "data/v2/pilot/graph/entity_registry_v3.jsonl"),
        "chunk_entities": sha256_file(ROOT / "runs/v2/phase3_graph_v2/index/chunk_entities.json"),
        "edges": sha256_file(ROOT / "runs/v2/phase3_graph_v2/index/edges.jsonl"),
        "nodes": sha256_file(ROOT / "runs/v2/phase3_graph_v2/index/nodes.jsonl"),
    }
    phase3f_expected = {
        "config": phase3f_freeze["configuration_sha256"],
        "registry": phase3f_freeze["registry_sha256"],
        "chunk_entities": phase3f_freeze["artifact_hashes"]["runs/v2/phase3_graph_v2/index/chunk_entities.json"],
        "edges": phase3f_freeze["artifact_hashes"]["runs/v2/phase3_graph_v2/index/edges.jsonl"],
        "nodes": phase3f_freeze["artifact_hashes"]["runs/v2/phase3_graph_v2/index/nodes.jsonl"],
    }
    if phase3f_actual != phase3f_expected:
        raise RuntimeError("Phase3F candidate bytes changed")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != "50d7e13f65223da102877af1eee8e8c6fc993567":
        raise RuntimeError(f"protected commit changed: {head}")
    audit = {
        "status": "passed_prequery_gate",
        "separation": "qrels read only by this post-freeze isolation audit; never by index builder or retrieval ranker",
        "gold_isolation": {
            "qrels_path": str(qrels.relative_to(ROOT)),
            "qrels_sha256": sha256_file(qrels),
            "relevant_qrel_rows": len(relevant_rows),
            "unique_gold_chunk_count": len(gold_ids),
            "missing_gold_chunks": missing,
            "isolated_gold_chunks": isolated,
            "passed": not missing and not isolated,
        },
        "protected": {
            "head_commit": head,
            "phase3f": phase3f_actual,
            "phase3_invalid_v1_tree_sha256": v1_digest,
            "phase3_invalid_v1_copy_tree_sha256": copy_digest,
            "phase2b_owner_judgments_sha256": sha256_file(owner_path),
            "phase2b_rows": len(owner_rows),
            "phase2b_owner_labels": owner_labels,
            "bm25_faiss_run_tree_sha256": tree_digest(ROOT / "runs/v2/phase2a_r5_windowed"),
        },
        "index_freeze_sha256": sha256_file(freeze_path),
    }
    write_json(output, audit, overwrite=args.overwrite)
    print(stable_json(audit))


if __name__ == "__main__":
    main()
