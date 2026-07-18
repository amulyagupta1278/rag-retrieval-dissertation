#!/usr/bin/env python3
"""Select G0–G5 retrieval-time ablations for Entity-Co-occurrence Graph Retrieval."""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.statistics import query_level_metrics
from src.retrievers.graphrag_retriever import GraphRAGRetriever
from src.utils.io_utils import load_jsonl

ABLATIONS = {
    "g0_current": {},
    "g1_seed_filtering": {"seed_filtering": True},
    "g2_verified_aliases": {"seed_filtering": True, "use_aliases": True},
    "g3_hub_penalty": {"seed_filtering": True, "use_aliases": True, "hub_penalty": True},
    "g4_dual_entity_coverage": {
        "seed_filtering": True, "use_aliases": True, "hub_penalty": True,
        "dual_entity_coverage": True,
    },
    "g5_lexical_fallback": {
        "seed_filtering": True, "use_aliases": True, "hub_penalty": True,
        "dual_entity_coverage": True, "lexical_fallback": True,
    },
}


def _flags(config: dict) -> list[str]:
    mapping = {
        "seed_filtering": "--seed-filtering", "use_aliases": "--use-aliases",
        "hub_penalty": "--hub-penalty", "dual_entity_coverage": "--dual-entity-coverage",
        "lexical_fallback": "--lexical-fallback",
    }
    return [flag for key, flag in mapping.items() if config.get(key)]


def _mean(rows: dict[str, dict[str, float]], ids: set[str], metric: str) -> float:
    values = [rows[qid][metric] for qid in sorted(ids)]
    return sum(values) / len(values) if values else 0.0


def _nested(candidates: dict[str, dict], qa: list[dict]) -> dict:
    qa_by_id = {item["question_id"]: item for item in qa}
    all_ids = set(qa_by_id)
    frequency: Counter = Counter()
    folds = []
    oof: dict[str, dict[str, float]] = {}
    train_scores = {name: [] for name in candidates}
    for held_out in range(5):
        validation = {qid for qid, item in qa_by_id.items() if item["fold_id"] == held_out}
        training = all_ids - validation
        cross = {qid for qid in training if qa_by_id[qid]["category"] in {"entity_relation", "multi_hop"}}
        scores = {}
        for name, candidate in candidates.items():
            rows = candidate["rows"]
            scores[name] = (
                _mean(rows, cross, "ndcg_at_10"),
                _mean(rows, training, "ndcg_at_10"),
                _mean(rows, cross, "recall_at_10"),
            )
            train_scores[name].append(scores[name][0])
        selected = max(candidates, key=lambda name: (*scores[name], name))
        frequency[selected] += 1
        for qid in validation:
            oof[qid] = candidates[selected]["rows"][qid]
        folds.append({"held_out_fold": held_out, "selected": selected, "training_objective": scores[selected]})
    selected = max(
        candidates,
        key=lambda name: (frequency[name], sum(train_scores[name]) / len(train_scores[name]), name),
    )
    cross_all = {qid for qid in all_ids if qa_by_id[qid]["category"] in {"entity_relation", "multi_hop"}}
    baseline = candidates["g0_current"]["rows"]
    cross_gain = _mean(oof, cross_all, "ndcg_at_10") - _mean(baseline, cross_all, "ndcg_at_10")
    recall_gain = _mean(oof, cross_all, "recall_at_10") - _mean(baseline, cross_all, "recall_at_10")
    aggregate_loss = _mean(baseline, all_ids, "ndcg_at_10") - _mean(oof, all_ids, "ndcg_at_10")
    selected_rows = candidates[selected]["rows"]
    final_cross_gain = _mean(selected_rows, cross_all, "ndcg_at_10") - _mean(baseline, cross_all, "ndcg_at_10")
    final_recall_gain = _mean(selected_rows, cross_all, "recall_at_10") - _mean(baseline, cross_all, "recall_at_10")
    final_aggregate_loss = _mean(baseline, all_ids, "ndcg_at_10") - _mean(selected_rows, all_ids, "ndcg_at_10")
    oof_passes = cross_gain >= 0.05 and recall_gain >= 0.10 and aggregate_loss <= 0.02
    final_passes = final_cross_gain >= 0.05 and final_recall_gain >= 0.10 and final_aggregate_loss <= 0.02
    passes = oof_passes and final_passes
    return {
        "fold_selections": folds, "selection_frequency": dict(sorted(frequency.items())),
        "selected_by_nested_cv": selected,
        "oof_cross_ndcg_gain": cross_gain, "oof_both_gold_recall_gain": recall_gain,
        "oof_aggregate_ndcg_loss": aggregate_loss, "stop_rule_passed": passes,
        "final_cross_ndcg_gain": final_cross_gain,
        "final_both_gold_recall_gain": final_recall_gain,
        "final_aggregate_ndcg_loss": final_aggregate_loss,
        "oof_stop_rule_passed": oof_passes, "final_candidate_stop_rule_passed": final_passes,
        "selected": selected if passes else "g0_current",
    }


def _audit_graph(
    graph_dir: Path, chunks: str, qa: list[dict], config: dict, output: Path, seed: int,
) -> None:
    retriever = GraphRAGRetriever(
        graph_path=graph_dir / "graph.gpickle", nodes_path=graph_dir / "nodes.jsonl",
        edges_path=graph_dir / "edges.jsonl", chunks_path=chunks, **config,
    )
    retriever.load_index()
    entities = sorted(
        (node for node, data in retriever._graph.nodes(data=True) if data.get("type") == "entity")
    )
    rng = random.Random(seed)
    entity_sample = [
        {
            "entity": entity, "degree": retriever._graph.degree(entity),
            "review_status": "pending", "reviewer": None,
            "valid_entity": None, "schema_leakage_absent": None, "rationale": None,
        }
        for entity in sorted(rng.sample(entities, min(100, len(entities))))
    ]
    hubs = sorted(
        ({"node": node, "degree": retriever._graph.degree(node)} for node in entities),
        key=lambda value: (-value["degree"], value["node"]),
    )[:20]
    alias_collisions = {
        alias: nodes for alias, nodes in retriever._aliases.items() if len(nodes) > 1
    }
    by_category: dict[str, list[dict]] = {}
    for category in sorted({item["category"] for item in qa}):
        values = sorted((item for item in qa if item["category"] == category), key=lambda item: item["question_id"])
        by_category[category] = rng.sample(values, 6)
    traces = []
    for item in sorted((value for values in by_category.values() for value in values), key=lambda value: value["question_id"]):
        retriever.retrieve(item["question"], top_k=10)
        traces.append({
            "query_id": item["question_id"], "category": item["category"],
            **retriever.last_trace,
            "human_review": {
                "review_status": "pending", "reviewer": None,
                "accepted_seeds_correct": None, "rejected_seeds_correct": None,
                "ranking_path_plausible": None, "rationale": None,
            },
        })
    output.mkdir(parents=True, exist_ok=True)
    (output / "entity_audit_100.json").write_text(json.dumps(entity_sample, indent=2) + "\n", encoding="utf-8")
    (output / "top_hubs_20.json").write_text(json.dumps(hubs, indent=2) + "\n", encoding="utf-8")
    (output / "alias_collisions.json").write_text(json.dumps(alias_collisions, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "seed_traces_30.jsonl").open("w", encoding="utf-8") as handle:
        for trace in traces:
            handle.write(json.dumps(trace, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-summary", required=True)
    parser.add_argument("--benchmark-manifest", required=True)
    parser.add_argument("--qrels-audit-summary", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--index-root", default="indexes/model_selection/v3_clean_benchmark_r1/entity_graph")
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean_benchmark_r1/entity_graph")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    benchmark = json.loads(Path(args.benchmark_manifest).read_text(encoding="utf-8"))
    qrels_audit = json.loads(Path(args.qrels_audit_summary).read_text(encoding="utf-8"))
    if not audit.get("agreement_gate_passed") or benchmark.get("status") != "reviewed_development_benchmark_published" or qrels_audit.get("qrels_audit_status") != "complete":
        raise RuntimeError("Graph ablations locked until benchmark and pooled judgments pass")
    qa = load_jsonl(args.qa)
    qrels = QRelsBuilder.load_qrels_tsv(args.qrels)
    index_root, output_root = Path(args.index_root), Path(args.output_root)
    candidates = {}
    for index, (name, config) in enumerate(ABLATIONS.items()):
        output = output_root / name
        command = [
            sys.executable, "experiments/run_graphrag.py", "--top-k", "10", "--split", "dev",
            "--require-index-provenance", "--chunks", args.chunks, "--qa-dataset", args.qa,
            "--qrels", args.qrels, "--query-categories", args.categories, "--config", args.config,
            "--graph-dir", str(index_root), "--output-root", str(output), *_flags(config),
        ]
        if index == 0:
            command.append("--rebuild")
        print("+", " ".join(command), flush=True)
        subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": "0"}, check=True)
        run_path = output / "retrieval/graphrag_run.jsonl"
        candidates[name] = {"config": config, "rows": query_level_metrics(load_jsonl(run_path), qrels)}
    decision = _nested(candidates, qa)
    decision["selected_run"] = str(
        output_root / decision["selected"] / "retrieval/graphrag_run.jsonl"
    )
    report = {
        "protocol": "five_fold_nested_entity_cooccurrence_ablations",
        "candidate_configs": ABLATIONS, **decision,
        "graph_audit_status": "pending_human_review",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "ablation_decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _audit_graph(index_root, args.chunks, qa, ABLATIONS[decision["selected"]], output_root / "audit", args.seed)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
