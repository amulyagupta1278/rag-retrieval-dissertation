#!/usr/bin/env python3
"""Add known-gold, comparison, ceiling, and worst-trace Phase 6 reports."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import evaluate_phase6_seed42 as evaluation  # noqa: E402
from src.utils.atomic_io import write_json, write_jsonl  # noqa: E402
from src.utils.hashing import sha256_file  # noqa: E402


def load_known_gold(
    path: Path, query_ids: set[str], chunk_ids: set[str]
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = defaultdict(dict)
    for row in evaluation.read_jsonl(path):
        query_id = row.get("query_id")
        chunk_id = row.get("chunk_id")
        grade = row.get("relevance")
        if query_id not in query_ids or chunk_id not in chunk_ids:
            raise ValueError("known-gold qrel contains unknown identifier")
        if not isinstance(grade, int) or grade not in (0, 1, 2):
            raise ValueError("known-gold qrel contains invalid grade")
        if chunk_id in result[query_id]:
            raise ValueError("duplicate known-gold query/chunk pair")
        result[query_id][chunk_id] = grade
    if set(result) != query_ids:
        raise ValueError("known-gold qrels do not cover exact frozen query set")
    return dict(result)


def aggregate(
    rows: list[dict[str, Any]], category_counts: Counter[str]
) -> dict[str, Any]:
    return {
        "aggregate": {"metrics": evaluation.mean_metrics(rows), "query_n": len(rows)},
        "per_category": {
            category: {
                "metrics": evaluation.mean_metrics(
                    [row for row in rows if row["category"] == category]
                ),
                "query_n": category_counts[category],
            }
            for category in evaluation.CATEGORIES
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--qa", type=Path, required=True)
    parser.add_argument("--known-gold-qrels", type=Path, required=True)
    parser.add_argument("--final-qrels", type=Path, required=True)
    parser.add_argument("--bm25-ranking", type=Path, required=True)
    parser.add_argument("--faiss-ranking", type=Path, required=True)
    parser.add_argument("--graph-ranking", type=Path, required=True)
    parser.add_argument("--hybrid-ranking", type=Path, required=True)
    parser.add_argument("--prompt-ranking", type=Path, required=True)
    parser.add_argument("--phase2a-efficiency", type=Path, required=True)
    parser.add_argument("--graph-manifest", type=Path, required=True)
    parser.add_argument("--hybrid-latency", type=Path, required=True)
    parser.add_argument("--prompt-trace-operational", type=Path, required=True)
    parser.add_argument("--prompt-full-operational", type=Path, required=True)
    parser.add_argument("--bm25-index-dir", type=Path, required=True)
    parser.add_argument("--faiss-index-dir", type=Path, required=True)
    parser.add_argument("--git-head", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for key, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, key, value.resolve())
    output_dir = args.output_dir
    output_names = (
        "known_gold_metrics.json",
        "known_gold_per_query.jsonl",
        "balanced_metrics.json",
        "final_pooled_per_query.jsonl",
        "paired_uncertainty_vs_bm25.json",
        "failure_taxonomy.jsonl",
        "efficiency_snapshot.json",
        "system_comparison_table.json",
        "known_gold_vs_final_pooled_shifts.json",
        "prompt_rag_candidate_recall_ceiling.json",
        "worst_query_traces.json",
        "supplement_manifest.json",
    )
    if not args.overwrite and any((output_dir / name).exists() for name in output_names):
        raise FileExistsError("supplement output exists; pass --overwrite")

    chunks = evaluation.read_jsonl(args.chunks)
    qa = evaluation.read_jsonl(args.qa)
    chunk_ids = {row["chunk_id"] for row in chunks}
    qa_by_id = {row["question_id"]: row for row in qa}
    if len(chunk_ids) != 140 or len(qa_by_id) != 34:
        raise ValueError("frozen corpus/query counts must be 140/34")
    query_ids = set(qa_by_id)
    category_counts = Counter(row["category"] for row in qa)
    final_qrels = evaluation.load_qrels(args.final_qrels, query_ids, chunk_ids)
    known_qrels = load_known_gold(args.known_gold_qrels, query_ids, chunk_ids)
    ranking_paths = {
        "bm25": args.bm25_ranking,
        "faiss_windowed_max": args.faiss_ranking,
        "graph_v3_2": args.graph_ranking,
        "hybrid_rrf": args.hybrid_ranking,
        "prompt_rag_claude": args.prompt_ranking,
    }
    rankings = {
        system: evaluation.load_ranking(
            path, system, query_ids, chunk_ids, final_qrels
        )
        for system, path in ranking_paths.items()
    }

    known_rows: list[dict[str, Any]] = []
    final_per_query_rows: list[dict[str, Any]] = []
    final_rows: dict[str, list[dict[str, Any]]] = {}
    known_by_system: dict[str, list[dict[str, Any]]] = {}
    for system, ranking in rankings.items():
        system_known = []
        system_final = []
        for query_id in sorted(query_ids):
            common = {
                "category": qa_by_id[query_id]["category"],
                "query_id": query_id,
                "system": system,
            }
            known = {
                **common,
                "metrics": evaluation.query_metrics(ranking[query_id], known_qrels[query_id]),
            }
            final = {
                **common,
                "metrics": evaluation.query_metrics(ranking[query_id], final_qrels[query_id]),
            }
            system_known.append(known)
            system_final.append(final)
            known_rows.append({"row_id": f"{system}:{query_id}", **known})
            final_per_query_rows.append({"row_id": f"{system}:{query_id}", **final})
        known_by_system[system] = system_known
        final_rows[system] = system_final

    known_metrics = {
        system: aggregate(rows, category_counts)
        for system, rows in known_by_system.items()
    }
    final_metrics = {
        system: aggregate(rows, category_counts) for system, rows in final_rows.items()
    }
    comparison = {
        system: {
            "final_pooled": final_metrics[system]["aggregate"],
            "known_gold": known_metrics[system]["aggregate"],
        }
        for system in rankings
    }
    shifts: dict[str, Any] = {
        "interpretation": (
            "Known-gold uses R5 direct-support qrels. Final-pooled uses all 755 blind "
            "owner judgments; added relevant context changes both gains and recall denominators."
        ),
        "material_threshold_absolute": 0.01,
        "systems": {},
    }
    for system in rankings:
        shifts["systems"][system] = {}
        for slice_name in ("aggregate", *evaluation.CATEGORIES):
            if slice_name == "aggregate":
                known = known_metrics[system]["aggregate"]["metrics"]
                final = final_metrics[system]["aggregate"]["metrics"]
                query_n = 34
            else:
                known = known_metrics[system]["per_category"][slice_name]["metrics"]
                final = final_metrics[system]["per_category"][slice_name]["metrics"]
                query_n = category_counts[slice_name]
            deltas = {
                metric: final[metric] - known[metric] for metric in evaluation.METRICS
            }
            shifts["systems"][system][slice_name] = {
                "deltas_final_minus_known": deltas,
                "material_deltas_abs_ge_0_01": {
                    metric: value for metric, value in deltas.items() if abs(value) >= 0.01
                },
                "query_n": query_n,
            }

    ceilings = []
    for query_id in sorted(query_ids):
        relevant = {
            chunk_id for chunk_id, grade in final_qrels[query_id].items() if grade > 0
        }
        candidate_set = set(rankings["bm25"][query_id][:50])
        ceilings.append(
            {
                "category": qa_by_id[query_id]["category"],
                "query_id": query_id,
                "recall_ceiling": len(relevant & candidate_set) / len(relevant),
                "relevant_n": len(relevant),
            }
        )
    ceiling_report = {
        "aggregate_macro_mean": sum(row["recall_ceiling"] for row in ceilings) / 34,
        "candidate_generator": "frozen_bm25_top50",
        "per_category": {
            category: {
                "macro_mean": sum(
                    row["recall_ceiling"]
                    for row in ceilings
                    if row["category"] == category
                )
                / category_counts[category],
                "query_n": category_counts[category],
            }
            for category in evaluation.CATEGORIES
        },
        "per_query": ceilings,
    }

    worst: dict[str, list[dict[str, Any]]] = {}
    failure_rows: list[dict[str, Any]] = []
    for system, rows in final_rows.items():
        selected = sorted(
            rows,
            key=lambda row: (
                row["metrics"]["mrr_at_10"],
                row["metrics"]["recall_at_10"],
                row["metrics"]["complete_evidence_recall_at_10"],
                row["query_id"],
            ),
        )[:5]
        worst[system] = [
            {
                **row,
                "positive_qrel_chunk_ids": sorted(
                    chunk_id
                    for chunk_id, grade in final_qrels[row["query_id"]].items()
                    if grade > 0
                ),
                "top10_chunk_ids": rankings[system][row["query_id"]][:10],
            }
            for row in selected
        ]
        for row in rows:
            query_id = row["query_id"]
            positive = {
                chunk_id for chunk_id, grade in final_qrels[query_id].items() if grade > 0
            }
            retrieved = set(rankings[system][query_id][:10])
            if positive.issubset(retrieved):
                continue
            failure_rows.append(
                {
                    "category": row["category"],
                    "failure_id": f"{system}:{query_id}",
                    "missing_positive_chunk_ids": sorted(positive - retrieved),
                    "query_id": query_id,
                    "recall_at_10": row["metrics"]["recall_at_10"],
                    "system": system,
                    "taxonomy": (
                        "no_positive_in_top10"
                        if not (positive & retrieved)
                        else "incomplete_multi_evidence_top10"
                    ),
                    "top10_chunk_ids": rankings[system][query_id][:10],
                }
            )

    uncertainty: dict[str, Any] = {}
    for system in rankings:
        uncertainty[system] = {}
        for slice_name, categories in (
            ("aggregate", None),
            *((category, {category}) for category in evaluation.CATEGORIES),
        ):
            left = evaluation.slice_rows(final_rows, system, categories)
            right = evaluation.slice_rows(final_rows, "bm25", categories)
            uncertainty[system][slice_name] = {
                "comparator": "bm25",
                "metric_intervals": {
                    metric: evaluation.paired_bootstrap(left, right, metric)
                    for metric in evaluation.METRICS
                },
                "query_n": len(left),
            }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "known_gold_metrics.json", known_metrics, overwrite=args.overwrite)
    write_jsonl(
        output_dir / "known_gold_per_query.jsonl",
        known_rows,
        key="row_id",
        overwrite=args.overwrite,
    )
    write_json(output_dir / "balanced_metrics.json", final_metrics, overwrite=args.overwrite)
    write_jsonl(
        output_dir / "final_pooled_per_query.jsonl",
        final_per_query_rows,
        key="row_id",
        overwrite=args.overwrite,
    )
    write_json(
        output_dir / "paired_uncertainty_vs_bm25.json",
        uncertainty,
        overwrite=args.overwrite,
    )
    write_jsonl(
        output_dir / "failure_taxonomy.jsonl",
        failure_rows,
        key="failure_id",
        overwrite=args.overwrite,
    )
    write_json(
        output_dir / "efficiency_snapshot.json",
        evaluation.efficiency_snapshot(args),
        overwrite=args.overwrite,
    )
    write_json(output_dir / "system_comparison_table.json", comparison, overwrite=args.overwrite)
    write_json(
        output_dir / "known_gold_vs_final_pooled_shifts.json",
        shifts,
        overwrite=args.overwrite,
    )
    write_json(
        output_dir / "prompt_rag_candidate_recall_ceiling.json",
        ceiling_report,
        overwrite=args.overwrite,
    )
    write_json(output_dir / "worst_query_traces.json", worst, overwrite=args.overwrite)

    input_paths = (
        args.chunks,
        args.qa,
        args.known_gold_qrels,
        args.final_qrels,
        *ranking_paths.values(),
        args.phase2a_efficiency,
        args.graph_manifest,
        args.hybrid_latency,
        args.prompt_trace_operational,
        args.prompt_full_operational,
    )
    output_paths = tuple(output_dir / name for name in output_names if name != "supplement_manifest.json")
    manifest = {
        "code_hashes": {
            "scripts/evaluate_phase6_seed42.py": sha256_file(
                ROOT / "scripts/evaluate_phase6_seed42.py"
            ),
            "scripts/supplement_phase6_seed42_final_metrics.py": sha256_file(
                ROOT / "scripts/supplement_phase6_seed42_final_metrics.py"
            ),
        },
        "inputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in input_paths},
        "git_head_at_execution": args.git_head,
        "outputs": {str(path.relative_to(ROOT)): sha256_file(path) for path in output_paths},
        "status": "frozen",
    }
    write_json(output_dir / "supplement_manifest.json", manifest, overwrite=args.overwrite)
    print(json.dumps({"candidate_ceiling": ceiling_report["aggregate_macro_mean"]}, sort_keys=True))


if __name__ == "__main__":
    main()
