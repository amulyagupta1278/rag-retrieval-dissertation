#!/usr/bin/env python3
"""Classify and verify preserved invalid Phase 3 V1 independently of V2 build."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.atomic_io import stable_json, write_json  # noqa: E402
from src.utils.hashing import sha256_bytes, sha256_file  # noqa: E402


APPROVED_SOURCE = (ROOT / "runs/v2/phase3_graph").resolve()
APPROVED_COPY = (ROOT / "runs/v2/phase3_graph_invalid_v1").resolve()
APPROVED_OUTPUT = (ROOT / "audits/phase3_graph_v2/invalid_v1_classification.json").resolve()
INVALID_SEEDS = ("and", "as", "in", "of", "it", "id", "iv", "vi", "na", "pm")


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def tree_digest(path: Path) -> tuple[str, dict[str, str]]:
    """Hash relative names and file bytes for a deterministic tree digest."""
    hashes = {str(file.relative_to(path)): sha256_file(file) for file in sorted(path.rglob("*")) if file.is_file()}
    return sha256_bytes(stable_json(hashes).encode("utf-8")), hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--invalid-copy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    source, invalid_copy, output = args.source_run.resolve(), args.invalid_copy.resolve(), args.output.resolve()
    if (source, invalid_copy, output) != (APPROVED_SOURCE, APPROVED_COPY, APPROVED_OUTPUT):
        raise ValueError("V1 classification must use approved preserved and audit paths")
    source_digest, source_hashes = tree_digest(source)
    copy_digest, copy_hashes = tree_digest(invalid_copy)
    if source_hashes != copy_hashes or source_digest != copy_digest:
        raise RuntimeError("invalid V1 copy is not byte-for-byte identical to preserved V1")

    traces = parse_jsonl(source / "traces/graph_traces.jsonl")
    seed_queries: dict[str, list[str]] = defaultdict(list)
    for trace in traces:
        for seed in trace.get("seed_entities", []):
            if seed in INVALID_SEEDS:
                seed_queries[seed].append(str(trace["query_id"]))
    missing = sorted(set(INVALID_SEEDS) - set(seed_queries))
    if missing:
        raise RuntimeError(f"expected invalid V1 seeds absent from preserved traces: {missing}")
    old_script = (ROOT / "scripts/run_phase3_graph.py").read_text(encoding="utf-8")
    required_snippets = (
        "if e in qtext",
        "if alias in qtext",
        "for q in qa:",
        "ACRONYM=re.compile",
        "PHRASE=re.compile",
    )
    absent_snippets = [snippet for snippet in required_snippets if snippet not in old_script]
    if absent_snippets:
        raise RuntimeError(f"preserved V1 implementation evidence changed: {absent_snippets}")
    pool_count = len(parse_jsonl(source / "pool/graph_unseen_blind.jsonl"))
    if pool_count != 275:
        raise RuntimeError(f"expected 275 invalid V1 pool candidates, found {pool_count}")

    evidence = {
        "status": "invalid_implementation_substring_matching_and_entity_pollution",
        "classification_basis": "methodology defects, not retrieval score",
        "preserved_paths": [
            "configs/graph_v2_frozen.json",
            "runs/v2/phase3_graph/",
            "audits/phase3/",
            "runs/v2/phase3_graph_invalid_v1/",
        ],
        "protected_hashes": {
            "configs/graph_v2_frozen.json": sha256_file(ROOT / "configs/graph_v2_frozen.json"),
            "audits/phase3/phase2b_preservation.json": sha256_file(ROOT / "audits/phase3/phase2b_preservation.json"),
        },
        "v1_run_tree_sha256": source_digest,
        "invalid_copy_tree_sha256": copy_digest,
        "byte_for_byte_copy_verified": True,
        "excluded_pool_candidate_count": pool_count,
        "pool_disposition": "preserved but excluded from every final judgment union",
        "invalidating_evidence": [
            {
                "defect": "stopword/common-token seeds",
                "artifact": "runs/v2/phase3_graph/traces/graph_traces.jsonl",
                "observed_seed_query_ids": {seed: sorted(query_ids) for seed, query_ids in sorted(seed_queries.items())},
            },
            {
                "defect": "raw entity substring matching",
                "artifact": "scripts/run_phase3_graph.py",
                "exact_code": "if e in qtext",
                "methodology_equivalent": "entity in query_text",
            },
            {
                "defect": "raw alias substring matching",
                "artifact": "scripts/run_phase3_graph.py",
                "exact_code": "if alias in qtext",
                "methodology_equivalent": "alias in query_text",
            },
            {
                "defect": "noisy regex extraction",
                "artifact": "scripts/run_phase3_graph.py",
                "exact_extractors": [
                    "ACRONYM=re.compile(r\"\\b[A-Z][A-Z0-9-]{1,}\\b\")",
                    "PHRASE=re.compile(r\"\\b[A-Z][A-Za-z&’'-]*(?:\\s+(?:[A-Z][A-Za-z&’'-]*|of|and|the)){1,5}\\b\")",
                ],
            },
            {
                "defect": "benchmark-derived entity leakage",
                "artifact": "scripts/run_phase3_graph.py",
                "exact_evidence": "for q in qa: gp=q.get('graph_path',{}); graph-path entities/aliases are added to metadata/aliases before chunk indexing",
            },
            {
                "defect": "generic bridge domination",
                "artifact": "runs/v2/phase3_graph/traces/graph_traces.jsonl",
                "evidence": "preserved traces contain the audited common-token seeds and paths through polluted regex entities",
            },
            {
                "defect": "inadequate correctness tests",
                "artifact": "tests/test_phase3_graph.py",
                "evidence": "V1 test checks frozen config and pool blinding only; matching, graph construction, and traversal formula are untested",
            },
        ],
    }
    write_json(output, evidence, overwrite=args.overwrite)
    print(stable_json({"status": evidence["status"], "tree_sha256": source_digest, "excluded_candidates": pool_count}))


if __name__ == "__main__":
    main()
