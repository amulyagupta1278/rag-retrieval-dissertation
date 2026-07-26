#!/usr/bin/env python3
"""Run frozen BM25 + corrected Graph v3.2 RRF fusion without relevance data."""

from __future__ import annotations

import argparse
import json
import shlex
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.retrievers.hybrid_rrf_v1 import fuse_rankings, validate_query_rows  # noqa: E402
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


EXPECTED_QUERY_IDS = {f"v2q-{index:03d}" for index in range(1, 35)}
EXPECTED_HASHES = {
    "config": "2989effa7d87ffb6c4a2a9e8d3c43b0f69e4cb9f3f97333e897374e927b27fbe",
    "bm25": "93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a",
    "graph": "68ad05ff4b600fa549f957b4bd44579af7e9d6addc2ddebff3f71a4584adc59a",
    "chunks": "70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6",
    "trace_decision": "356eed5c6de7271e3a19b352c1c5fed1a234d8c2ee0832a36c10e18f29e031e1",
}
REJECTED_GRAPH_HASHES = {
    "invalid_v1": "77a5d83bf2989602bc506175bb9ee569addf49bc1aa57af138cc283d8d5985df",
    "invalid_v3_1": "7b2e339a0865cd9ab7682ba8d309407ae97bb27bd862b5ad7fddf08f8f839d84",
}
APPROVED = {
    "config": ROOT / "configs/hybrid_rrf_v1_frozen.json",
    "bm25": ROOT / "runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl",
    "graph": ROOT / "runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl",
    "chunks": ROOT / "data/v2/pilot/chunks/chunks.jsonl",
    "trace_decision": ROOT / "audits/phase3_graph_v3_2/trace_validity_decision.json",
    "output": ROOT / "runs/v2/phase4_hybrid",
}
OUTPUTS = (
    "rankings/hybrid_top50.jsonl",
    "rankings/hybrid_top10.jsonl",
    "traces/fusion_traces.jsonl",
    "latency/fusion_overhead_samples.jsonl",
    "input_hashes.json",
    "fusion_manifest.json",
    "output_hashes.json",
)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read nonempty JSONL."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL input: {path}")
    return rows


def percentile(values: list[float], percentage: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), percentage))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in APPROVED:
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = {name: getattr(args, name).resolve() for name in APPROVED}
    expected_paths = {name: path.resolve() for name, path in APPROVED.items()}
    if paths != expected_paths:
        raise ValueError(f"Phase 4 fusion paths differ from approved paths: {paths}")
    collisions = [paths["output"] / relative for relative in OUTPUTS if (paths["output"] / relative).exists()]
    if collisions and not args.overwrite:
        raise FileExistsError(f"fusion output collision; pass --overwrite explicitly: {collisions}")

    input_hashes = {name: sha256_file(paths[name]) for name in EXPECTED_HASHES}
    if input_hashes != EXPECTED_HASHES:
        raise ValueError(f"frozen Phase 4 input hash mismatch: {input_hashes}")
    if input_hashes["graph"] in REJECTED_GRAPH_HASHES.values():
        raise ValueError("invalid Graph V1/v3.1 ranking hash rejected")
    trace_decision = json.loads(paths["trace_decision"].read_text(encoding="utf-8"))
    if trace_decision["status"] != "passed_trace_validity_gate" or trace_decision["invalid_query_ids"]:
        raise ValueError("corrected Graph v3.2 trace gate not passed")
    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    chunks = parse_jsonl(paths["chunks"])
    known_chunk_ids = {str(row["chunk_id"]) for row in chunks}
    if len(chunks) != 140 or len(known_chunk_ids) != 140:
        raise ValueError("frozen pilot corpus must contain 140 unique chunks")
    bm25 = validate_query_rows(
        parse_jsonl(paths["bm25"]), component="bm25", known_chunk_ids=known_chunk_ids,
        expected_query_ids=EXPECTED_QUERY_IDS,
    )
    graph = validate_query_rows(
        parse_jsonl(paths["graph"]), component="entity_graph_v3_2", known_chunk_ids=known_chunk_ids,
        expected_query_ids=EXPECTED_QUERY_IDS,
    )

    rankings50: list[dict[str, Any]] = []
    rankings10: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    overhead_samples: list[dict[str, Any]] = []
    for query_id in sorted(EXPECTED_QUERY_IDS):
        ranking, trace = fuse_rankings(bm25[query_id], graph[query_id], config=config, known_chunk_ids=known_chunk_ids)
        rankings50.append({"query_id": query_id, "ranking": ranking})
        rankings10.append({"query_id": query_id, "ranking": ranking[:10]})
        traces.append({"query_id": query_id, "items": trace})
        expected = stable_json((ranking, trace))
        fuse_rankings(bm25[query_id], graph[query_id], config=config, known_chunk_ids=known_chunk_ids)
        for repetition in range(1, 21):
            started = time.perf_counter_ns()
            repeated = fuse_rankings(bm25[query_id], graph[query_id], config=config, known_chunk_ids=known_chunk_ids)
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if stable_json(repeated) != expected:
                raise RuntimeError(f"nondeterministic fusion for {query_id}")
            overhead_samples.append({
                "sample_id": f"{query_id}-{repetition:02d}",
                "query_id": query_id,
                "repetition": repetition,
                "fusion_overhead_ms": elapsed_ms,
            })
    write_jsonl(paths["output"] / OUTPUTS[0], rankings50, key="query_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / OUTPUTS[1], rankings10, key="query_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / OUTPUTS[2], traces, key="query_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / OUTPUTS[3], overhead_samples, key="sample_id", overwrite=args.overwrite)
    input_record = {
        "scoring_inputs": {str(paths[name].relative_to(ROOT)): input_hashes[name] for name in ("config", "bm25", "graph", "chunks")},
        "validation_only_input": {str(paths["trace_decision"].relative_to(ROOT)): input_hashes["trace_decision"]},
        "approved_r5_qa_sha256_not_read_by_fusion": "0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b",
        "approved_r5_qrels_sha256_not_read_by_fusion": "d335e034b517a4fe8810c8d09584991f2553dd985a3140524d99d20bcdc3faf4",
        "explicitly_rejected_graph_hashes": REJECTED_GRAPH_HASHES,
    }
    write_json(paths["output"] / OUTPUTS[4], input_record, overwrite=args.overwrite)
    overheads = [row["fusion_overhead_ms"] for row in overhead_samples]
    raw_outputs = {
        str((paths["output"] / relative).relative_to(ROOT)): sha256_file(paths["output"] / relative)
        for relative in OUTPUTS[:5]
    }
    manifest = {
        "status": "fusion_only_pending_trace_gate",
        "system": config["system"],
        "configuration": config,
        "query_count": len(rankings50),
        "corpus_chunk_count": len(known_chunk_ids),
        "fusion_formula": "1/(60+rank_bm25) + 1/(60+rank_entity_graph_v3_2)",
        "raw_component_scores_used": False,
        "component_indexes_rebuilt": False,
        "relevance_inputs_read": False,
        "reference_answers_read": False,
        "query_categories_read": False,
        "prior_metrics_read": False,
        "owner_judgments_read": False,
        "blind_pool_relevance_read": False,
        "invalid_graph_artifacts_read": False,
        "determinism_verified": True,
        "exact_command": " ".join(shlex.quote(argument) for argument in sys.argv),
        "fusion_overhead_protocol": {
            "warmup_per_query": 1,
            "repetitions_per_query": 20,
            "sample_n": len(overheads),
            "mean_ms": statistics.mean(overheads),
            "median_ms": statistics.median(overheads),
            "p95_ms": percentile(overheads, 95),
            "stddev_ms": statistics.pstdev(overheads),
        },
        "code_hashes": {
            str(Path(__file__).relative_to(ROOT)): sha256_file(Path(__file__)),
            "src/retrievers/hybrid_rrf_v1.py": sha256_file(ROOT / "src/retrievers/hybrid_rrf_v1.py"),
        },
        "raw_output_hashes": raw_outputs,
    }
    write_json(paths["output"] / OUTPUTS[5], manifest, overwrite=args.overwrite)
    output_hashes = {
        **raw_outputs,
        str((paths["output"] / OUTPUTS[5]).relative_to(ROOT)): sha256_file(paths["output"] / OUTPUTS[5]),
    }
    write_json(paths["output"] / OUTPUTS[6], output_hashes, overwrite=args.overwrite)
    print(stable_json({
        "status": manifest["status"],
        "queries": len(rankings50),
        "empty_graph_queries": sum(not graph[query_id] for query_id in graph),
        "overhead": manifest["fusion_overhead_protocol"],
        "output_hashes": output_hashes,
    }))


if __name__ == "__main__":
    main()
