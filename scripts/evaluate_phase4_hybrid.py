#!/usr/bin/env python3
"""Gate, evaluate, time, and pool frozen Phase 4 Hybrid RRF results."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import re
import resource
import shlex
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.run_phase2a_bm25_faiss import METRICS, query_metrics, tokenize  # noqa: E402
from src.retrievers.entity_graph_v3 import EntityMatcher, rank_query  # noqa: E402
from src.retrievers.hybrid_rrf_v1 import fuse_rankings  # noqa: E402
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


NOTICE = "Metrics use non-exhaustive direct-support qrels. Unjudged relevant chunks may exist. Pilot results are exploratory and not final dissertation evidence."
SEED = 42
BOOTSTRAPS = 10_000
LATENCY_VALIDATION_QUERY_N = 34
LATENCY_ADDITIONAL_WARMUP_QUERY_N = 5
LATENCY_MEASURED_QUERY_N = 34
LATENCY_REPETITIONS_PER_QUERY = 20
LATENCY_MEASURED_SAMPLE_N = 680
LATENCY_EXECUTION_ORDER = [
    {"phase": "unmeasured_ranking_validation", "query_n": LATENCY_VALIDATION_QUERY_N},
    {"phase": "additional_unmeasured_warmup", "query_n": LATENCY_ADDITIONAL_WARMUP_QUERY_N},
    {
        "phase": "measured_repetitions",
        "query_n": LATENCY_MEASURED_QUERY_N,
        "repetitions_per_query": LATENCY_REPETITIONS_PER_QUERY,
        "sample_n": LATENCY_MEASURED_SAMPLE_N,
    },
]
CATEGORIES = ("entity_relation", "exact_lookup", "multi_hop", "paraphrase", "synthesis", "terminology")
TRACE_SELECTION = {
    "v2q-001": "exact_lookup", "v2q-002": "exact_lookup", "v2q-007": "terminology",
    "v2q-013": "paraphrase", "v2q-019": "entity_relation", "v2q-024": "entity_relation",
    "v2q-025": "multi_hop", "v2q-029": "multi_hop",
}
EXPECTED_PROTECTED_HASHES = {
    "qa": "0abd328ff639a05e80559202a018df0bd50aaf875f8d6b7753af925cc8a89c4b",
    "qrels": "d335e034b517a4fe8810c8d09584991f2553dd985a3140524d99d20bcdc3faf4",
    "chunks": "70c1e3b8b0380809adea000654333a5921132ab7608ff328a9fa7934e8f43aa6",
    "bm25": "93b42dc121927561bf880cbe44ccf264c60bac1196adac08ce3d6d5e80d2db6a",
    "graph": "68ad05ff4b600fa549f957b4bd44579af7e9d6addc2ddebff3f71a4584adc59a",
    "current_blind": "5ccc84c900fe1fe9c1f385fb0ff4154362293fe8391938c701b3436a3bb64c3b",
    "current_sealed": "2445cbbc1c6d0b0cdeceba0d71c8422d93e431ee592ad99a4eee1351b9faedd4",
    "owner_judgments": "2dc3f2534c806d06cbf8327eb1858684efa80734e6c63f0a4163600e4969d5ad",
    "graph_registry": "725204c83a20d37d875419d888628970dfd80c511631b5b5c6bc158158876a34",
    "graph_edges": "cd2203c233961d91c2deeb37ad8266ab0571e34942f628c97d4b5323e7741486",
    "graph_nodes": "aa7fb60c6557c9b7ccc62ffae1d7c8d01345355f7bff7f5f27336408a32715a1",
    "graph_chunk_entities": "d42182a02696444e6ece314fea5ac45a4977e4ec39115ab51e6f4e2c8f24b6c6",
    "graph_config": "7be005bef39b6fb971a130efc2470af80c67275ecc9ab7597a25f63ca82d0aea",
    "bm25_state": "057b06b2ed1f81ad533615a121691c09365eb53cc163ff7c1b0796e1a438c822",
    "bm25_provenance": "d00b6e735ec9deeb22b85152258abcff62a6f9100149919029d8822aa3bf7434",
}
APPROVED = {
    "config": ROOT / "configs/hybrid_rrf_v1_frozen.json",
    "bm25": ROOT / "runs/v2/phase2a_r5_windowed/rankings/bm25_top50.jsonl",
    "graph": ROOT / "runs/v2/phase3_graph_v3_2/rankings/graph_v3_2_top50.jsonl",
    "hybrid": ROOT / "runs/v2/phase4_hybrid/rankings/hybrid_top50.jsonl",
    "hybrid_top10": ROOT / "runs/v2/phase4_hybrid/rankings/hybrid_top10.jsonl",
    "fusion_traces": ROOT / "runs/v2/phase4_hybrid/traces/fusion_traces.jsonl",
    "fusion_manifest": ROOT / "runs/v2/phase4_hybrid/fusion_manifest.json",
    "fusion_hashes": ROOT / "runs/v2/phase4_hybrid/output_hashes.json",
    "chunks": ROOT / "data/v2/pilot/chunks/chunks.jsonl",
    "qa": ROOT / "data/v2/pilot/qa/pilot-qa-v2-owner-approved-20260724-r5.jsonl",
    "qrels": ROOT / "data/v2/pilot/qrels/pilot-qa-v2-owner-approved-20260724-r5.jsonl",
    "graph_traces": ROOT / "runs/v2/phase3_graph_v3_2/traces/graph_v3_2_full_traces.jsonl",
    "current_blind": ROOT / "runs/v2/phase3_graph_v3_2/pool/provisional_blind_top10_bm25_faiss_graph_v3_2.jsonl",
    "current_sealed": ROOT / "runs/v2/phase3_graph_v3_2/pool/sealed_provenance_bm25_faiss_graph_v3_2.jsonl",
    "owner_judgments": ROOT / "audits/phase2b/owner_judgments.csv",
    "bm25_state": ROOT / "runs/v2/phase2a/indexes/bm25/state.json",
    "bm25_provenance": ROOT / "runs/v2/phase2a/indexes/bm25/provenance.json",
    "graph_registry": ROOT / "data/v2/pilot/graph/entity_registry_v3_2.jsonl",
    "graph_edges": ROOT / "runs/v2/phase3_graph_v3_2/index/edges.jsonl",
    "graph_nodes": ROOT / "runs/v2/phase3_graph_v3_2/index/nodes.jsonl",
    "graph_chunk_entities": ROOT / "runs/v2/phase3_graph_v3_2/index/chunk_entities.json",
    "graph_config": ROOT / "configs/entity_graph_v3_2_frozen.json",
    "output": ROOT / "runs/v2/phase4_hybrid",
    "audit_output": ROOT / "audits/phase4_hybrid",
}
RUN_OUTPUTS = (
    "fusion_freeze_manifest.json",
    "metrics/balanced_known_gold_metrics.json",
    "metrics/per_query_metrics.jsonl",
    "statistics/paired_bootstrap_hybrid_vs_constituents.json",
    "failures/hybrid_failure_taxonomy.jsonl",
    "failures/worst_eight_queries.json",
    "latency/live_raw_samples.jsonl",
    "latency/live_summary.json",
    "metrics/rrf_k_robustness.json",
    "pool/provisional_blind_top10_bm25_faiss_graph_hybrid.jsonl",
    "pool/sealed_provenance_bm25_faiss_graph_hybrid.jsonl",
    "pool/design.json",
    "commands.json",
    "evaluation_manifest.json",
    "evaluation_hashes.json",
)
AUDIT_OUTPUTS = (
    "eight_fusion_trace_audit.jsonl",
    "trace_validity_decision.json",
    "pool_integrity.json",
    "protected_artifact_integrity.json",
)


def parse_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL input: {path}")
    return rows


def percentile(values: list[float] | np.ndarray, percentage: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), percentage))


def validate_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {name: getattr(args, name).resolve() for name in APPROVED}
    expected = {name: path.resolve() for name, path in APPROVED.items()}
    if paths != expected:
        raise ValueError(f"Phase 4 evaluation paths differ from approved paths: {paths}")
    collisions = [paths["output"] / relative for relative in RUN_OUTPUTS if (paths["output"] / relative).exists()]
    collisions += [paths["audit_output"] / relative for relative in AUDIT_OUTPUTS if (paths["audit_output"] / relative).exists()]
    if collisions and not args.overwrite:
        raise FileExistsError(f"evaluation output collision; pass --overwrite explicitly: {collisions}")
    return paths


def rows_by_query(path: Path) -> dict[str, dict[str, Any]]:
    rows = parse_jsonl(path)
    output = {str(row["query_id"]): row for row in rows}
    if len(output) != len(rows) or set(output) != {f"v2q-{index:03d}" for index in range(1, 35)}:
        raise ValueError(f"query set mismatch or duplicate in {path}")
    return output


def trace_gate(paths: dict[str, Path], config: dict[str, Any]) -> dict[str, Any]:
    """Audit eight traces before any QA/qrel file is read."""
    bm25, graph = rows_by_query(paths["bm25"]), rows_by_query(paths["graph"])
    hybrid, traces = rows_by_query(paths["hybrid"]), rows_by_query(paths["fusion_traces"])
    manifest = json.loads(paths["fusion_manifest"].read_text(encoding="utf-8"))
    recorded_hashes = json.loads(paths["fusion_hashes"].read_text(encoding="utf-8"))
    for relative, expected in recorded_hashes.items():
        if sha256_file(ROOT / relative) != expected:
            raise ValueError(f"fusion artifact hash mismatch before trace gate: {relative}")
    if manifest["status"] != "fusion_only_pending_trace_gate" or manifest["relevance_inputs_read"]:
        raise ValueError("fusion manifest violates pre-evaluation boundary")
    audits = []
    aggregate_conditions = Counter()
    for query_id, category in TRACE_SELECTION.items():
        bm_rank = {item["chunk_id"]: item["rank"] for item in bm25[query_id]["ranking"]}
        graph_rank = {item["chunk_id"]: item["rank"] for item in graph[query_id]["ranking"]}
        hybrid_ranking = hybrid[query_id]["ranking"]
        trace_items = traces[query_id]["items"]
        checks = {
            "formula_reproduced": True,
            "raw_scores_absent": True,
            "equal_weighting": config["weights"] == {"bm25": 1.0, "entity_graph_v3_2": 1.0},
            "input_ranks_match": True,
            "missing_list_handling_correct": True,
            "tie_break_deterministic": True,
            "no_duplicate_chunks": len({item["chunk_id"] for item in hybrid_ranking}) == len(hybrid_ranking),
            "invalid_graph_artifact_absent": not manifest["invalid_graph_artifacts_read"],
        }
        for rank, (result, item) in enumerate(zip(hybrid_ranking, trace_items), 1):
            chunk_id = item["chunk_id"]
            expected_bm = 1 / (60 + bm_rank[chunk_id]) if chunk_id in bm_rank else 0.0
            expected_graph = 1 / (60 + graph_rank[chunk_id]) if chunk_id in graph_rank else 0.0
            checks["formula_reproduced"] &= abs(item["bm25_rrf_contribution"] - expected_bm) < 1e-15
            checks["formula_reproduced"] &= abs(item["graph_rrf_contribution"] - expected_graph) < 1e-15
            checks["formula_reproduced"] &= abs(item["total_rrf_score"] - expected_bm - expected_graph) < 1e-15
            checks["formula_reproduced"] &= result["score"] == item["total_rrf_score"] and result["rank"] == rank == item["final_hybrid_rank"]
            checks["raw_scores_absent"] &= not ({"bm25_score", "graph_score", "raw_score"} & set(item))
            checks["input_ranks_match"] &= item["bm25_rank"] == bm_rank.get(chunk_id) and item["graph_rank"] == graph_rank.get(chunk_id)
            checks["missing_list_handling_correct"] &= (item["bm25_rank"] is not None or item["bm25_rrf_contribution"] == 0)
            checks["missing_list_handling_correct"] &= (item["graph_rank"] is not None or item["graph_rrf_contribution"] == 0)
            if item["tie_break"] == "chunk_id_ascending":
                checks["tie_break_deterministic"] &= item["tied_chunk_ids"] == sorted(item["tied_chunk_ids"])
        common = set(bm_rank) & set(graph_rank)
        conditions = {
            "graph_has_results": bool(graph_rank),
            "graph_empty": not graph_rank,
            "both_retrieve_same_chunk": bool(common),
            "bm25_only_chunk": bool(set(bm_rank) - set(graph_rank)),
            "graph_only_chunk": bool(set(graph_rank) - set(bm_rank)),
            "strong_component_disagreement": any(abs(bm_rank[chunk_id] - graph_rank[chunk_id]) >= 10 for chunk_id in common),
        }
        aggregate_conditions.update({key: int(value) for key, value in conditions.items()})
        audits.append({
            "query_id": query_id,
            "category": category,
            "checks": checks,
            "conditions": conditions,
            "bm25_result_n": len(bm_rank),
            "graph_result_n": len(graph_rank),
            "hybrid_result_n": len(hybrid_ranking),
            "trace_valid": all(checks.values()),
        })
    category_counts = Counter(TRACE_SELECTION.values())
    required_categories = category_counts == Counter({"exact_lookup": 2, "terminology": 1, "paraphrase": 1, "entity_relation": 2, "multi_hop": 2})
    required_conditions = all(aggregate_conditions[key] > 0 for key in (
        "graph_has_results", "graph_empty", "both_retrieve_same_chunk", "bm25_only_chunk",
        "graph_only_chunk", "strong_component_disagreement",
    ))
    passed = all(row["trace_valid"] for row in audits) and required_categories and required_conditions
    write_jsonl(paths["audit_output"] / AUDIT_OUTPUTS[0], audits, key="query_id", overwrite=args_global.overwrite)
    decision = {
        "status": "passed_fusion_trace_gate" if passed else "failed_fusion_trace_gate",
        "inspected_query_ids": sorted(TRACE_SELECTION),
        "inspected_trace_count": len(audits),
        "valid_trace_count": sum(row["trace_valid"] for row in audits),
        "invalid_query_ids": [row["query_id"] for row in audits if not row["trace_valid"]],
        "category_counts": dict(sorted(category_counts.items())),
        "required_conditions_covered": dict(sorted(aggregate_conditions.items())),
        "configuration_sha256": sha256_file(paths["config"]),
        "hybrid_top50_sha256": sha256_file(paths["hybrid"]),
        "fusion_traces_sha256": sha256_file(paths["fusion_traces"]),
        "metrics_calculated_at_gate_time": False,
        "fusion_run_preserved": True,
    }
    write_json(paths["audit_output"] / AUDIT_OUTPUTS[1], decision, overwrite=args_global.overwrite)
    if not passed:
        raise RuntimeError(f"fusion trace gate failed; metrics prohibited: {decision}")
    freeze = {
        "status": "hybrid_rankings_frozen_after_trace_gate_before_qrels",
        "configuration_sha256": sha256_file(paths["config"]),
        "fusion_manifest_sha256": sha256_file(paths["fusion_manifest"]),
        "trace_decision_sha256": sha256_file(paths["audit_output"] / AUDIT_OUTPUTS[1]),
        "ranking_hashes": {
            str(paths["hybrid"].relative_to(ROOT)): sha256_file(paths["hybrid"]),
            str(paths["hybrid_top10"].relative_to(ROOT)): sha256_file(paths["hybrid_top10"]),
            str(paths["fusion_traces"].relative_to(ROOT)): sha256_file(paths["fusion_traces"]),
        },
        "qrels_read_before_freeze": False,
    }
    write_json(paths["output"] / RUN_OUTPUTS[0], freeze, overwrite=args_global.overwrite)
    return decision


def load_benchmark(paths: dict[str, Path]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, int]], dict[str, dict[str, Any]]]:
    qa_rows, qrel_rows, chunk_rows = parse_jsonl(paths["qa"]), parse_jsonl(paths["qrels"]), parse_jsonl(paths["chunks"])
    qa = {row["question_id"]: row for row in qa_rows}
    chunks = {row["chunk_id"]: row for row in chunk_rows}
    if len(qa) != len(qa_rows) != 34 or len(qa) != 34:
        raise ValueError("R5 must contain 34 unique queries")
    if len(chunks) != 140:
        raise ValueError("pilot corpus must contain 140 unique chunks")
    gains: dict[str, dict[str, int]] = defaultdict(dict)
    for row in qrel_rows:
        query_id, chunk_id, relevance = row["query_id"], row["chunk_id"], row["relevance"]
        if query_id not in qa or chunk_id not in chunks or type(relevance) is not int or relevance not in {0, 1, 2}:
            raise ValueError(f"malformed qrel: {row}")
        if chunk_id in gains[query_id]:
            raise ValueError(f"duplicate qrel: {query_id}:{chunk_id}")
        gains[query_id][chunk_id] = relevance
    if len(qrel_rows) != 48 or set(gains) != set(qa) or any(row["relevance"] != 2 for row in qrel_rows):
        raise ValueError("R5 requires 48 direct grade-2 qrels covering all queries")
    counts = Counter(row["category"] for row in qa_rows)
    if counts != Counter({"exact_lookup": 6, "terminology": 6, "paraphrase": 6, "entity_relation": 6, "multi_hop": 6, "synthesis": 4}):
        raise ValueError(f"R5 category counts changed: {counts}")
    return qa, dict(gains), chunks


def evaluate(
    system: str, ranking_rows: dict[str, dict[str, Any]], qa: dict[str, dict[str, Any]], gains: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    output = []
    for query_id in sorted(qa):
        ranking = ranking_rows[query_id]["ranking"]
        output.append({
            "row_id": f"{system}:{query_id}",
            "system": system,
            "query_id": query_id,
            "category": qa[query_id]["category"],
            "known_gold_ids": sorted(chunk_id for chunk_id, relevance in gains[query_id].items() if relevance > 0),
            "metrics": query_metrics([item["chunk_id"] for item in ranking], gains[query_id]),
            "top10": ranking[:10],
        })
    return output


def aggregate(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {metric: statistics.mean(row["metrics"][metric] for row in rows) for metric in METRICS}


def panel(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "aggregate": {"notice": NOTICE, "query_n": len(rows), "metrics": aggregate(rows)},
        "per_category": {
            category: {"notice": NOTICE, "query_n": len(subset := [row for row in rows if row["category"] == category]), "metrics": aggregate(subset)}
            for category in CATEGORIES
        },
    }


def paired_bootstrap(hybrid: list[dict[str, Any]], comparator: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    if [row["query_id"] for row in hybrid] != [row["query_id"] for row in comparator]:
        raise ValueError("paired bootstrap query order mismatch")
    effects = np.asarray([left["metrics"][metric] - right["metrics"][metric] for left, right in zip(hybrid, comparator)], dtype=float)
    rng = np.random.default_rng(SEED)
    samples = np.empty(BOOTSTRAPS)
    for index in range(BOOTSTRAPS):
        samples[index] = effects[rng.integers(0, len(effects), len(effects))].mean()
    return {
        "query_n": len(effects),
        "point_effect_hybrid_minus_comparator": float(effects.mean()),
        "ci95": [percentile(samples, 2.5), percentile(samples, 97.5)],
        "uncertainty_includes_zero": percentile(samples, 2.5) <= 0 <= percentile(samples, 97.5),
        "samples": BOOTSTRAPS,
        "seed": SEED,
        "unit": "whole query",
        "inference": "exploratory pilot; no final H4 verdict",
    }


def comparison_panel(hybrid: list[dict[str, Any]], comparator: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "aggregate": {metric: paired_bootstrap(hybrid, comparator, metric) for metric in METRICS},
        "per_category": {
            category: {
                metric: paired_bootstrap(
                    [row for row in hybrid if row["category"] == category],
                    [row for row in comparator if row["category"] == category], metric,
                ) for metric in METRICS
            } for category in CATEGORIES
        },
    }


class FrozenBM25:
    """Load persisted BM25 state; never tokenize corpus or rebuild index."""

    def __init__(self, state: dict[str, Any], provenance: dict[str, Any]) -> None:
        self.chunk_ids = list(state["chunk_ids"])
        self.doc_freqs = [Counter(tokens) for tokens in state["tokenized_corpus"]]
        self.doc_lengths = np.asarray(state["document_lengths"], dtype=float)
        self.average_length = float(state["average_document_length"])
        self.idf = state["idf"]
        self.k1, self.b = float(provenance["k1"]), float(provenance["b"])

    def rank(self, query: str) -> list[dict[str, Any]]:
        scores = np.zeros(len(self.chunk_ids), dtype=float)
        for term in tokenize(query):
            frequency = np.asarray([document.get(term, 0) for document in self.doc_freqs], dtype=float)
            scores += (self.idf.get(term, 0) or 0) * (
                frequency * (self.k1 + 1)
                / (frequency + self.k1 * (1 - self.b + self.b * self.doc_lengths / self.average_length))
            )
        order = sorted(range(len(self.chunk_ids)), key=lambda index: (-float(scores[index]), self.chunk_ids[index]))[:50]
        return [{"chunk_id": self.chunk_ids[index], "rank": rank, "score": float(scores[index])} for rank, index in enumerate(order, 1)]


def summarize(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values), "mean_ms": statistics.mean(values), "median_ms": statistics.median(values),
        "p95_ms": percentile(values, 95), "stddev_ms": statistics.pstdev(values),
    }


def measure_latency(
    paths: dict[str, Path], config: dict[str, Any], qa: dict[str, dict[str, Any]], chunks: dict[str, dict[str, Any]],
    frozen_rankings: dict[str, dict[str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Measure live BM25, Graph, fusion, sequential total, and parallel estimate."""
    bm25 = FrozenBM25(
        json.loads(paths["bm25_state"].read_text(encoding="utf-8")),
        json.loads(paths["bm25_provenance"].read_text(encoding="utf-8")),
    )
    graph_config = json.loads(paths["graph_config"].read_text(encoding="utf-8"))
    matcher = EntityMatcher(parse_jsonl(paths["graph_registry"]))
    edges = parse_jsonl(paths["graph_edges"])
    n_chunks = len(chunks)

    def run_query(query_id: str) -> tuple[dict[str, float], list[dict[str, Any]]]:
        question = qa[query_id]["question"]
        total_started = time.perf_counter_ns()
        started = time.perf_counter_ns()
        bm_ranking = bm25.rank(question)
        bm_ms = (time.perf_counter_ns() - started) / 1_000_000
        started = time.perf_counter_ns()
        graph_ranking, _ = rank_query(
            query=question, matcher=matcher, edges=edges, n_chunks=n_chunks,
            maximum_path_length=graph_config["scoring"]["maximum_path_length_to_chunk"],
            hop_decay=graph_config["scoring"]["hop_decay"],
        )
        graph_ms = (time.perf_counter_ns() - started) / 1_000_000
        started = time.perf_counter_ns()
        hybrid_ranking, _ = fuse_rankings(bm_ranking[:50], graph_ranking[:50], config=config, known_chunk_ids=set(chunks))
        fusion_ms = (time.perf_counter_ns() - started) / 1_000_000
        sequential_ms = (time.perf_counter_ns() - total_started) / 1_000_000
        return {
            "bm25_retrieval_ms": bm_ms,
            "graph_retrieval_ms": graph_ms,
            "rrf_fusion_overhead_ms": fusion_ms,
            "sequential_end_to_end_ms": sequential_ms,
            "parallel_critical_path_estimate_ms": max(bm_ms, graph_ms) + fusion_ms,
        }, hybrid_ranking

    query_ids = sorted(qa)
    if len(query_ids) != LATENCY_VALIDATION_QUERY_N:
        raise ValueError(f"latency protocol requires {LATENCY_VALIDATION_QUERY_N} validation queries")
    for query_id in query_ids:
        timing, live_hybrid = run_query(query_id)
        del timing
        live_bm = bm25.rank(qa[query_id]["question"])
        live_graph, _ = rank_query(
            query=qa[query_id]["question"], matcher=matcher, edges=edges, n_chunks=n_chunks,
            maximum_path_length=graph_config["scoring"]["maximum_path_length_to_chunk"],
            hop_decay=graph_config["scoring"]["hop_decay"],
        )
        if [row["chunk_id"] for row in live_bm] != [row["chunk_id"] for row in frozen_rankings["bm25"][query_id]["ranking"]]:
            raise RuntimeError(f"live BM25 differs from frozen ranking for {query_id}")
        if stable_json(live_graph[:50]) != stable_json(frozen_rankings["entity_graph_v3_2"][query_id]["ranking"]):
            raise RuntimeError(f"live Graph differs from frozen ranking for {query_id}")
        if stable_json(live_hybrid) != stable_json(frozen_rankings["hybrid_bm25_graph_rrf"][query_id]["ranking"]):
            raise RuntimeError(f"live Hybrid differs from frozen ranking for {query_id}")
    for query_id in query_ids[:LATENCY_ADDITIONAL_WARMUP_QUERY_N]:
        run_query(query_id)
    samples = []
    for repetition in range(1, LATENCY_REPETITIONS_PER_QUERY + 1):
        for query_id in query_ids:
            timing, live_hybrid = run_query(query_id)
            if stable_json(live_hybrid) != stable_json(frozen_rankings["hybrid_bm25_graph_rrf"][query_id]["ranking"]):
                raise RuntimeError(f"nondeterministic live Hybrid result for {query_id}")
            samples.append({"sample_id": f"{repetition:02d}-{query_id}", "query_id": query_id, "repetition": repetition, **timing})
    if len(samples) != LATENCY_MEASURED_SAMPLE_N:
        raise RuntimeError(f"latency sample count differs from frozen protocol: {len(samples)}")
    timing_keys = [key for key in samples[0] if key.endswith("_ms")]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    graph_index_paths = [paths[name] for name in ("graph_nodes", "graph_edges", "graph_chunk_entities", "graph_registry", "graph_config")]
    bm25_index_paths = [paths["bm25_state"], paths["bm25_provenance"]]
    summary = {
        "protocol": {
            "execution_order": LATENCY_EXECUTION_ORDER,
            "validation_warmup_query_n": LATENCY_VALIDATION_QUERY_N,
            "additional_warmup_query_n": LATENCY_ADDITIONAL_WARMUP_QUERY_N,
            "measured_query_n": LATENCY_MEASURED_QUERY_N,
            "repetitions_per_query": LATENCY_REPETITIONS_PER_QUERY,
            "measured_sample_n": len(samples),
            "query_order": "query_id ascending inside each repetition",
            "cache_condition": "warm persisted-index/cache operational conditions",
            "cache_flushing_performed": False,
            "cold_start_latency": False,
            "batch_size": 1,
            "component_indexes_rebuilt": False,
            "validation_invocations": {
                "combined_run_query_call_n": 34,
                "combined_bm25_retrieval_call_n": 34,
                "combined_graph_retrieval_call_n": 34,
                "combined_rrf_fusion_call_n": 34,
                "separate_bm25_validation_call_n": 34,
                "separate_graph_validation_call_n": 34,
                "total_bm25_calls_before_additional_warmup": 68,
                "total_graph_calls_before_additional_warmup": 68,
                "total_rrf_fusion_calls_before_additional_warmup": 34
            },
        },
        "timings": {key: summarize([row[key] for row in samples]) for key in timing_keys},
        "h4_latency_endpoint": "measured sequential_end_to_end_ms",
        "parallel_value_status": "estimate only; max(BM25, Graph) + measured RRF overhead",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "thread_environment": {key: os.getenv(key) for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")},
        "index_size_bytes": {
            "bm25_persisted_state_and_provenance": sum(path.stat().st_size for path in bm25_index_paths),
            "graph_v3_2_index_registry_and_config": sum(path.stat().st_size for path in graph_index_paths),
            "hybrid_additional_index": 0,
        },
        "process_peak_rss_bytes": int(rss if sys.platform == "darwin" else rss * 1024),
        "memory_scope_warning": "Process peak RSS includes Python and loaded native libraries; it is a process high-water mark, not isolated per-system memory.",
        "latency_interpretation": "Reported values are warm-cache operational latency and must not be presented as cold-start latency.",
        "compatibility_statement": "Before measurement, 34 queries ran through unmeasured live ranking validation and five additional queries ran as unmeasured warm-up. All reported component and Hybrid timings then used one 20-repetition protocol; no timings from earlier incompatible runs were added.",
    }
    return samples, summary


def failure_analysis(
    hybrid_rows: list[dict[str, Any]], ranking_maps: dict[str, dict[str, dict[str, Any]]],
    graph_traces: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    failures = []
    for row in hybrid_rows:
        metrics = row["metrics"]
        if metrics["complete_evidence_recall_at_5"] == 1 and metrics["complete_evidence_recall_at_10"] == 1:
            continue
        query_id, gold = row["query_id"], set(row["known_gold_ids"])
        ranks = {
            system: {item["chunk_id"]: item["rank"] for item in ranking_maps[system][query_id]["ranking"]}
            for system in ("bm25", "entity_graph_v3_2", "hybrid_bm25_graph_rrf")
        }
        missing5 = sorted(chunk_id for chunk_id in gold if ranks["hybrid_bm25_graph_rrf"].get(chunk_id, 10**9) > 5)
        missing10 = sorted(chunk_id for chunk_id in gold if ranks["hybrid_bm25_graph_rrf"].get(chunk_id, 10**9) > 10)
        graph_empty = not ranking_maps["entity_graph_v3_2"][query_id]["ranking"]
        partial = bool(gold - set(missing10)) and bool(missing10)
        bm_diluted = any(ranks["bm25"].get(chunk_id, 10**9) <= 10 < ranks["hybrid_bm25_graph_rrf"].get(chunk_id, 10**9) for chunk_id in gold)
        graph_diluted = any(ranks["entity_graph_v3_2"].get(chunk_id, 10**9) <= 10 < ranks["hybrid_bm25_graph_rrf"].get(chunk_id, 10**9) for chunk_id in gold)
        absent_both = all(chunk_id not in ranks["bm25"] and chunk_id not in ranks["entity_graph_v3_2"] for chunk_id in missing10)
        present_below = any(chunk_id in ranks["bm25"] or chunk_id in ranks["entity_graph_v3_2"] for chunk_id in missing5)
        disagreement = any(
            chunk_id in ranks["bm25"] and chunk_id in ranks["entity_graph_v3_2"]
            and abs(ranks["bm25"][chunk_id] - ranks["entity_graph_v3_2"][chunk_id]) >= 10
            for chunk_id in missing5
        )
        if graph_empty and graph_traces[query_id]["status"] == "no_valid_seed" and missing10:
            taxonomy, rationale = "no_graph_seed", "Corrected Graph trace records no valid seed; Hybrid therefore uses BM25 contributions only."
        elif partial and row["category"] in {"multi_hop", "synthesis"}:
            taxonomy, rationale = "incomplete_multi_evidence", "Hybrid top 10 contains some but not all known evidence chunks."
        elif absent_both and missing10:
            taxonomy, rationale = "both_components_missed", "Missing known-gold chunks appear in neither constituent top 50."
        elif bm_diluted:
            taxonomy, rationale = "bm25_hit_diluted_by_graph_only_competitors", "Known-gold BM25 top-10 hit falls below Hybrid cutoff after Graph-only contributions enter fusion."
        elif graph_diluted:
            taxonomy, rationale = "graph_hit_diluted_by_bm25_only_competitors", "Known-gold Graph top-10 hit falls below Hybrid cutoff after BM25-only contributions enter fusion."
        elif disagreement:
            taxonomy, rationale = "component_disagreement", "Constituent ranks for missing known-gold evidence differ by at least ten positions."
        elif present_below:
            taxonomy, rationale = "relevant_chunk_present_but_fused_below_cutoff", "Known-gold chunk is inside a constituent top 50 but below Hybrid cutoff."
        else:
            taxonomy, rationale = "unresolved", "Saved traces do not support a more specific causal classification."
        failures.append({
            "failure_id": f"hybrid_bm25_graph_rrf:{query_id}", "system": "hybrid_bm25_graph_rrf",
            "query_id": query_id, "category": row["category"], "taxonomy": taxonomy, "rationale": rationale,
            "miss_at_5": bool(missing5), "miss_at_10": bool(missing10), "known_gold_ids": sorted(gold),
            "missed_gold_at_5": missing5, "missed_gold_at_10": missing10,
            "known_gold_ranks": {
                chunk_id: {system: ranks[system].get(chunk_id) for system in ranks} for chunk_id in sorted(gold)
            },
            "metric_snapshot": {metric: metrics[metric] for metric in ("mrr_at_10", "recall_at_10", "complete_evidence_recall_at_10")},
        })
    expected = {
        row["query_id"] for row in hybrid_rows
        if row["metrics"]["complete_evidence_recall_at_5"] < 1 or row["metrics"]["complete_evidence_recall_at_10"] < 1
    }
    if {row["query_id"] for row in failures} != expected:
        raise AssertionError("failure taxonomy does not cover every Hybrid cutoff miss")
    worst = sorted(hybrid_rows, key=lambda row: (
        row["metrics"]["mrr_at_10"], row["metrics"]["recall_at_10"],
        row["metrics"]["complete_evidence_recall_at_10"], row["query_id"],
    ))[:8]
    worst_rows = [{
        "query_id": row["query_id"], "category": row["category"], "known_gold_ids": row["known_gold_ids"],
        "mrr_at_10": row["metrics"]["mrr_at_10"], "recall_at_10": row["metrics"]["recall_at_10"],
        "complete_evidence_recall_at_10": row["metrics"]["complete_evidence_recall_at_10"],
        "top10": row["top10"],
        "failure_taxonomy": next((failure["taxonomy"] for failure in failures if failure["query_id"] == row["query_id"]), "none"),
    } for row in worst]
    return failures, worst_rows


def fuse_at_k(bm25: list[dict[str, Any]], graph: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    if k not in {30, 60, 100}:
        raise ValueError("bounded robustness permits only k=30,60,100")
    ranks = ({row["chunk_id"]: row["rank"] for row in bm25}, {row["chunk_id"]: row["rank"] for row in graph})
    scores = {
        chunk_id: sum(1 / (k + rank_map[chunk_id]) for rank_map in ranks if chunk_id in rank_map)
        for chunk_id in set(ranks[0]) | set(ranks[1])
    }
    return [
        {"chunk_id": chunk_id, "rank": rank, "score": scores[chunk_id]}
        for rank, chunk_id in enumerate(sorted(scores, key=lambda item: (-scores[item], item))[:50], 1)
    ]


def robustness(
    ranking_maps: dict[str, dict[str, dict[str, Any]]], qa: dict[str, dict[str, Any]], gains: dict[str, dict[str, int]],
    primary_hybrid: list[dict[str, Any]],
) -> dict[str, Any]:
    constituent_mrr = {
        system: aggregate(evaluate(system, ranking_maps[system], qa, gains))["mrr_at_10"]
        for system in ("bm25", "entity_graph_v3_2")
    }
    results = {}
    for k in (30, 60, 100):
        if k == 60:
            rows = primary_hybrid
        else:
            rankings = {
                query_id: {"query_id": query_id, "ranking": fuse_at_k(
                    ranking_maps["bm25"][query_id]["ranking"], ranking_maps["entity_graph_v3_2"][query_id]["ranking"], k,
                )} for query_id in sorted(qa)
            }
            rows = evaluate(f"hybrid_rrf_k{k}", rankings, qa, gains)
        metrics = aggregate(rows)
        results[str(k)] = {
            "status": "primary_preregistered" if k == 60 else "exploratory_robustness_only",
            "aggregate_metrics": metrics,
            "per_category_mrr_at_10": {
                category: statistics.mean(row["metrics"]["mrr_at_10"] for row in rows if row["category"] == category)
                for category in CATEGORIES
            },
            "hybrid_highest_aggregate_mrr_at_10": metrics["mrr_at_10"] > max(constituent_mrr.values()),
        }
    finding = {value["hybrid_highest_aggregate_mrr_at_10"] for value in results.values()}
    return {
        "notice": NOTICE,
        "primary_configuration_unchanged": True,
        "weights_unchanged": True,
        "tested_k_values_only": [30, 60, 100],
        "constituent_aggregate_mrr_at_10": constituent_mrr,
        "results": results,
        "qualitative_h4_ranking_finding_stable": len(finding) == 1,
        "selection_policy": "No k selected; k=60 remains primary regardless of result.",
    }


def expand_pool(
    paths: dict[str, Path], hybrid: dict[str, dict[str, Any]], qa: dict[str, dict[str, Any]],
    chunks: dict[str, dict[str, Any]], gains: dict[str, dict[str, int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    blind, sealed = parse_jsonl(paths["current_blind"]), parse_jsonl(paths["current_sealed"])
    if len(blind) != 610 or len(sealed) != 610:
        raise ValueError("corrected BM25/FAISS/Graph pool must contain 610 pairs")
    existing_pairs = {(row["query_id"], row["chunk_id"]) for row in sealed}
    numbers: dict[str, int] = defaultdict(int)
    for row in blind:
        match = re.search(r"-candidate-(\d+)$", row["display_id"])
        if not match:
            raise ValueError(f"unexpected display ID: {row['display_id']}")
        numbers[row["query_id"]] = max(numbers[row["query_id"]], int(match.group(1)))
    rng = random.Random(SEED)
    hybrid_hash = sha256_file(paths["hybrid"])
    new_blind, new_sealed = [], []
    for query_id in sorted(qa):
        candidates = [item for item in hybrid[query_id]["ranking"][:10] if (query_id, item["chunk_id"]) not in existing_pairs]
        candidates.sort(key=lambda item: item["chunk_id"])
        rng.shuffle(candidates)
        for item in candidates:
            pair = (query_id, item["chunk_id"])
            existing_pairs.add(pair)
            numbers[query_id] += 1
            display_id = f"{query_id}-candidate-{numbers[query_id]:02d}"
            new_blind.append({
                "display_id": display_id, "query_id": query_id, "question": qa[query_id]["question"],
                "chunk_id": item["chunk_id"], "chunk_text": chunks[item["chunk_id"]]["text"],
                "relevance_judgment": "", "reviewer_notes": "",
            })
            new_sealed.append({
                "display_id": display_id, "query_id": query_id, "chunk_id": item["chunk_id"],
                "contributions": [{"system": "hybrid_bm25_graph_rrf", "rank": item["rank"], "score": item["score"]}],
                "current_gold": gains[query_id].get(item["chunk_id"], 0) > 0,
                "hybrid_ranking_sha256": hybrid_hash,
            })
    expanded_blind, expanded_sealed = blind + new_blind, sealed + new_sealed
    blind_map = {row["display_id"]: row for row in expanded_blind}
    sealed_map = {row["display_id"]: row for row in expanded_sealed}
    forbidden = {"system", "systems", "rank", "score", "current_gold", "gold", "relevance", "contributions", "hybrid_ranking_sha256"}
    if len(blind_map) != len(expanded_blind) or set(blind_map) != set(sealed_map):
        raise ValueError("expanded blind/sealed IDs duplicate or misalign")
    if len({(row["query_id"], row["chunk_id"]) for row in expanded_sealed}) != len(expanded_sealed):
        raise ValueError("expanded pool contains duplicate query/chunk pairs")
    if any(set(row) & forbidden or row["relevance_judgment"] or row["reviewer_notes"] for row in expanded_blind):
        raise ValueError("blind pool leaks provenance or contains owner labels")
    systems = {item["system"] for row in expanded_sealed for item in row["contributions"]}
    if systems != {"bm25", "faiss_windowed_max", "entity_graph_v3_2", "hybrid_bm25_graph_rrf"}:
        raise ValueError(f"combined pool system set invalid: {systems}")
    design = {
        "status": "provisional_pending_prompt_rag_expansion_and_owner_judging",
        "seed": SEED, "candidate_cutoff": 10, "deduplication_key": ["query_id", "chunk_id"],
        "existing_pair_count": len(blind), "unseen_hybrid_pair_count": len(new_blind),
        "combined_pair_count": len(expanded_blind), "owner_labels_completed": False, "final_qrels": False,
        "systems": sorted(systems), "invalid_graph_sources_included": False,
        "hybrid_ranking_sha256": hybrid_hash, "original_504_phase2b_rows_unchanged": True,
    }
    return expanded_blind, expanded_sealed, design


def main() -> None:
    global args_global
    parser = argparse.ArgumentParser(description=__doc__)
    for name in APPROVED:
        parser.add_argument(f"--{name.replace('_', '-')}", dest=name, type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args_global = parser.parse_args()
    paths = validate_paths(args_global)
    config = json.loads(paths["config"].read_text(encoding="utf-8"))

    trace_decision = trace_gate(paths, config)

    protected_before = {name: sha256_file(paths[name]) for name in EXPECTED_PROTECTED_HASHES}
    if protected_before != EXPECTED_PROTECTED_HASHES:
        raise ValueError(f"protected Phase 0-3 hash mismatch after trace gate: {protected_before}")
    qa, gains, chunks = load_benchmark(paths)
    all_input_hashes = {
        str(path.relative_to(ROOT)): sha256_file(path)
        for name, path in paths.items() if name not in {"output", "audit_output"}
    }
    ranking_maps = {
        "bm25": rows_by_query(paths["bm25"]),
        "entity_graph_v3_2": rows_by_query(paths["graph"]),
        "hybrid_bm25_graph_rrf": rows_by_query(paths["hybrid"]),
    }
    evaluated = {system: evaluate(system, rows, qa, gains) for system, rows in ranking_maps.items()}
    metrics = {
        "notice": NOTICE,
        "status": "exploratory_known_gold_pilot",
        "qrels_scope": "AI-assisted, owner-authorized, non-exhaustive direct-support qrels; all 48 current judgments have grade 2.",
        "systems": {system: panel(rows) for system, rows in evaluated.items()},
    }
    write_json(paths["output"] / RUN_OUTPUTS[1], metrics, overwrite=args_global.overwrite)
    write_jsonl(paths["output"] / RUN_OUTPUTS[2], [row for system in evaluated for row in evaluated[system]], key="row_id", overwrite=args_global.overwrite)

    constituents = {system: metrics["systems"][system]["aggregate"]["metrics"]["mrr_at_10"] for system in ("bm25", "entity_graph_v3_2")}
    strongest = max(constituents, key=constituents.get)
    comparisons = {
        "notice": NOTICE, "samples": BOOTSTRAPS, "seed": SEED, "effect_direction": "Hybrid minus comparator",
        "strongest_constituent_by_aggregate_mrr_at_10": strongest,
        "constituent_aggregate_mrr_at_10": constituents,
        "comparisons": {
            "hybrid_vs_bm25": comparison_panel(evaluated["hybrid_bm25_graph_rrf"], evaluated["bm25"]),
            "hybrid_vs_entity_graph_v3_2": comparison_panel(evaluated["hybrid_bm25_graph_rrf"], evaluated["entity_graph_v3_2"]),
        },
        "strongest_constituent_comparison_alias": f"hybrid_vs_{strongest}",
        "inference": "exploratory pilot only; no final H4 verdict",
    }
    hybrid_mrr = metrics["systems"]["hybrid_bm25_graph_rrf"]["aggregate"]["metrics"]["mrr_at_10"]
    strongest_mrr = constituents[strongest]
    strongest_mrr_effect = comparisons["comparisons"][f"hybrid_vs_{strongest}"]["aggregate"]["mrr_at_10"]
    if strongest_mrr_effect["uncertainty_includes_zero"]:
        comparisons["equal_weight_fusion_vs_strongest"] = (
            "point_estimate_higher_but_inconclusive" if hybrid_mrr > strongest_mrr
            else "no_point_difference_and_inconclusive" if hybrid_mrr == strongest_mrr
            else "point_estimate_lower_but_inconclusive"
        )
    else:
        comparisons["equal_weight_fusion_vs_strongest"] = (
            "higher_with_interval_excluding_zero" if hybrid_mrr > strongest_mrr
            else "no_point_difference" if hybrid_mrr == strongest_mrr
            else "lower_with_interval_excluding_zero"
        )
    comparisons["category_effect_on_mrr_at_10_vs_strongest"] = {}
    strongest_comparison = comparisons["comparisons"][f"hybrid_vs_{strongest}"]
    for category in CATEGORIES:
        effect = strongest_comparison["per_category"][category]["mrr_at_10"]
        comparisons["category_effect_on_mrr_at_10_vs_strongest"][category] = {
            "classification": (
                "point_estimate_higher_but_inconclusive" if effect["uncertainty_includes_zero"] and effect["point_effect_hybrid_minus_comparator"] > 0
                else "no_point_difference_and_inconclusive" if effect["uncertainty_includes_zero"] and effect["point_effect_hybrid_minus_comparator"] == 0
                else "point_estimate_lower_but_inconclusive" if effect["uncertainty_includes_zero"]
                else "higher_with_interval_excluding_zero" if effect["point_effect_hybrid_minus_comparator"] > 0
                else "no_point_difference" if effect["point_effect_hybrid_minus_comparator"] == 0
                else "lower_with_interval_excluding_zero"
            ),
            "point_effect": effect["point_effect_hybrid_minus_comparator"],
            "ci95": effect["ci95"],
            "uncertainty_includes_zero": effect["uncertainty_includes_zero"],
        }
    write_json(paths["output"] / RUN_OUTPUTS[3], comparisons, overwrite=args_global.overwrite)

    graph_traces = rows_by_query(paths["graph_traces"])
    failures, worst = failure_analysis(evaluated["hybrid_bm25_graph_rrf"], ranking_maps, graph_traces)
    write_jsonl(paths["output"] / RUN_OUTPUTS[4], failures, key="failure_id", overwrite=args_global.overwrite)
    write_json(paths["output"] / RUN_OUTPUTS[5], {"notice": NOTICE, "selection": "ascending MRR@10, Recall@10, Complete Evidence Recall@10, query ID", "queries": worst}, overwrite=args_global.overwrite)

    latency_rows, latency_summary = measure_latency(paths, config, qa, chunks, ranking_maps)
    write_jsonl(paths["output"] / RUN_OUTPUTS[6], latency_rows, key="sample_id", overwrite=args_global.overwrite)
    write_json(paths["output"] / RUN_OUTPUTS[7], latency_summary, overwrite=args_global.overwrite)
    robustness_report = robustness(ranking_maps, qa, gains, evaluated["hybrid_bm25_graph_rrf"])
    write_json(paths["output"] / RUN_OUTPUTS[8], robustness_report, overwrite=args_global.overwrite)

    blind, sealed, pool_design = expand_pool(paths, ranking_maps["hybrid_bm25_graph_rrf"], qa, chunks, gains)
    write_jsonl(paths["output"] / RUN_OUTPUTS[9], blind, key="display_id", overwrite=args_global.overwrite)
    write_jsonl(paths["output"] / RUN_OUTPUTS[10], sealed, key="display_id", overwrite=args_global.overwrite)
    pool_design["blind_sha256"] = sha256_file(paths["output"] / RUN_OUTPUTS[9])
    pool_design["sealed_sha256"] = sha256_file(paths["output"] / RUN_OUTPUTS[10])
    write_json(paths["output"] / RUN_OUTPUTS[11], pool_design, overwrite=args_global.overwrite)
    pool_integrity = {
        "status": "passed", "blind_rows": len(blind), "sealed_rows": len(sealed),
        "unique_pairs": len({(row["query_id"], row["chunk_id"]) for row in sealed}),
        "blind_sealed_alignment": True, "provenance_leaks": 0, "blank_owner_fields": len(blind),
        "existing_pool_sha256": protected_before["current_blind"], "existing_sealed_sha256": protected_before["current_sealed"],
        "owner_judgments_sha256": protected_before["owner_judgments"], "invalid_graph_candidates_added": False,
        "hybrid_candidates_trace_to_ranking_sha256": sha256_file(paths["hybrid"]),
    }
    write_json(paths["audit_output"] / AUDIT_OUTPUTS[2], pool_integrity, overwrite=args_global.overwrite)

    commands = {
        "fusion": json.loads(paths["fusion_manifest"].read_text(encoding="utf-8"))["exact_command"],
        "evaluation": " ".join(shlex.quote(argument) for argument in sys.argv),
        "focused_tests": "pytest -q tests/test_phase4_hybrid.py",
        "full_tests": "pytest -q",
        "diff_check": "git diff --check",
    }
    write_json(paths["output"] / RUN_OUTPUTS[12], commands, overwrite=args_global.overwrite)
    protected_after = {name: sha256_file(paths[name]) for name in EXPECTED_PROTECTED_HASHES}
    if protected_after != protected_before:
        raise RuntimeError("protected Phase 0-3 artifact changed during Phase 4 evaluation")
    protected_audit = {
        "status": "passed_unchanged", "before": protected_before, "after": protected_after,
        "phase4_writes_only": ["configs/hybrid_rrf_v1_frozen.json", "runs/v2/phase4_hybrid/", "audits/phase4_hybrid/", "src/retrievers/hybrid_rrf_v1.py", "scripts/run_phase4_hybrid.py", "scripts/evaluate_phase4_hybrid.py", "tests/test_phase4_hybrid.py"],
    }
    write_json(paths["audit_output"] / AUDIT_OUTPUTS[3], protected_audit, overwrite=args_global.overwrite)

    manifest = {
        "status": "phase4_hybrid_checkpoint_complete",
        "notice": NOTICE,
        "trace_gate": trace_decision,
        "primary_configuration_sha256": sha256_file(paths["config"]),
        "primary_configuration_changed_after_results": False,
        "strongest_constituent": strongest,
        "equal_weight_fusion_vs_strongest": comparisons["equal_weight_fusion_vs_strongest"],
        "no_final_h4_verdict": True,
        "failure_count_at_either_cutoff": len(failures),
        "latency": latency_summary,
        "robustness": robustness_report,
        "pool": pool_design,
        "prompt_rag_run": False,
        "generation_run": False,
        "owner_judging_completed": False,
        "input_hashes": all_input_hashes,
        "protected_phase0_to_3_hashes": protected_before,
        "code_hashes": {
            "scripts/evaluate_phase4_hybrid.py": sha256_file(Path(__file__)),
            "scripts/run_phase4_hybrid.py": sha256_file(ROOT / "scripts/run_phase4_hybrid.py"),
            "src/retrievers/hybrid_rrf_v1.py": sha256_file(ROOT / "src/retrievers/hybrid_rrf_v1.py"),
            "tests/test_phase4_hybrid.py": sha256_file(ROOT / "tests/test_phase4_hybrid.py"),
        },
        "outputs": {},
    }
    output_paths = [paths["output"] / relative for relative in RUN_OUTPUTS[:13]] + [paths["audit_output"] / relative for relative in AUDIT_OUTPUTS]
    manifest["outputs"] = {str(path.relative_to(ROOT)): sha256_file(path) for path in output_paths}
    write_json(paths["output"] / RUN_OUTPUTS[13], manifest, overwrite=args_global.overwrite)
    all_hashes = {**manifest["outputs"], str((paths["output"] / RUN_OUTPUTS[13]).relative_to(ROOT)): sha256_file(paths["output"] / RUN_OUTPUTS[13])}
    write_json(paths["output"] / RUN_OUTPUTS[14], {"input_hashes": all_input_hashes, "output_hashes": all_hashes}, overwrite=args_global.overwrite)
    print(stable_json({
        "status": manifest["status"],
        "trace_gate": trace_decision["status"],
        "aggregate_metrics": {system: metrics["systems"][system]["aggregate"]["metrics"] for system in metrics["systems"]},
        "strongest_constituent": strongest,
        "fusion_vs_strongest": comparisons["equal_weight_fusion_vs_strongest"],
        "failures": len(failures),
        "latency": latency_summary["timings"],
        "pool": pool_design,
    }))


args_global: argparse.Namespace


if __name__ == "__main__":
    main()
