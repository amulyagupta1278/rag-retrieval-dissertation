#!/usr/bin/env python3
"""Run BM25/dense model selection on development queries only.

Execution is blocked until the 60-question audit summary explicitly records
completion. Every candidate receives separate index and run directories.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

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


def _aggregate_metrics(path: Path) -> dict[str, float]:
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["query_category"] == "all":
                return {
                    "mrr_at_10": float(row["mrr@10"]), "recall_at_10": float(row["recall@10"]),
                    "ndcg_at_10": float(row["ndcg@10"]), "avg_latency_ms": float(row["avg_latency_ms"]),
                }
    raise RuntimeError(f"Aggregate row missing: {path}")


def _common(args: argparse.Namespace) -> list[str]:
    return [
        "--top-k", "10", "--rebuild", "--split", "dev",
        "--chunks", args.chunks, "--qa-dataset", args.qa, "--qrels", args.qrels,
        "--query-categories", args.categories, "--config", args.config,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-summary", required=True)
    parser.add_argument("--qrels-audit-summary", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--categories", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--mode", choices=("bm25", "dense", "all"), default="all")
    parser.add_argument("--output-root", default="runs/model_selection/v3_clean")
    parser.add_argument("--index-root", default="indexes/model_selection/v3_clean")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    if audit.get("audit_status") != "complete" or audit.get("questions_reviewed") != 60:
        raise RuntimeError("P2 is locked until the 60/60 human audit is explicitly complete")
    qrels_audit = json.loads(Path(args.qrels_audit_summary).read_text(encoding="utf-8"))
    qrels_hash = hashlib.sha256(Path(args.qrels).read_bytes()).hexdigest()
    if (
        qrels_audit.get("qrels_audit_status") != "complete"
        or qrels_audit.get("audited_qrels_sha256") != qrels_hash
    ):
        raise RuntimeError("P2 is locked until pooled qrels review is complete and hash-aligned")
    qa = [json.loads(line) for line in Path(args.qa).read_text(encoding="utf-8").splitlines() if line.strip()]
    dev_count = sum(item.get("split") == "dev" for item in qa)
    test_count = sum(item.get("split") == "test" for item in qa)
    if not dev_count or not test_count:
        raise RuntimeError("Frozen dev/test split is missing")
    results: dict[str, dict] = {"protocol": {"selection_split": "dev", "dev_queries": dev_count, "test_queries_unseen": test_count}}
    output_root, index_root = Path(args.output_root), Path(args.index_root)

    if args.mode in {"bm25", "all"}:
        candidates = {}
        for config in BM25_GRID:
            output, index = output_root / config["slug"], index_root / config["slug"] / "bm25_index.pkl"
            _run([
                sys.executable, "experiments/run_bm25.py", *_common(args),
                "--k1", str(config["k1"]), "--b", str(config["b"]),
                "--index-path", str(index), "--output-root", str(output),
            ])
            candidates[config["slug"]] = {**config, **_aggregate_metrics(output / "metrics/bm25_metrics.csv")}
        selected = max(candidates, key=lambda slug: (
            candidates[slug]["ndcg_at_10"], candidates[slug]["recall_at_10"],
            -candidates[slug]["avg_latency_ms"], slug,
        ))
        results["bm25"] = {"candidates": candidates, "selected": selected}

    if args.mode in {"dense", "all"}:
        candidates = {}
        for config in DENSE_GRID:
            output, index = output_root / config["slug"], index_root / config["slug"]
            normalize_flag = "--normalize-embeddings" if config["normalize"] else "--no-normalize-embeddings"
            _run([
                sys.executable, "experiments/run_faiss.py", *_common(args),
                "--model-name", config["model"], "--model-revision", config["revision"],
                "--similarity-metric", config["metric"], normalize_flag,
                "--query-prefix", config["query_prefix"], "--passage-prefix", config["passage_prefix"],
                "--index-dir", str(index), "--output-root", str(output),
            ])
            candidates[config["slug"]] = {**config, **_aggregate_metrics(output / "metrics/faiss_metrics.csv")}
        baseline = candidates["minilm_l2_unnormalized"]
        best = max(candidates, key=lambda slug: (
            candidates[slug]["ndcg_at_10"], candidates[slug]["recall_at_10"],
            -candidates[slug]["avg_latency_ms"], slug,
        ))
        candidate = candidates[best]
        passes = (
            candidate["ndcg_at_10"] >= baseline["ndcg_at_10"] + 0.01
            or (
                candidate["recall_at_10"] >= baseline["recall_at_10"] + 0.03
                and candidate["ndcg_at_10"] >= baseline["ndcg_at_10"] - 0.01
            )
        )
        selected = best if passes else "minilm_l2_unnormalized"
        results["dense"] = {
            "candidates": candidates, "best_candidate": best,
            "stop_rule_passed": passes, "selected": selected,
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
