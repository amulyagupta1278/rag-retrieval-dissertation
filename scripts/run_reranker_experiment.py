#!/usr/bin/env python3
"""Evaluate direct cross-encoder reranking after baseline configuration freeze."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sentence_transformers import CrossEncoder

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.statistics import query_level_metrics
from src.utils.io_utils import load_jsonl, save_jsonl

MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
REVISION = "c5ee24cb16019beea0893ab7796b1df96625c6b8"


def _mean(rows: dict[str, dict[str, float]], metric: str) -> float:
    return sum(row[metric] for row in rows.values()) / len(rows)


def _index_runs(runs: list[dict], expected: set[str], name: str) -> dict[str, dict]:
    indexed = {run["query_id"]: run for run in runs}
    if len(indexed) != len(runs) or set(indexed) != expected:
        raise RuntimeError(f"{name} run does not exactly cover development benchmark")
    if any(len(run.get("results", [])) < 50 for run in runs):
        raise RuntimeError(f"{name} reranking input must contain top 50 results/query")
    return indexed


def _validate_selected_configuration(
    indexed: dict[str, dict], selection: dict, family: str,
) -> None:
    slug = selection[family]["selected"]
    expected = selection[family]["candidate_configs"][slug]
    keys = (
        ("k1", "b") if family == "bm25" else
        ("model_name", "model_revision", "similarity_metric", "normalize_embeddings", "query_prefix", "passage_prefix")
    )
    expected_alias = {
        "model_name": expected.get("model"), "model_revision": expected.get("revision"),
        "similarity_metric": expected.get("metric"), "normalize_embeddings": expected.get("normalize"),
        "query_prefix": expected.get("query_prefix"), "passage_prefix": expected.get("passage_prefix"),
        "k1": expected.get("k1"), "b": expected.get("b"),
    }
    for run in indexed.values():
        snapshot = run.get("config_snapshot", {})
        mismatches = {
            key: (expected_alias[key], snapshot.get(key)) for key in keys
            if expected_alias[key] != snapshot.get(key)
        }
        if mismatches:
            raise RuntimeError(f"{family} run does not match selected configuration {slug}: {mismatches}")


def _candidate_pool(left: dict, right: dict, mode: str) -> list[dict]:
    if mode == "bm25":
        return left["results"][:50]
    if mode == "dense":
        return right["results"][:50]
    combined: dict[str, dict] = {}
    for result in left["results"][:50] + right["results"][:50]:
        combined.setdefault(result["chunk_id"], result)
    return list(combined.values())[:100]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-selection", required=True)
    parser.add_argument("--bm25-run", required=True)
    parser.add_argument("--dense-run", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean_benchmark_r1/reranker")
    args = parser.parse_args()
    selection = json.loads(Path(args.model_selection).read_text(encoding="utf-8"))
    if not selection.get("bm25", {}).get("selected") or not selection.get("dense", {}).get("selected"):
        raise RuntimeError("BM25 and dense selections must be frozen before reranking")
    qa = load_jsonl(args.qa)
    dev_ids = {item["question_id"] for item in qa if item.get("split") == "dev"}
    if len(dev_ids) != 100:
        raise RuntimeError("Reranker selection expects 100 development questions")
    bm25 = _index_runs(load_jsonl(args.bm25_run), dev_ids, "BM25")
    dense = _index_runs(load_jsonl(args.dense_run), dev_ids, "dense")
    _validate_selected_configuration(bm25, selection, "bm25")
    _validate_selected_configuration(dense, selection, "dense")
    model = CrossEncoder(MODEL, revision=REVISION)
    evaluator = RetrievalEvaluator(
        args.qrels, args.categories, qa_dataset_path=args.qa, split="dev",
        chunks_path=args.chunks,
    )
    qrels = QRelsBuilder.load_qrels_tsv(args.qrels)
    output = Path(args.output_root)
    metrics: dict[str, dict] = {}
    input_runs = {"bm25": list(bm25.values()), "dense": list(dense.values())}
    for name, runs in input_runs.items():
        rows = query_level_metrics(runs, qrels)
        metrics[f"input_{name}"] = {
            "ndcg_at_10": _mean(rows, "ndcg_at_10"),
            "recall_at_10": _mean(rows, "recall_at_10"),
        }
    generated_paths = {}
    for mode in ("bm25", "dense", "union"):
        for depth in (20, 50, 100):
            if mode != "union" and depth == 100:
                continue
            reranked = []
            for query_id in sorted(dev_ids):
                base = bm25[query_id]
                candidates = _candidate_pool(base, dense[query_id], mode)[:depth]
                pairs = [(base["query_text"], result.get("text", "")) for result in candidates]
                start = time.perf_counter_ns()
                scores = model.predict(pairs, show_progress_bar=False)
                rerank_ms = (time.perf_counter_ns() - start) / 1_000_000
                ordered = sorted(
                    zip(candidates, scores), key=lambda item: (-float(item[1]), item[0]["chunk_id"]),
                )
                results = [
                    {
                        **result, "rank": rank, "score": float(score),
                        "retriever": "cross_encoder_reranker",
                        "extra": {
                            **result.get("extra", {}), "reranker_model": MODEL,
                            "reranker_revision": REVISION, "candidate_mode": mode,
                            "rerank_depth": depth,
                        },
                    }
                    for rank, (result, score) in enumerate(ordered, 1)
                ]
                retrieval_latency = (
                    float(base.get("total_latency_ms", 0.0)) if mode == "bm25" else
                    float(dense[query_id].get("total_latency_ms", 0.0)) if mode == "dense" else
                    float(base.get("total_latency_ms", 0.0)) + float(dense[query_id].get("total_latency_ms", 0.0))
                )
                reranked.append({
                    "query_id": query_id, "query_text": base["query_text"],
                    "retriever": "cross_encoder_reranker", "top_k": len(results),
                    "total_latency_ms": retrieval_latency + rerank_ms,
                    "results": results,
                    "config_snapshot": {
                        "model": MODEL, "revision": REVISION, "candidate_mode": mode,
                        "rerank_depth": depth, "selection_split": "dev",
                    },
                })
            slug = f"{mode}_top_{depth}"
            run_path = output / slug / "retrieval/reranked_run.jsonl"
            save_jsonl(reranked, run_path)
            generated_paths[slug] = str(run_path)
            bundles = evaluator.evaluate_run_file(run_path, retriever_name=slug)
            evaluator.save_metrics_csv(bundles, output / slug / "metrics/reranker_metrics.csv")
            rows = query_level_metrics(reranked, qrels)
            metrics[slug] = {
                "ndcg_at_10": _mean(rows, "ndcg_at_10"),
                "recall_at_10": _mean(rows, "recall_at_10"),
                "mrr_at_10": _mean(rows, "mrr_at_10"),
            }
    candidate_names = [name for name in metrics if not name.startswith("input_")]
    best = max(candidate_names, key=lambda name: (metrics[name]["ndcg_at_10"], metrics[name]["recall_at_10"], name))
    baseline_name = max(("input_bm25", "input_dense"), key=lambda name: metrics[name]["ndcg_at_10"])
    ndcg_gain = metrics[best]["ndcg_at_10"] - metrics[baseline_name]["ndcg_at_10"]
    recall_loss = metrics[baseline_name]["recall_at_10"] - metrics[best]["recall_at_10"]
    passes = ndcg_gain >= 0.01 and recall_loss <= 0.02
    report = {
        "selection_split": "dev", "model": MODEL, "revision": REVISION,
        "metrics": metrics, "run_paths": generated_paths, "best_candidate": best,
        "baseline": baseline_name, "ndcg_at_10_gain": ndcg_gain,
        "recall_at_10_loss": recall_loss, "stop_rule_passed": passes,
        "selected": best if passes else baseline_name.removeprefix("input_"),
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "reranker_decision.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
