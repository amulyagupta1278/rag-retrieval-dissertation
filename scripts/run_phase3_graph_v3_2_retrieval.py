#!/usr/bin/env python3
"""Run frozen Graph v3.2 retrieval only; never read relevance/evaluation data."""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_phase3_graph_v2 import parse_jsonl  # noqa: E402
from src.retrievers.entity_graph_v3 import EntityMatcher, rank_query  # noqa: E402
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_bytes, sha256_file  # noqa: E402


APPROVED = {
    "config": (ROOT / "configs/entity_graph_v3_2_frozen.json").resolve(),
    "registry": (ROOT / "data/v2/pilot/graph/entity_registry_v3_2.jsonl").resolve(),
    "nodes": (ROOT / "runs/v2/phase3_graph_v3_2/index/nodes.jsonl").resolve(),
    "edges": (ROOT / "runs/v2/phase3_graph_v3_2/index/edges.jsonl").resolve(),
    "chunk_entities": (ROOT / "runs/v2/phase3_graph_v3_2/index/chunk_entities.json").resolve(),
    "freeze_manifest": (ROOT / "runs/v2/phase3_graph_v3_2/index_freeze_manifest.json").resolve(),
    "queries": (ROOT / "runs/v2/phase3_graph_v3_2/inputs/r5_queries_only.jsonl").resolve(),
    "output": (ROOT / "runs/v2/phase3_graph_v3_2").resolve(),
}
FROZEN_INPUT_HASHES = {
    "config": "7be005bef39b6fb971a130efc2470af80c67275ecc9ab7597a25f63ca82d0aea",
    "registry": "725204c83a20d37d875419d888628970dfd80c511631b5b5c6bc158158876a34",
    "nodes": "aa7fb60c6557c9b7ccc62ffae1d7c8d01345355f7bff7f5f27336408a32715a1",
    "edges": "cd2203c233961d91c2deeb37ad8266ab0571e34942f628c97d4b5323e7741486",
    "chunk_entities": "d42182a02696444e6ece314fea5ac45a4977e4ec39115ab51e6f4e2c8f24b6c6",
    "freeze_manifest": "9195af5767cf9c637d614bc1845f56b56d5cc48d12e8e1236b277ba3e85ad8e0",
    "queries": "c96270ffa4acc060a3a2eae4ab081bd8146230eece361e53d8e3d1af69494488",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--edges", type=Path, required=True)
    parser.add_argument("--chunk-entities", type=Path, required=True)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = {name: getattr(args, name).resolve() for name in APPROVED}
    if paths != APPROVED:
        differences = {name: str(paths[name]) for name in paths if paths[name] != APPROVED[name]}
        raise ValueError(f"retrieval paths differ from frozen approved paths: {differences}")
    for name, expected_hash in FROZEN_INPUT_HASHES.items():
        if sha256_file(paths[name]) != expected_hash:
            raise ValueError(f"frozen {name} bytes differ from expected SHA-256")
    output_files = [
        paths["output"] / "rankings/graph_v3_2_top50.jsonl",
        paths["output"] / "rankings/graph_v3_2_top10.jsonl",
        paths["output"] / "traces/graph_v3_2_full_traces.jsonl",
        paths["output"] / "latency/retrieval_samples.jsonl",
        paths["output"] / "retrieval_manifest.json",
        paths["output"] / "retrieval_hashes.json",
    ]
    if not args.overwrite:
        collisions = [path for path in output_files if path.exists()]
        if collisions:
            raise FileExistsError(f"retrieval output collision; pass --overwrite explicitly: {collisions}")

    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    freeze = json.loads(paths["freeze_manifest"].read_text(encoding="utf-8"))
    if freeze["status"] != "entity_graph_v3.2_frozen_before_queries" or freeze["benchmark_queries_run"] != 0:
        raise ValueError("index freeze does not precede query execution")
    if sha256_file(paths["config"]) != freeze["configuration_sha256"]:
        raise ValueError("configuration hash mismatch")
    if sha256_file(paths["registry"]) != freeze["registry_sha256"]:
        raise ValueError("registry hash mismatch")
    expected_artifacts = freeze["artifact_hashes"]
    for name in ("nodes", "edges", "chunk_entities"):
        relative = str(paths[name].relative_to(ROOT))
        if sha256_file(paths[name]) != expected_artifacts[relative]:
            raise ValueError(f"frozen {name} hash mismatch")
    graph_hashes = {
        str(paths[name].relative_to(ROOT)): sha256_file(paths[name])
        for name in ("chunk_entities", "edges", "nodes")
    }
    if sha256_bytes(stable_json(graph_hashes).encode("utf-8")) != freeze["graph_sha256"]:
        raise ValueError("composite Graph hash mismatch")

    queries = parse_jsonl(paths["queries"])
    if len(queries) != 34 or any(set(row) != {"query_id", "question"} for row in queries):
        raise ValueError("ranking input must contain exactly 34 ID/text-only query rows")
    if len({row["query_id"] for row in queries}) != 34:
        raise ValueError("duplicate query IDs")
    registry = parse_jsonl(paths["registry"])
    edges = parse_jsonl(paths["edges"])
    chunk_entities = json.loads(paths["chunk_entities"].read_text(encoding="utf-8"))
    n_chunks = len(chunk_entities)
    if n_chunks != 140:
        raise ValueError(f"expected 140 chunks, got {n_chunks}")
    matcher = EntityMatcher(registry)
    maximum_path = int(config["scoring"]["maximum_path_length_to_chunk"])
    hop_decay = float(config["scoring"]["hop_decay"])

    # Frozen warm-up protocol. Results discarded.
    for query in sorted(queries, key=lambda row: str(row["query_id"])):
        rank_query(
            query=str(query["question"]), matcher=matcher, edges=edges, n_chunks=n_chunks,
            maximum_path_length=maximum_path, hop_decay=hop_decay,
        )

    top50_rows: list[dict[str, Any]] = []
    top10_rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    latency_rows: list[dict[str, Any]] = []
    repetitions = int(config["retrieval_timing"]["repetitions_per_query"])
    for query in sorted(queries, key=lambda row: str(row["query_id"])):
        query_id, question = str(query["query_id"]), str(query["question"])
        ranking, trace = rank_query(
            query=question, matcher=matcher, edges=edges, n_chunks=n_chunks,
            maximum_path_length=maximum_path, hop_decay=hop_decay,
        )
        top50 = ranking[:50]
        top10 = ranking[:10]
        top50_rows.append({"query_id": query_id, "ranking": top50})
        top10_rows.append({"query_id": query_id, "ranking": top10})
        trace_ranking = []
        for row in top50:
            contributions = trace["contributions"].get(row["chunk_id"], [])
            reproduced = sum(float(item["contribution"]) for item in contributions)
            trace_ranking.append({
                "chunk_id": row["chunk_id"],
                "rank": row["rank"],
                "total_score": row["score"],
                "reproduced_score": reproduced,
                "paths": contributions,
            })
        traces.append({
            "query_id": query_id,
            "question": question,
            "status": trace["status"],
            "no_seed_reason": "no_valid_seed" if trace["status"] == "no_valid_seed" else "",
            "matched_seeds": trace["matched_seeds"],
            "ranking": trace_ranking,
        })
        canonical = stable_json(ranking)
        for repetition in range(1, repetitions + 1):
            started = time.perf_counter_ns()
            repeated_ranking, _ = rank_query(
                query=question, matcher=matcher, edges=edges, n_chunks=n_chunks,
                maximum_path_length=maximum_path, hop_decay=hop_decay,
            )
            elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
            if stable_json(repeated_ranking) != canonical:
                raise RuntimeError(f"nondeterministic ranking for {query_id}")
            latency_rows.append({
                "sample_id": f"{query_id}-{repetition:02d}",
                "query_id": query_id,
                "repetition": repetition,
                "latency_ms": elapsed_ms,
            })

    write_jsonl(paths["output"] / "rankings/graph_v3_2_top50.jsonl", top50_rows, key="query_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "rankings/graph_v3_2_top10.jsonl", top10_rows, key="query_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "traces/graph_v3_2_full_traces.jsonl", traces, key="query_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / "latency/retrieval_samples.jsonl", latency_rows, key="sample_id", overwrite=args.overwrite)
    raw_paths = output_files[:4]
    raw_hashes = {str(path.relative_to(ROOT)): sha256_file(path) for path in raw_paths}
    latencies = [row["latency_ms"] for row in latency_rows]
    manifest = {
        "status": "retrieval_only_frozen_pending_trace_audit",
        "system": "entity-graph-v3.2",
        "query_count": len(queries),
        "query_input_fields": ["query_id", "question"],
        "query_input_sha256": sha256_file(paths["queries"]),
        "index_freeze_sha256": sha256_file(paths["freeze_manifest"]),
        "configuration_sha256": sha256_file(paths["config"]),
        "registry_sha256": sha256_file(paths["registry"]),
        "graph_sha256": freeze["graph_sha256"],
        "ranking_code_sha256": sha256_file(Path(__file__)),
        "core_code_sha256": sha256_file(ROOT / "src/retrievers/entity_graph_v3.py"),
        "scoring": config["scoring"],
        "no_fallback": True,
        "zero_score_padding": False,
        "determinism_verified_across_repetitions": True,
        "warmup_query_count": len(queries),
        "repetitions_per_query": repetitions,
        "latency_samples": len(latency_rows),
        "latency_descriptive_only": {
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p95_ms": sorted(latencies)[max(0, int(0.95 * len(latencies)) - 1)],
        },
        "relevance_or_evaluation_inputs_read": False,
        "previous_rankings_or_metrics_read": False,
        "categories_read": False,
        "raw_artifact_hashes": raw_hashes,
        "execution_provenance": {
            "command": [sys.executable, *sys.argv],
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "git_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
            "git_status_porcelain": subprocess.check_output(["git", "status", "--porcelain=v1", "-uall"], cwd=ROOT, text=True).splitlines(),
            "platform": platform.platform(),
            "python": sys.version,
            "input_hashes": dict(sorted(FROZEN_INPUT_HASHES.items())),
        },
    }
    write_json(paths["output"] / "retrieval_manifest.json", manifest, overwrite=args.overwrite)
    final_hashes = {**raw_hashes, str((paths["output"] / "retrieval_manifest.json").relative_to(ROOT)): sha256_file(paths["output"] / "retrieval_manifest.json")}
    write_json(paths["output"] / "retrieval_hashes.json", final_hashes, overwrite=args.overwrite)
    print(stable_json({
        "status": manifest["status"],
        "queries": len(queries),
        "no_seed_queries": sum(trace["status"] == "no_valid_seed" for trace in traces),
        "latency_samples": len(latency_rows),
        "artifact_hashes": final_hashes,
    }))


if __name__ == "__main__":
    main()
