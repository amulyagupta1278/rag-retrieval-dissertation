#!/usr/bin/env python3
"""Evaluate frozen Graph v3.2 and expand the still-blind top-10 pool."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import re
import statistics
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_phase2a_bm25_faiss import METRICS, query_metrics  # noqa: E402
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


SEED = 42
BOOTSTRAPS = 10_000
SYSTEMS = ("bm25", "faiss_windowed_max", "entity_graph_v3_2")
CATEGORIES = ("entity_relation", "exact_lookup", "multi_hop", "paraphrase", "synthesis", "terminology")
FORBIDDEN_BLIND_FIELDS = {
    "system", "systems", "rank", "score", "current_gold", "gold", "relevance",
    "predicted_relevance", "contributions", "contributing_systems",
}
APPROVED = {
    "qa": ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl",
    "qrels": ROOT / "data/v2/pilot/qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl",
    "chunks": ROOT / "data/v2/pilot/chunks/chunks.jsonl",
    "documents": ROOT / "data/v2/pilot/extracted/documents.jsonl",
    "graph_ranking": ROOT / "runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl",
    "graph_traces": ROOT / "runs/v2/phase3_graph_v3_2/traces/graph_v3_2_full_traces.jsonl",
    "graph_edges": ROOT / "runs/v2/phase3_graph_v3_2/index/edges.jsonl",
    "graph_nodes": ROOT / "runs/v2/phase3_graph_v3_2/index/nodes.jsonl",
    "graph_chunk_entities": ROOT / "runs/v2/phase3_graph_v3_2/index/chunk_entities.json",
    "graph_registry": ROOT / "data/v2/pilot/graph/entity_registry_v3_2.jsonl",
    "graph_config": ROOT / "configs/entity_graph_v3_2_frozen.json",
    "graph_freeze": ROOT / "runs/v2/phase3_graph_v3_2/index_freeze_manifest.json",
    "graph_retrieval_manifest": ROOT / "runs/v2/phase3_graph_v3_2/retrieval_manifest.json",
    "graph_trace_decision": ROOT / "audits/phase3_graph_v3_2/trace_validity_decision.json",
    "bm25_ranking": ROOT / "runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl",
    "faiss_ranking": ROOT / "runs/v2/phase2a_r5_windowed/rankings/faiss_windowed_max_top50.jsonl",
    "baseline_blind_pool": ROOT / "runs/v2/phase2a_r5_windowed/pool/provisional_blind_top10.jsonl",
    "baseline_sealed_pool": ROOT / "runs/v2/phase2a_r5_windowed/pool/sealed_provenance.jsonl",
    "owner_judgments": ROOT / "audits/phase2b/owner_judgments.csv",
    "output": ROOT / "runs/v2/phase3_graph_v3_2",
    "audit_output": ROOT / "audits/phase3_graph_v3_2",
}
FROZEN_INPUT_HASHES = {
    "qa": "0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b",
    "qrels": "d335e034b517a4fe8810c8d09584991f2553dd985a3140524d99d20bcdc3faf4",
    "chunks": "70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6",
    "bm25_ranking": "93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a",
    "faiss_ranking": "7e419626d2e7d00efaedfa9f1ce0dda01760dbce5c901b214e992e32df597115",
    "graph_config": "7be005bef39b6fb971a130efc2470af80c67275ecc9ab7597a25f63ca82d0aea",
    "graph_registry": "725204c83a20d37d875419d888628970dfd80c511631b5b5c6bc158158876a34",
    "graph_freeze": "9195af5767cf9c637d614bc1845f56b56d5cc48d12e8e1236b277ba3e85ad8e0",
    "graph_nodes": "aa7fb60c6557c9b7ccc62ffae1d7c8d01345355f7bff7f5f27336408a32715a1",
    "graph_edges": "cd2203c233961d91c2deeb37ad8266ab0571e34942f628c97d4b5323e7741486",
    "graph_chunk_entities": "d42182a02696444e6ece314fea5ac45a4977e4ec39115ab51e6f4e2c8f24b6c6",
}
FROZEN_QUERY_ONLY_PATH = ROOT / "runs/v2/phase3_graph_v3_2/inputs/r5_queries_only.jsonl"
FROZEN_QUERY_ONLY_SHA256 = "c96270ffa4acc060a3a2eae4ab081bd8146230eece361e53d8e3d1af69494488"
OUTPUTS = (
    "metrics/balanced_known_gold_metrics.json",
    "metrics/per_query_metrics.jsonl",
    "statistics/paired_bootstrap_graph_vs_baselines.json",
    "failure_taxonomy_at_5_and_10.jsonl",
    "pool/provisional_blind_top10_bm25_faiss_graph_v3_2.jsonl",
    "pool/sealed_provenance_bm25_faiss_graph_v3_2.jsonl",
    "pool/design.json",
    "evaluation_manifest.json",
    "evaluation_hashes.json",
)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read nonempty JSONL rows."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL input: {path}")
    return rows


def validate_cli_paths(args: argparse.Namespace) -> dict[str, Path]:
    """Require exact frozen inputs and approved output roots."""
    paths = {name: getattr(args, name).resolve() for name in APPROVED}
    expected = {name: path.resolve() for name, path in APPROVED.items()}
    differences = {name: str(paths[name]) for name in paths if paths[name] != expected[name]}
    if differences:
        raise ValueError(f"paths differ from approved Phase 3G v3.2 paths: {differences}")
    collisions = [paths["output"] / relative for relative in OUTPUTS[:-1] if (paths["output"] / relative).exists()]
    collisions += [paths["audit_output"] / "evaluation_pool_integrity.json"] if (paths["audit_output"] / "evaluation_pool_integrity.json").exists() else []
    if collisions and not args.overwrite:
        raise FileExistsError(f"evaluation output collision; pass --overwrite explicitly: {collisions}")
    return paths


def validate_frozen_graph(paths: dict[str, Path]) -> dict[str, Any]:
    """Fail if any v3.2 freeze, retrieval, or trace-gate invariant changed."""
    for name, expected_hash in FROZEN_INPUT_HASHES.items():
        if sha256_file(paths[name]) != expected_hash:
            raise ValueError(f"frozen {name} bytes differ from expected SHA-256")
    if sha256_file(FROZEN_QUERY_ONLY_PATH) != FROZEN_QUERY_ONLY_SHA256:
        raise ValueError("frozen query-only R5 input bytes differ from expected SHA-256")
    freeze = json.loads(paths["graph_freeze"].read_text(encoding="utf-8"))
    retrieval = json.loads(paths["graph_retrieval_manifest"].read_text(encoding="utf-8"))
    decision = json.loads(paths["graph_trace_decision"].read_text(encoding="utf-8"))
    if freeze["status"] != "entity_graph_v3.2_frozen_before_queries" or freeze["benchmark_queries_run"] != 0:
        raise ValueError("Graph v3.2 index was not frozen before queries")
    if decision["status"] != "passed_trace_validity_gate":
        raise ValueError("Graph v3.2 trace gate did not pass")
    if decision["invalid_query_ids"] or decision["valid_trace_count"] != decision["inspected_trace_count"]:
        raise ValueError("Graph v3.2 trace gate contains invalid traces")
    graph_inputs = {
        str(paths[name].relative_to(ROOT)): sha256_file(paths[name])
        for name in ("graph_nodes", "graph_edges", "graph_chunk_entities")
    }
    for relative, digest in graph_inputs.items():
        if freeze["artifact_hashes"][relative] != digest:
            raise ValueError(f"frozen Graph artifact hash mismatch: {relative}")
    if freeze["registry_sha256"] != sha256_file(paths["graph_registry"]):
        raise ValueError("frozen Graph registry hash mismatch")
    if freeze["configuration_sha256"] != sha256_file(paths["graph_config"]):
        raise ValueError("frozen Graph configuration hash mismatch")
    if retrieval["graph_sha256"] != freeze["graph_sha256"]:
        raise ValueError("retrieval/freeze composite Graph hash mismatch")
    if retrieval["raw_artifact_hashes"][str(paths["graph_ranking"].relative_to(ROOT))] != sha256_file(paths["graph_ranking"]):
        raise ValueError("Graph v3.2 ranking hash mismatch")
    if retrieval["raw_artifact_hashes"][str(paths["graph_traces"].relative_to(ROOT))] != sha256_file(paths["graph_traces"]):
        raise ValueError("Graph v3.2 trace hash mismatch")
    return {"freeze": freeze, "retrieval": retrieval, "decision": decision}


def validate_benchmark(
    qa_rows: list[dict[str, Any]], qrel_rows: list[dict[str, Any]], chunks: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, int]], dict[str, dict[str, Any]]]:
    """Validate R5 query, direct-gold qrel, and chunk contracts."""
    qa = {str(row["question_id"]): row for row in qa_rows}
    chunk_map = {str(row["chunk_id"]): row for row in chunks}
    if len(qa_rows) != 34 or len(qa) != 34:
        raise ValueError("R5 must contain 34 unique queries")
    if len(chunks) != 140 or len(chunk_map) != 140:
        raise ValueError("pilot corpus must contain 140 unique chunks")
    category_counts = {category: 0 for category in CATEGORIES}
    for row in qa.values():
        category = str(row["category"])
        if category not in category_counts:
            raise ValueError(f"unknown category: {category}")
        category_counts[category] += 1
    if category_counts != {"entity_relation": 6, "exact_lookup": 6, "multi_hop": 6, "paraphrase": 6, "synthesis": 4, "terminology": 6}:
        raise ValueError(f"R5 category counts changed: {category_counts}")
    gains: dict[str, dict[str, int]] = defaultdict(dict)
    judgment_ids: set[str] = set()
    for row in qrel_rows:
        query_id, chunk_id = str(row["query_id"]), str(row["chunk_id"])
        relevance = row["relevance"]
        if query_id not in qa or chunk_id not in chunk_map:
            raise ValueError(f"unknown qrel reference: {query_id}:{chunk_id}")
        if type(relevance) is not int or relevance not in {0, 1, 2}:
            raise ValueError(f"malformed relevance for {query_id}:{chunk_id}: {relevance!r}")
        judgment_id = f"{query_id}:{chunk_id}"
        if judgment_id in judgment_ids:
            raise ValueError(f"duplicate qrel: {judgment_id}")
        judgment_ids.add(judgment_id)
        gains[query_id][chunk_id] = relevance
    if set(gains) != set(qa) or any(not any(value > 0 for value in values.values()) for values in gains.values()):
        raise ValueError("every R5 query must have at least one positive direct-gold qrel")
    if len(qrel_rows) != 48 or any(row["relevance"] != 2 for row in qrel_rows):
        raise ValueError("R5 direct-gold contract requires exactly 48 grade-2 qrels")
    return qa, dict(gains), chunk_map


def validate_rankings(
    rows: list[dict[str, Any]],
    qa: dict[str, dict[str, Any]],
    known_chunk_ids: set[str],
    system: str,
) -> dict[str, dict[str, Any]]:
    """Validate deterministic unique ranking rows against R5 query IDs."""
    by_query = {str(row["query_id"]): row for row in rows}
    if len(rows) != len(by_query) or set(by_query) != set(qa):
        raise ValueError(f"{system} ranking query set differs from R5")
    for query_id, row in by_query.items():
        ranking = row["ranking"]
        ids = [str(item["chunk_id"]) for item in ranking]
        ranks = [item["rank"] for item in ranking]
        if len(ids) != len(set(ids)) or ranks != list(range(1, len(ranking) + 1)):
            raise ValueError(f"{system} duplicate chunk or malformed ranks for {query_id}")
        unknown = sorted(set(ids) - known_chunk_ids)
        if unknown:
            raise ValueError(f"{system} ranking references unknown chunks for {query_id}: {unknown}")
    return by_query


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Macro-average each frozen retrieval metric over whole queries."""
    return {metric: statistics.mean(float(row["metrics"][metric]) for row in rows) for metric in METRICS}


def evaluate_system(
    system: str, rankings: dict[str, dict[str, Any]], qa: dict[str, dict[str, Any]], gains: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    """Compute per-query metrics in deterministic query order."""
    rows = []
    for query_id in sorted(qa):
        ranked = [str(item["chunk_id"]) for item in rankings[query_id]["ranking"]]
        rows.append({
            "row_id": f"{system}:{query_id}",
            "system": system,
            "query_id": query_id,
            "category": qa[query_id]["category"],
            "known_gold_ids": sorted(chunk_id for chunk_id, grade in gains[query_id].items() if grade > 0),
            "metrics": query_metrics(ranked, gains[query_id]),
            "top10": rankings[query_id]["ranking"][:10],
        })
    return rows


def panel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate and every-category macro panel."""
    return {
        "query_n": len(rows),
        "aggregate": aggregate(rows),
        "per_category": {
            category: {
                "query_n": len(subset := [row for row in rows if row["category"] == category]),
                "metrics": aggregate(subset),
            }
            for category in CATEGORIES
        },
    }


def percentile(values: np.ndarray, percentage: float) -> float:
    """Return NumPy's linear percentile as a plain float."""
    return float(np.percentile(values, percentage))


def paired_bootstrap(left: list[dict[str, Any]], right: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    """Bootstrap paired whole-query Graph-minus-baseline effects."""
    if [row["query_id"] for row in left] != [row["query_id"] for row in right]:
        raise ValueError("paired bootstrap query order mismatch")
    effects = np.asarray([
        float(graph["metrics"][metric]) - float(baseline["metrics"][metric])
        for graph, baseline in zip(left, right)
    ])
    rng = np.random.default_rng(SEED)
    means = np.empty(BOOTSTRAPS)
    for index in range(BOOTSTRAPS):
        means[index] = effects[rng.integers(0, len(effects), len(effects))].mean()
    return {
        "query_n": len(effects),
        "point_effect_graph_minus_baseline": float(effects.mean()),
        "ci95": [percentile(means, 2.5), percentile(means, 97.5)],
        "samples": BOOTSTRAPS,
        "seed": SEED,
        "unit": "whole query",
        "method": "paired nonparametric bootstrap percentile interval",
        "inference": "exploratory pilot; not final H3 evidence",
    }


def bootstrap_comparisons(evaluated: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Compare Graph with each frozen baseline for required slices."""
    slices = {
        "aggregate": lambda row: True,
        "entity_relation": lambda row: row["category"] == "entity_relation",
        "multi_hop": lambda row: row["category"] == "multi_hop",
    }
    graph = evaluated["entity_graph_v3_2"]
    output: dict[str, Any] = {
        "bootstrap_samples": BOOTSTRAPS,
        "seed": SEED,
        "unit": "whole query",
        "effect_direction": "entity_graph_v3_2 minus baseline",
        "inference": "exploratory pilot only; no final H3 verdict",
        "comparisons": {},
    }
    for baseline_name in ("bm25", "faiss_windowed_max"):
        baseline = evaluated[baseline_name]
        output["comparisons"][f"entity_graph_v3_2_vs_{baseline_name}"] = {}
        for slice_name, include in slices.items():
            graph_slice = [row for row in graph if include(row)]
            baseline_slice = [row for row in baseline if include(row)]
            output["comparisons"][f"entity_graph_v3_2_vs_{baseline_name}"][slice_name] = {
                metric: paired_bootstrap(graph_slice, baseline_slice, metric) for metric in METRICS
            }
    return output


def adjacency(edges: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Build undirected Graph adjacency matching frozen ranker traversal."""
    graph: dict[str, set[str]] = defaultdict(set)
    for row in edges:
        source, target = str(row["source"]), str(row["target"])
        graph[source].add(target)
        graph[target].add(source)
    return graph


def reachable_chunks(graph: dict[str, set[str]], seed_ids: list[str], maximum_distance: int = 2) -> set[str]:
    """Return chunks reachable from any seed within frozen two-hop cutoff."""
    reached: set[str] = set()
    for entity_id in seed_ids:
        start = f"entity:{entity_id}"
        queue: deque[tuple[str, int]] = deque([(start, 0)])
        visited = {start}
        while queue:
            node, distance = queue.popleft()
            if distance == maximum_distance:
                continue
            for neighbor in sorted(graph.get(node, set())):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                next_distance = distance + 1
                if neighbor.startswith("chunk:"):
                    reached.add(neighbor.removeprefix("chunk:"))
                else:
                    queue.append((neighbor, next_distance))
    return reached


def failure_taxonomy(
    graph_rows: list[dict[str, Any]], traces: dict[str, dict[str, Any]], edges: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Classify every Graph known-gold completeness miss at cutoffs 5 or 10."""
    graph = adjacency(edges)
    failures: list[dict[str, Any]] = []
    for row in graph_rows:
        metrics = row["metrics"]
        if metrics["complete_evidence_recall_at_5"] == 1.0 and metrics["complete_evidence_recall_at_10"] == 1.0:
            continue
        query_id = row["query_id"]
        trace = traces[query_id]
        rank_by_chunk = {item["chunk_id"]: item["rank"] for item in trace["ranking"]}
        gold = set(row["known_gold_ids"])
        top5 = {item["chunk_id"] for item in row["top10"][:5]}
        top10 = {item["chunk_id"] for item in row["top10"]}
        missing5, missing10 = sorted(gold - top5), sorted(gold - top10)
        seed_ids = [str(item["entity_id"]) for item in trace["matched_seeds"]]
        reachable = reachable_chunks(graph, seed_ids)
        if missing10:
            if not seed_ids:
                label = "no_valid_seed"
                rationale = "Trace records no valid seed; frozen Graph returns no zero-score fallback results."
            elif gold & top10:
                label = "incomplete_multi_evidence"
                rationale = "Top 10 contains some, but not all, direct-gold evidence chunks."
            elif set(missing10) & reachable:
                label = "valid_path_but_distractor_scored_higher"
                rationale = "At least one missed gold chunk is reachable within two hops, but does not enter top 10."
            else:
                label = "valid_seed_but_disconnected_gold_chunk"
                rationale = "Trace has valid seeds, but missed gold chunks are not reachable within frozen two-hop Graph."
        else:
            label = "known_gold_below_rank_5"
            rationale = "All direct-gold evidence enters top 10, but at least one item ranks below cutoff 5."
        failures.append({
            "failure_id": f"entity_graph_v3_2:{query_id}",
            "system": "entity_graph_v3_2",
            "query_id": query_id,
            "category": row["category"],
            "taxonomy": label,
            "rationale": rationale,
            "miss_at_5": bool(missing5),
            "miss_at_10": bool(missing10),
            "known_gold_ids": sorted(gold),
            "missed_gold_at_5": missing5,
            "missed_gold_at_10": missing10,
            "known_gold_saved_ranks": {chunk_id: rank_by_chunk.get(chunk_id) for chunk_id in sorted(gold)},
            "matched_seeds": [{
                "entity_id": item["entity_id"],
                "canonical_label": item["canonical_label"],
                "matched_query_span": item["matched_query_span"],
            } for item in trace["matched_seeds"]],
            "missed_gold_reachable_within_two_hops": sorted(set(missing5) & reachable),
            "top10_chunk_ids": [item["chunk_id"] for item in row["top10"]],
            "metric_snapshot": {
                "recall_at_5": metrics["recall_at_5"],
                "recall_at_10": metrics["recall_at_10"],
                "complete_evidence_recall_at_5": metrics["complete_evidence_recall_at_5"],
                "complete_evidence_recall_at_10": metrics["complete_evidence_recall_at_10"],
            },
        })
    expected = {
        row["query_id"] for row in graph_rows
        if row["metrics"]["complete_evidence_recall_at_5"] < 1.0
        or row["metrics"]["complete_evidence_recall_at_10"] < 1.0
    }
    if {row["query_id"] for row in failures} != expected:
        raise AssertionError("failure taxonomy does not cover every cutoff-5/10 completeness miss")
    summary = {
        "miss_definition": "Complete Evidence Recall@5 < 1 or Complete Evidence Recall@10 < 1 using R5 direct-gold qrels",
        "miss_query_n": len(failures),
        "miss_at_5_n": sum(row["miss_at_5"] for row in failures),
        "miss_at_10_n": sum(row["miss_at_10"] for row in failures),
        "taxonomy_counts": dict(sorted((label, sum(row["taxonomy"] == label for row in failures)) for label in {row["taxonomy"] for row in failures})),
        "scope": "trace-supported Graph v3.2 diagnostic; qrels are non-exhaustive",
    }
    return failures, summary


def next_candidate_numbers(blind: list[dict[str, Any]]) -> dict[str, int]:
    """Find next neutral display number per query without encoding system identity."""
    numbers: dict[str, int] = defaultdict(int)
    pattern = re.compile(r"-candidate-(\d+)$")
    for row in blind:
        match = pattern.search(str(row["display_id"]))
        if not match:
            raise ValueError(f"unexpected baseline display ID: {row['display_id']}")
        numbers[str(row["query_id"])] = max(numbers[str(row["query_id"])], int(match.group(1)))
    return numbers


def expand_blind_pool(
    baseline_blind: list[dict[str, Any]], baseline_sealed: list[dict[str, Any]],
    graph_rankings: dict[str, dict[str, Any]], qa: dict[str, dict[str, Any]],
    chunks: dict[str, dict[str, Any]], gains: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Add unseen valid-v3.2 top-10 pairs while keeping provenance sealed."""
    if len(baseline_blind) != 504 or len(baseline_sealed) != 504:
        raise ValueError("frozen baseline pool must contain 504 blind and 504 sealed rows")
    blind_by_id = {str(row["display_id"]): row for row in baseline_blind}
    sealed_by_id = {str(row["display_id"]): row for row in baseline_sealed}
    if len(blind_by_id) != 504 or set(blind_by_id) != set(sealed_by_id):
        raise ValueError("baseline blind/sealed display IDs duplicate or misaligned")
    if any(set(row) & FORBIDDEN_BLIND_FIELDS for row in baseline_blind):
        raise ValueError("baseline blind pool leaks sealed fields")
    existing_pairs = {(str(row["query_id"]), str(row["chunk_id"])) for row in baseline_sealed}
    if len(existing_pairs) != 504:
        raise ValueError("baseline pool contains duplicate query/chunk pairs")
    numbers = next_candidate_numbers(baseline_blind)
    new_blind: list[dict[str, Any]] = []
    new_sealed: list[dict[str, Any]] = []
    for query_id in sorted(qa):
        for item in graph_rankings[query_id]["ranking"][:10]:
            chunk_id = str(item["chunk_id"])
            pair = (query_id, chunk_id)
            if pair in existing_pairs:
                continue
            if chunk_id not in chunks:
                raise ValueError(f"Graph pool candidate references unknown chunk: {chunk_id}")
            existing_pairs.add(pair)
            numbers[query_id] += 1
            display_id = f"{query_id}-candidate-{numbers[query_id]:02d}"
            new_blind.append({
                "display_id": display_id,
                "query_id": query_id,
                "question": qa[query_id]["question"],
                "chunk_id": chunk_id,
                "chunk_text": chunks[chunk_id]["text"],
                "relevance_judgment": "",
                "reviewer_notes": "",
            })
            new_sealed.append({
                "display_id": display_id,
                "query_id": query_id,
                "chunk_id": chunk_id,
                "contributions": [{
                    "system": "entity_graph_v3_2",
                    "rank": int(item["rank"]),
                    "score": float(item["score"]),
                }],
                "current_gold": gains[query_id].get(chunk_id, 0) > 0,
            })
    expanded_blind = baseline_blind + new_blind
    expanded_sealed = baseline_sealed + new_sealed
    expanded_blind_by_id = {str(row["display_id"]): row for row in expanded_blind}
    expanded_sealed_by_id = {str(row["display_id"]): row for row in expanded_sealed}
    if len(expanded_blind_by_id) != len(expanded_blind) or set(expanded_blind_by_id) != set(expanded_sealed_by_id):
        raise ValueError("expanded blind/sealed display IDs duplicate or misaligned")
    for display_id, blind in expanded_blind_by_id.items():
        sealed = expanded_sealed_by_id[display_id]
        if (blind["query_id"], blind["chunk_id"]) != (sealed["query_id"], sealed["chunk_id"]):
            raise ValueError(f"blind/sealed pair mismatch: {display_id}")
        if set(blind) & FORBIDDEN_BLIND_FIELDS:
            raise ValueError(f"expanded blind pool leaks sealed fields: {display_id}")
        if blind["relevance_judgment"] or blind["reviewer_notes"]:
            raise ValueError(f"owner fields must remain blank: {display_id}")
    pair_count = len({(row["query_id"], row["chunk_id"]) for row in expanded_sealed})
    if pair_count != len(expanded_sealed):
        raise ValueError("expanded pool contains duplicate query/chunk pairs")
    design = {
        "status": "provisional_blind_pool_pending_hybrid_expansion_and_owner_judging",
        "baseline_pair_count": len(baseline_blind),
        "graph_v3_2_unseen_pair_count": len(new_blind),
        "expanded_pair_count": len(expanded_blind),
        "systems_included": ["bm25", "faiss_windowed_max", "entity_graph_v3_2"],
        "candidate_cutoff": 10,
        "deduplication_key": ["query_id", "chunk_id"],
        "source_graph_run": "frozen entity-graph-v3.2 only",
        "excluded_sources": ["phase3_graph_invalid_v1", "entity-graph-v3.1"],
        "repeated_pair_policy": "A pair independently returned by valid v3.2 is valid; no artifact or provenance from invalid V1/v3.1 is merged.",
        "blind_fields": sorted(expanded_blind[0]),
        "sealed_fields": sorted(expanded_sealed[0]),
        "hidden_from_owner": sorted(FORBIDDEN_BLIND_FIELDS),
        "owner_grades_completed": False,
        "original_504_files_modified": False,
        "final_qrels": False,
    }
    return expanded_blind, expanded_sealed, design


def seed_coverage(traces: dict[str, dict[str, Any]], qa: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Summarize valid seed presence overall and by every category."""
    def summarize(query_ids: list[str]) -> dict[str, Any]:
        seeded = [query_id for query_id in query_ids if traces[query_id]["matched_seeds"]]
        return {
            "query_n": len(query_ids),
            "seeded_query_n": len(seeded),
            "no_seed_query_n": len(query_ids) - len(seeded),
            "seed_coverage": len(seeded) / len(query_ids),
            "mean_matched_seeds_per_query": statistics.mean(len(traces[query_id]["matched_seeds"]) for query_id in query_ids),
        }
    all_ids = sorted(qa)
    return {
        "aggregate": summarize(all_ids),
        "per_category": {
            category: summarize([query_id for query_id in all_ids if qa[query_id]["category"] == category])
            for category in CATEGORIES
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in APPROVED:
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = validate_cli_paths(args)
    frozen = validate_frozen_graph(paths)
    input_hashes_before = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for name, path in paths.items() if name not in {"output", "audit_output"}
    }

    qa_rows, qrel_rows = parse_jsonl(paths["qa"]), parse_jsonl(paths["qrels"])
    chunks_rows, documents_rows = parse_jsonl(paths["chunks"]), parse_jsonl(paths["documents"])
    qa, gains, chunks = validate_benchmark(qa_rows, qrel_rows, chunks_rows)
    documents = {str(row["document_id"]): row for row in documents_rows}
    if len(documents) != len(documents_rows):
        raise ValueError("duplicate document IDs")
    ranking_inputs = {
        "bm25": parse_jsonl(paths["bm25_ranking"]),
        "faiss_windowed_max": parse_jsonl(paths["faiss_ranking"]),
        "entity_graph_v3_2": parse_jsonl(paths["graph_ranking"]),
    }
    rankings = {
        system: validate_rankings(rows, qa, set(chunks), system)
        for system, rows in ranking_inputs.items()
    }
    traces = {str(row["query_id"]): row for row in parse_jsonl(paths["graph_traces"])}
    if set(traces) != set(qa):
        raise ValueError("Graph trace query set differs from R5")

    evaluated = {system: evaluate_system(system, rankings[system], qa, gains) for system in SYSTEMS}
    per_query = [row for system in SYSTEMS for row in evaluated[system]]
    coverage = seed_coverage(traces, qa)
    metrics = {
        "status": "exploratory_pilot_known_gold_not_final_dissertation_evidence",
        "benchmark": "pilot-qa-v2-owner-approved-20260724-r5",
        "qrels_scope": "AI-assisted, owner-authorized, non-exhaustive direct-support qrels; all 48 current judgments have grade 2",
        "metric_labels": {
            "mrr_recall_hit_rate_complete_evidence_recall": "known-gold",
            "precision_at_5_and_10": "judged-gold precision with fixed denominator k",
            "binary_ndcg_at_10": "incomplete-pool binary nDCG@10",
            "graded_ndcg_at_10": "incomplete-pool graded nDCG@10 using linear qrel gains",
        },
        "metric_definitions": {
            "mrr_at_k": "Reciprocal rank of first relevance>0 chunk within top k; zero if absent.",
            "recall_at_k": "Distinct relevance>0 chunks retrieved within top k divided by known positive qrels.",
            "hit_rate_at_k": "One if any relevance>0 chunk occurs within top k; otherwise zero.",
            "precision_at_k": "Count of known relevance>0 chunks within top k divided by fixed k.",
            "binary_ndcg_at_10": "DCG@10 with gain 1 for relevance>0, normalized by ideal binary DCG.",
            "graded_ndcg_at_10": "DCG@10 with linear qrel gain, normalized by ideal graded DCG.",
            "complete_evidence_recall_at_k": "One only if every known relevance>0 chunk occurs within top k; otherwise zero.",
            "aggregation": "Unweighted macro mean across whole queries.",
        },
        "no_single_global_winner": True,
        "systems": {system: panel(evaluated[system]) for system in SYSTEMS},
        "graph_seed_coverage": coverage,
    }
    write_json(paths["output"] / OUTPUTS[0], metrics, overwrite=args.overwrite)
    write_jsonl(paths["output"] / OUTPUTS[1], per_query, key="row_id", overwrite=args.overwrite)
    write_json(paths["output"] / OUTPUTS[2], bootstrap_comparisons(evaluated), overwrite=args.overwrite)

    failures, failure_summary = failure_taxonomy(
        evaluated["entity_graph_v3_2"], traces, parse_jsonl(paths["graph_edges"]),
    )
    write_jsonl(paths["output"] / OUTPUTS[3], failures, key="failure_id", overwrite=args.overwrite)

    baseline_blind = parse_jsonl(paths["baseline_blind_pool"])
    baseline_sealed = parse_jsonl(paths["baseline_sealed_pool"])
    expanded_blind, expanded_sealed, pool_design = expand_blind_pool(
        baseline_blind, baseline_sealed, rankings["entity_graph_v3_2"], qa, chunks, gains,
    )
    write_jsonl(paths["output"] / OUTPUTS[4], expanded_blind, key="display_id", overwrite=args.overwrite)
    write_jsonl(paths["output"] / OUTPUTS[5], expanded_sealed, key="display_id", overwrite=args.overwrite)
    pool_design.update({
        "blind_sha256": sha256_file(paths["output"] / OUTPUTS[4]),
        "sealed_sha256": sha256_file(paths["output"] / OUTPUTS[5]),
    })
    write_json(paths["output"] / OUTPUTS[6], pool_design, overwrite=args.overwrite)

    latency = frozen["retrieval"]["latency_descriptive_only"]
    index_paths = [paths["graph_nodes"], paths["graph_edges"], paths["graph_chunk_entities"]]
    efficiency = {
        "latency_ms": {
            "mean": latency["mean_ms"], "median": latency["median_ms"], "p95": latency["p95_ms"],
            "sample_n": frozen["retrieval"]["latency_samples"],
            "warmup_query_n": frozen["retrieval"]["warmup_query_count"],
            "repetitions_per_query": frozen["retrieval"]["repetitions_per_query"],
        },
        "index_build_time_seconds": frozen["freeze"]["build_seconds"],
        "index_size_bytes": sum(path.stat().st_size for path in index_paths),
        "index_size_breakdown_bytes": {str(path.relative_to(ROOT)): path.stat().st_size for path in index_paths},
        "registry_size_bytes_reported_separately": paths["graph_registry"].stat().st_size,
        "timing_scope": "frozen retrieval-only run; descriptive, not inferential",
    }
    input_hashes_after = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for name, path in paths.items() if name not in {"output", "audit_output"}
    }
    if input_hashes_after != input_hashes_before:
        raise RuntimeError("a frozen input changed during evaluation")
    with paths["owner_judgments"].open(encoding="utf-8", newline="") as handle:
        owner_rows = list(csv.DictReader(handle))
    owner_blank = len(owner_rows) == 504 and all(
        not row["owner_grade_2_1_0_U"] and not row["owner_rationale"] for row in owner_rows
    )
    if not owner_blank:
        raise ValueError("Phase 2B owner judgment package is not sealed and blank")
    integrity = {
        "status": "passed",
        "blind_rows": len(expanded_blind),
        "sealed_rows": len(expanded_sealed),
        "baseline_rows_preserved": len(baseline_blind),
        "new_graph_v3_2_rows": pool_design["graph_v3_2_unseen_pair_count"],
        "unique_query_chunk_pairs": len({(row["query_id"], row["chunk_id"]) for row in expanded_sealed}),
        "blind_sealed_alignment": True,
        "forbidden_field_leaks": 0,
        "blank_owner_fields": len(expanded_blind),
        "owner_judgment_package_sha256": sha256_file(paths["owner_judgments"]),
        "invalid_v1_or_v3_1_artifacts_merged": False,
        "invalid_v1_or_v3_1_provenance_rows": 0,
        "graph_source_ranking_sha256": sha256_file(paths["graph_ranking"]),
    }
    integrity_path = paths["audit_output"] / "evaluation_pool_integrity.json"
    write_json(integrity_path, integrity, overwrite=args.overwrite)
    manifest = {
        "status": "corrected_graph_v3_2_metrics_and_provisional_pool_checkpoint",
        "inference": "exploratory pilot only; no final H3 verdict",
        "graph_configuration_modified": False,
        "hybrid_run": False,
        "generation_run": False,
        "benchmark_query_n": len(qa),
        "qrel_n": len(qrel_rows),
        "category_counts": {category: sum(row["category"] == category for row in qa.values()) for category in CATEGORIES},
        "seed_coverage": coverage,
        "efficiency": efficiency,
        "failure_taxonomy": failure_summary,
        "pool": pool_design,
        "input_hashes": input_hashes_before,
        "execution_provenance": {
            "command": [sys.executable, *sys.argv],
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "git_tree": subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip(),
            "git_status_porcelain": subprocess.check_output(["git", "status", "--porcelain=v1", "-uall"], cwd=ROOT, text=True).splitlines(),
            "platform": platform.platform(),
            "python": sys.version,
            "query_only_path": str(FROZEN_QUERY_ONLY_PATH.relative_to(ROOT)),
            "query_only_sha256": FROZEN_QUERY_ONLY_SHA256,
        },
        "outputs": {},
    }
    for relative in OUTPUTS[:7]:
        path = paths["output"] / relative
        manifest["outputs"][str(path.relative_to(ROOT))] = sha256_file(path)
    manifest["outputs"][str(integrity_path.relative_to(ROOT))] = sha256_file(integrity_path)
    write_json(paths["output"] / OUTPUTS[7], manifest, overwrite=args.overwrite)
    output_hashes = {
        **manifest["outputs"],
        str((paths["output"] / OUTPUTS[7]).relative_to(ROOT)): sha256_file(paths["output"] / OUTPUTS[7]),
    }
    write_json(paths["output"] / OUTPUTS[8], {
        "input_hashes": input_hashes_before,
        "output_hashes": output_hashes,
    }, overwrite=args.overwrite)
    print(stable_json({
        "status": manifest["status"],
        "graph_aggregate": metrics["systems"]["entity_graph_v3_2"]["aggregate"],
        "seed_coverage": coverage,
        "failure_summary": failure_summary,
        "pool": {key: pool_design[key] for key in ("baseline_pair_count", "graph_v3_2_unseen_pair_count", "expanded_pair_count")},
        "efficiency": efficiency,
    }))


if __name__ == "__main__":
    main()
