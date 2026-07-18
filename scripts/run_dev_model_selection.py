#!/usr/bin/env python3
"""Five-fold nested selection for frozen BM25 and dense candidate grids."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.statistics import query_level_metrics
from src.utils.io_utils import load_jsonl

BM25_GRID = [
    {"k1": k1, "b": b, "slug": f"bm25_k1_{k1}_b_{b}"}
    for k1 in (0.9, 1.2, 1.5, 1.8) for b in (0.4, 0.6, 0.75, 0.9)
]
DENSE_GRID = [
    {
        "slug": "minilm_l2_unnormalized", "model": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", "metric": "l2", "normalize": False,
        "query_prefix": "", "passage_prefix": "",
    },
    {
        "slug": "minilm_cosine_normalized", "model": "sentence-transformers/all-MiniLM-L6-v2",
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", "metric": "cosine", "normalize": True,
        "query_prefix": "", "passage_prefix": "",
    },
    {
        "slug": "bge_small_cosine", "model": "BAAI/bge-small-en-v1.5",
        "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a", "metric": "cosine", "normalize": True,
        "query_prefix": "", "passage_prefix": "",
    },
    {
        "slug": "bge_small_cosine_instruction", "model": "BAAI/bge-small-en-v1.5",
        "revision": "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a", "metric": "cosine", "normalize": True,
        "query_prefix": "Represent this sentence for searching relevant passages: ", "passage_prefix": "",
    },
    {
        "slug": "e5_small_v2_cosine_prefixes", "model": "intfloat/e5-small-v2",
        "revision": "ffb93f3bd4047442299a41ebb6fa998a38507c52", "metric": "cosine", "normalize": True,
        "query_prefix": "query: ", "passage_prefix": "passage: ",
    },
]


def _run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env={**os.environ, "PYTHONHASHSEED": "0"}, check=True)


def _mean(rows: dict[str, dict[str, float]], ids: set[str], metric: str) -> float:
    values = [rows[qid][metric] for qid in sorted(ids)]
    return sum(values) / len(values) if values else 0.0


def _objective(
    rows: dict[str, dict[str, float]], ids: set[str], qa_by_id: dict[str, dict], family: str,
) -> tuple[float, float, float]:
    target_categories = (
        {"exact_match", "terminology_heavy"} if family == "bm25" else {"paraphrase"}
    )
    target = {qid for qid in ids if qa_by_id[qid]["category"] in target_categories}
    return (
        _mean(rows, target, "ndcg_at_10"),
        _mean(rows, ids, "ndcg_at_10"),
        _mean(rows, ids, "recall_at_10"),
    )


def _nested_selection(
    candidates: dict[str, dict], qa: list[dict], family: str, baseline_slug: str,
) -> dict:
    qa_by_id = {item["question_id"]: item for item in qa}
    all_ids = set(qa_by_id)
    fold_selections: list[dict] = []
    oof_rows: dict[str, dict[str, float]] = {}
    selection_frequency: Counter = Counter()
    training_scores: dict[str, list[float]] = {slug: [] for slug in candidates}
    for held_out in range(5):
        validation_ids = {qid for qid, item in qa_by_id.items() if item["fold_id"] == held_out}
        training_ids = all_ids - validation_ids
        scored = {}
        for slug, candidate in candidates.items():
            objective = _objective(candidate["query_metrics"], training_ids, qa_by_id, family)
            training_scores[slug].append(objective[0])
            scored[slug] = objective
        selected = max(
            candidates,
            key=lambda slug: (*scored[slug], -candidates[slug]["latency_ms"], slug),
        )
        selection_frequency[selected] += 1
        for qid in validation_ids:
            oof_rows[qid] = candidates[selected]["query_metrics"][qid]
        fold_selections.append({
            "held_out_fold": held_out,
            "training_queries": len(training_ids),
            "validation_queries": len(validation_ids),
            "selected": selected,
            "training_objective": scored[selected],
        })
    selected = max(
        candidates,
        key=lambda slug: (
            selection_frequency[slug],
            sum(training_scores[slug]) / len(training_scores[slug]),
            -candidates[slug]["latency_ms"], slug,
        ),
    )
    baseline = candidates[baseline_slug]["query_metrics"]
    selected_ndcg = _mean(oof_rows, all_ids, "ndcg_at_10")
    selected_recall = _mean(oof_rows, all_ids, "recall_at_10")
    baseline_ndcg = _mean(baseline, all_ids, "ndcg_at_10")
    baseline_recall = _mean(baseline, all_ids, "recall_at_10")
    oof_passes = (
        selected_ndcg >= baseline_ndcg + 0.01
        or (selected_recall >= baseline_recall + 0.03 and selected_ndcg >= baseline_ndcg - 0.01)
    )
    final_rows = candidates[selected]["query_metrics"]
    final_ndcg = _mean(final_rows, all_ids, "ndcg_at_10")
    final_recall = _mean(final_rows, all_ids, "recall_at_10")
    final_passes = (
        final_ndcg >= baseline_ndcg + 0.01
        or (final_recall >= baseline_recall + 0.03 and final_ndcg >= baseline_ndcg - 0.01)
    )
    passes = oof_passes and final_passes
    retained = selected if passes else baseline_slug
    return {
        "fold_selections": fold_selections,
        "selection_frequency": dict(sorted(selection_frequency.items())),
        "selected_by_nested_cv": selected,
        "baseline": baseline_slug,
        "oof_metrics": {
            "ndcg_at_10": selected_ndcg,
            "recall_at_10": selected_recall,
            "baseline_ndcg_at_10": baseline_ndcg,
            "baseline_recall_at_10": baseline_recall,
            "final_candidate_ndcg_at_10": final_ndcg,
            "final_candidate_recall_at_10": final_recall,
        },
        "oof_stop_rule_passed": oof_passes,
        "final_candidate_stop_rule_passed": final_passes,
        "stop_rule_passed": passes,
        "selected": retained,
    }


def _validate_gate(args: argparse.Namespace, qa: list[dict]) -> None:
    audit = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    if not audit.get("agreement_gate_passed") or audit.get("questions_reviewed") != 100:
        raise RuntimeError("Selection locked until 100-question and inter-review gates pass")
    benchmark = json.loads(Path(args.benchmark_manifest).read_text(encoding="utf-8"))
    if benchmark.get("status") != "reviewed_development_benchmark_published":
        raise RuntimeError("Selection locked until reviewed benchmark publication passes")
    qrels_audit = json.loads(Path(args.qrels_audit_summary).read_text(encoding="utf-8"))
    qrels_hash = hashlib.sha256(Path(args.qrels).read_bytes()).hexdigest()
    if qrels_audit.get("qrels_audit_status") != "complete" or qrels_audit.get("audited_qrels_sha256") != qrels_hash:
        raise RuntimeError("Selection locked until blind pooled qrels are complete and hash-aligned")
    if len(qa) != 100 or any(item.get("split") != "dev" for item in qa):
        raise RuntimeError("Expected 100 exploratory development questions")
    fold_counts = Counter((item["category"], item.get("fold_id")) for item in qa)
    if any(fold_counts[(category, fold)] != 4 for category in {
        "exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop"
    } for fold in range(5)):
        raise RuntimeError("Development folds are not balanced at four questions/category/fold")


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
    parser.add_argument("--mode", choices=("bm25", "dense", "all"), default="all")
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean_benchmark_r1")
    parser.add_argument("--index-root", default="indexes/model_selection/v3_clean_benchmark_r1")
    args = parser.parse_args()
    qa = load_jsonl(args.qa)
    _validate_gate(args, qa)
    qrels = QRelsBuilder.load_qrels_tsv(args.qrels)
    results: dict[str, dict] = {
        "protocol": {
            "selection": "five_fold_nested", "queries": 100, "folds": 5,
            "primary_metric": "ndcg_at_10", "benchmark_version": "v3_clean_benchmark_r1",
        }
    }
    output_root, index_root = Path(args.output_root), Path(args.index_root)
    common = [
        "--top-k", "50", "--rebuild", "--split", "dev", "--require-index-provenance",
        "--chunks", args.chunks, "--qa-dataset", args.qa, "--qrels", args.qrels,
        "--query-categories", args.categories, "--config", args.config,
    ]

    if args.mode in {"bm25", "all"}:
        candidates = {}
        for config in BM25_GRID:
            output = output_root / config["slug"]
            index = index_root / config["slug"] / "bm25_index.pkl"
            _run([
                sys.executable, "experiments/run_bm25.py", *common,
                "--k1", str(config["k1"]), "--b", str(config["b"]),
                "--index-path", str(index), "--output-root", str(output),
            ])
            rows = query_level_metrics(load_jsonl(output / "retrieval/bm25_run.jsonl"), qrels)
            candidates[config["slug"]] = {
                **config, "query_metrics": rows,
                "latency_ms": sum(row["latency_ms"] for row in rows.values()) / len(rows),
            }
        decision = _nested_selection(candidates, qa, "bm25", "bm25_k1_1.5_b_0.75")
        decision["selected_run"] = str(
            output_root / decision["selected"] / "retrieval/bm25_run.jsonl"
        )
        results["bm25"] = {
            "candidate_configs": {slug: {k: v for k, v in value.items() if k != "query_metrics"} for slug, value in candidates.items()},
            **decision,
        }

    if args.mode in {"dense", "all"}:
        candidates = {}
        for config in DENSE_GRID:
            output = output_root / config["slug"]
            index = index_root / config["slug"]
            normalize = "--normalize-embeddings" if config["normalize"] else "--no-normalize-embeddings"
            _run([
                sys.executable, "experiments/run_faiss.py", *common,
                "--model-name", config["model"], "--model-revision", config["revision"],
                "--similarity-metric", config["metric"], normalize,
                "--query-prefix", config["query_prefix"], "--passage-prefix", config["passage_prefix"],
                "--index-dir", str(index), "--output-root", str(output),
            ])
            rows = query_level_metrics(load_jsonl(output / "retrieval/faiss_run.jsonl"), qrels)
            candidates[config["slug"]] = {
                **config, "query_metrics": rows,
                "latency_ms": sum(row["latency_ms"] for row in rows.values()) / len(rows),
            }
        decision = _nested_selection(candidates, qa, "dense", "minilm_l2_unnormalized")
        decision["selected_run"] = str(
            output_root / decision["selected"] / "retrieval/faiss_run.jsonl"
        )
        results["dense"] = {
            "candidate_configs": {slug: {k: v for k, v in value.items() if k != "query_metrics"} for slug, value in candidates.items()},
            **decision,
        }
    output_root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(results, indent=2, sort_keys=True) + "\n"
    (output_root / "model_selection.json").write_text(payload, encoding="utf-8")
    (output_root / "model_selection.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "  model_selection.json\n", encoding="utf-8"
    )
    print(json.dumps({key: value.get("selected") for key, value in results.items() if key != "protocol"}, indent=2))


if __name__ == "__main__":
    main()
