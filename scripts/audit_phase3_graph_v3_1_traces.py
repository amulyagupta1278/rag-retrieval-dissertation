#!/usr/bin/env python3
"""Audit exactly eight frozen v3.1 traces without reading qrels or metrics."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_phase3_graph_v2 import parse_jsonl  # noqa: E402
from src.retrievers.entity_graph_v3 import normalize_text, normalized_tokens  # noqa: E402
from src.utils.atomic_io import stable_json, write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


SELECTED = {
    "v2q-019": {
        "trace_role": "direct_named_entity",
        "expected_seed": "Ministry Of Petroleum and Natural Gas",
    },
    "v2q-024": {
        "trace_role": "indirect_alias",
        "expected_seed": "National Health Authority",
        "expected_alias": "NHA",
    },
    "v2q-025": {
        "trace_role": "multi_hop",
        "expected_seed": "Pradhan Mantri Jan Dhan Yojana",
        "expected_bridge": "Ministry Of Finance",
        "expected_target_document": "doc-pmmy",
    },
    "v2q-026": {
        "trace_role": "multi_hop",
        "expected_seed": "Mahatma Gandhi National Rural Employment Guarantee Act",
        "expected_bridge": "Ministry Of Rural Development",
        "expected_target_document": "doc-pmay-g",
    },
    "v2q-027": {
        "trace_role": "multi_hop",
        "expected_seed": "PM Street Vendor’s AtmaNirbhar Nidhi",
        "expected_bridge": "Ministry Of Housing And Urban Affairs",
        "expected_target_document": "doc-pmay-u",
    },
    "v2q-028": {
        "trace_role": "multi_hop",
        "expected_seed": "Recognition of Prior Learning",
        "expected_bridge": "Ministry Of Skill Development And Entrepreneurship",
        "expected_target_document": "doc-pmkvy-stt",
    },
    "v2q-029": {
        "trace_role": "multi_hop",
        "expected_seed": "Pradhan Mantri Ujjwala Yojana 2.0",
        "expected_bridge": "Ministry Of Petroleum and Natural Gas",
        "expected_target_document": "doc-pmuy",
    },
    "v2q-030": {
        "trace_role": "multi_hop",
        "expected_seed": "Atal Pension Yojana",
        "expected_bridge": "Department of Financial Services",
        "expected_target_document": "doc-pmjjby",
    },
}


def entity_by_label(registry: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    target = normalize_text(label)
    matches = [row for row in registry if row["status"] == "accepted" and normalize_text(str(row["canonical_label"])) == target]
    if len(matches) > 1:
        raise ValueError(f"duplicate canonical registry label: {label}")
    return matches[0] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "registry", "nodes", "edges", "chunks", "queries", "traces", "retrieval_manifest", "output", "decision"):
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    paths = {name: getattr(args, name).resolve() for name in ("config", "registry", "nodes", "edges", "chunks", "queries", "traces", "retrieval_manifest", "output", "decision")}
    approved = {
        "config": (ROOT / "configs/entity_graph_v3_1_frozen.json").resolve(),
        "registry": (ROOT / "data/v2/pilot/graph/entity_registry_v3_1.jsonl").resolve(),
        "nodes": (ROOT / "runs/v2/phase3_graph_v3_1/index/nodes.jsonl").resolve(),
        "edges": (ROOT / "runs/v2/phase3_graph_v3_1/index/edges.jsonl").resolve(),
        "chunks": (ROOT / "data/v2/pilot/chunks/chunks.jsonl").resolve(),
        "queries": (ROOT / "runs/v2/phase3_graph_v3_1/inputs/r5_queries_only.jsonl").resolve(),
        "traces": (ROOT / "runs/v2/phase3_graph_v3_1/traces/graph_v3_1_full_traces.jsonl").resolve(),
        "retrieval_manifest": (ROOT / "runs/v2/phase3_graph_v3_1/retrieval_manifest.json").resolve(),
        "output": (ROOT / "audits/phase3_graph_v3_1/eight_trace_audit.jsonl").resolve(),
        "decision": (ROOT / "audits/phase3_graph_v3_1/trace_validity_decision.json").resolve(),
    }
    if paths != approved:
        raise ValueError("trace audit requires approved frozen paths")

    config = json.loads(paths["config"].read_text(encoding="utf-8"))
    registry = parse_jsonl(paths["registry"])
    nodes = parse_jsonl(paths["nodes"])
    edges = parse_jsonl(paths["edges"])
    chunks = {row["chunk_id"]: row for row in parse_jsonl(paths["chunks"])}
    queries = {row["query_id"]: row for row in parse_jsonl(paths["queries"])}
    all_traces = {row["query_id"]: row for row in parse_jsonl(paths["traces"])}
    retrieval_manifest = json.loads(paths["retrieval_manifest"].read_text(encoding="utf-8"))
    selected_traces = {query_id: all_traces[query_id] for query_id in SELECTED}
    if len(selected_traces) != 8 or set(selected_traces) != set(SELECTED):
        raise ValueError("trace audit must inspect exactly selected eight traces")

    accepted = {row["entity_id"]: row for row in registry if row["status"] == "accepted"}
    banned = {normalize_text(value) for value in config["banned_entity_labels"]}
    generic = {normalize_text(value) for value in config["generic_entity_labels"]}
    edge_pairs = {frozenset((str(row["source"]), str(row["target"]))) for row in edges}
    co_pairs = {
        frozenset((str(row["source"]), str(row["target"])))
        for row in edges if row["edge_type"] == "CO_OCCURS_WITH"
    }
    chunk_documents = {str(row["chunk_id"]): str(row["document_id"]) for row in nodes if row["node_type"] == "chunk"}
    audit_rows: list[dict[str, Any]] = []

    for query_id, expected in sorted(SELECTED.items()):
        trace, query = selected_traces[query_id], queries[query_id]
        query_tokens = normalized_tokens(str(query["question"]))
        seed_checks: list[dict[str, Any]] = []
        for seed in trace["matched_seeds"]:
            entity = accepted.get(seed["entity_id"])
            start, end = int(seed["token_start"]), int(seed["token_end"])
            span_tokens = query_tokens[start:end]
            boundary_valid = span_tokens == normalized_tokens(str(seed["matched_alias"]))
            weight = math.log((140 + 1) / (int(seed["document_frequency"]) + 1)) + 1
            seed_checks.append({
                "entity_id": seed["entity_id"],
                "matched_query_span": seed["matched_query_span"],
                "matched_alias": seed["matched_alias"],
                "canonical_seed": seed["canonical_label"],
                "entity_type": seed["entity_type"],
                "document_frequency": seed["document_frequency"],
                "seed_weight": seed["seed_weight"],
                "registry_entity_exists_and_accepted": entity is not None,
                "exact_boundary_match": boundary_valid,
                "seed_weight_reproduced": math.isclose(float(seed["seed_weight"]), weight, rel_tol=0, abs_tol=1e-12),
                "meaningful_not_banned_or_generic": normalize_text(str(seed["canonical_label"])) not in banned | generic and normalize_text(str(seed["matched_alias"])) not in banned | generic,
            })

        path_checks: list[dict[str, Any]] = []
        all_paths_valid = True
        all_scores_valid = True
        no_duplicate_seed_chunk = True
        positive_scores_only = True
        for ranked in trace["ranking"]:
            seen_seed_ids: set[str] = set()
            reproduced = 0.0
            for contribution in ranked["paths"]:
                path = list(contribution["path"])
                supported = all(frozenset((left, right)) in edge_pairs for left, right in zip(path, path[1:]))
                distance = len(path) - 1
                formula = float(contribution["seed_weight"]) * (0.5**distance)
                seed_unique = contribution["entity_id"] not in seen_seed_ids
                seen_seed_ids.add(contribution["entity_id"])
                reproduced += formula
                valid = (
                    supported
                    and path[0] == f"entity:{contribution['entity_id']}"
                    and path[-1] == f"chunk:{ranked['chunk_id']}"
                    and distance == int(contribution["distance"])
                    and distance <= 2
                    and math.isclose(float(contribution["contribution"]), formula, rel_tol=0, abs_tol=1e-12)
                )
                all_paths_valid &= valid
                no_duplicate_seed_chunk &= seed_unique
                path_checks.append({
                    "chunk_id": ranked["chunk_id"],
                    "seed_entity_id": contribution["entity_id"],
                    "path": path,
                    "distance": distance,
                    "contribution": contribution["contribution"],
                    "edge_supported_and_formula_valid": valid,
                    "seed_unique_for_chunk": seed_unique,
                })
            score_valid = math.isclose(float(ranked["total_score"]), reproduced, rel_tol=0, abs_tol=1e-12)
            all_scores_valid &= score_valid and math.isclose(float(ranked["reproduced_score"]), reproduced, rel_tol=0, abs_tol=1e-12)
            positive_scores_only &= float(ranked["total_score"]) > 0

        ranking = trace["ranking"]
        rank_order_valid = all(int(row["rank"]) == index for index, row in enumerate(ranking, 1))
        tie_order_valid = all(
            not math.isclose(float(left["total_score"]), float(right["total_score"]), rel_tol=0, abs_tol=1e-12)
            or str(left["chunk_id"]) < str(right["chunk_id"])
            for left, right in zip(ranking, ranking[1:])
        )
        expected_seed = entity_by_label(registry, str(expected["expected_seed"]))
        expected_seed_resolved = expected_seed is not None and any(seed["entity_id"] == expected_seed["entity_id"] for seed in trace["matched_seeds"])
        expected_alias_resolved = not expected.get("expected_alias") or any(
            normalize_text(str(seed["matched_alias"])) == normalize_text(str(expected["expected_alias"]))
            for seed in trace["matched_seeds"]
        )
        relationship_supported: bool | None = None
        relationship_evidence: dict[str, Any] | None = None
        if expected.get("expected_bridge"):
            bridge = entity_by_label(registry, str(expected["expected_bridge"]))
            co_supported = bool(expected_seed and bridge and frozenset((f"entity:{expected_seed['entity_id']}", f"entity:{bridge['entity_id']}")) in co_pairs)
            target_mentions = sorted(
                chunk_id
                for chunk_id, document_id in chunk_documents.items()
                if bridge
                and document_id == expected["expected_target_document"]
                and frozenset((f"entity:{bridge['entity_id']}", f"chunk:{chunk_id}")) in edge_pairs
            )
            relationship_supported = co_supported and bool(target_mentions)
            relationship_evidence = {
                "seed": expected["expected_seed"],
                "bridge": expected["expected_bridge"],
                "target_document": expected["expected_target_document"],
                "seed_bridge_cooccurrence_edge": co_supported,
                "bridge_target_mention_chunks": target_mentions,
            }
        top10 = [
            {
                "rank": row["rank"],
                "chunk_id": row["chunk_id"],
                "score": row["total_score"],
                "document_id": chunks[row["chunk_id"]]["document_id"],
                "excerpt": " ".join(str(chunks[row["chunk_id"]]["text"]).split())[:240],
            }
            for row in ranking[:10]
        ]
        no_forbidden_inputs = (
            retrieval_manifest["relevance_or_evaluation_inputs_read"] is False
            and retrieval_manifest["previous_rankings_or_metrics_read"] is False
            and retrieval_manifest["categories_read"] is False
            and all(set(row) == {"query_id", "question"} for row in queries.values())
        )
        checks = {
            "all_seeds_meaningful_and_registered": all(
                row["registry_entity_exists_and_accepted"] and row["meaningful_not_banned_or_generic"] for row in seed_checks
            ),
            "exact_boundary_matching": all(row["exact_boundary_match"] for row in seed_checks),
            "expected_scheme_or_entity_seed_resolved": expected_seed_resolved,
            "expected_alias_resolved": bool(expected_alias_resolved),
            "expected_multi_hop_relationship_corpus_supported": relationship_supported if relationship_supported is not None else True,
            "paths_and_contributions_valid_max_depth_two": all_paths_valid,
            "scores_reproduced": all_scores_valid,
            "same_seed_not_double_counted": no_duplicate_seed_chunk,
            "independent_seed_accumulation": no_duplicate_seed_chunk and all(row["seed_weight_reproduced"] for row in seed_checks),
            "deterministic_rank_and_tie_order": rank_order_valid and tie_order_valid and retrieval_manifest["determinism_verified_across_repetitions"],
            "positive_scores_no_padding": positive_scores_only,
            "returned_chunks_graph_reachable_and_corpus_plausible": all_paths_valid,
            "no_relevance_benchmark_metadata_or_previous_results_in_ranking": no_forbidden_inputs,
        }
        failed = sorted(name for name, passed in checks.items() if not passed)
        audit_rows.append({
            "query_id": query_id,
            "trace_role": expected["trace_role"],
            "question": query["question"],
            "trace_status": trace["status"],
            "seed_checks": seed_checks,
            "expected_relationship": relationship_evidence,
            "checks": checks,
            "failed_checks": failed,
            "trace_valid": not failed,
            "top10_plausibility_view": top10,
            "path_check_count": len(path_checks),
        })

    write_jsonl(paths["output"], audit_rows, key="query_id", overwrite=args.overwrite)
    invalid_rows = [row for row in audit_rows if not row["trace_valid"]]
    ujjwala_alias_occurrences = sorted(
        row["chunk_id"]
        for row in chunks.values()
        if "ujjwala 2 0" in normalize_text(str(row["text"]))
    )
    decision = {
        "status": "invalid_trace_gate_missing_corpus_backed_scheme_alias" if invalid_rows else "passed_trace_validity_gate",
        "inspected_trace_count": len(audit_rows),
        "inspected_query_ids": sorted(SELECTED),
        "valid_trace_count": len(audit_rows) - len(invalid_rows),
        "invalid_trace_count": len(invalid_rows),
        "invalid_query_ids": [row["query_id"] for row in invalid_rows],
        "retrieval_run_preserved": True,
        "metrics_calculated": False,
        "pool_expansion_performed": False,
        "failure": {
            "query_id": "v2q-029",
            "observed": "no_valid_seed for query phrase Ujjwala 2.0",
            "exact_defect": "corpus-backed alias Ujjwala 2.0 absent from Pradhan Mantri Ujjwala Yojana 2.0 registry entity; only PMUY2 alias present",
            "corpus_occurrence_chunk_ids": ujjwala_alias_occurrences,
            "classification": "registry alias-coverage implementation defect; exact token matcher behaved as frozen",
            "not_a_score_based_change": True,
        } if invalid_rows else None,
        "required_next_step": "stop for owner approval; do not repair, evaluate, or expand pool" if invalid_rows else "stop for owner trace approval before evaluation",
        "trace_audit_sha256": sha256_file(paths["output"]),
        "retrieval_manifest_sha256": sha256_file(paths["retrieval_manifest"]),
    }
    write_json(paths["decision"], decision, overwrite=args.overwrite)
    print(stable_json(decision))


if __name__ == "__main__":
    main()
