#!/usr/bin/env python3
"""Create blind top-10 holdout pool from frozen system runs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.evaluator import RetrievalEvaluator
from src.evaluation.holdout_lock import verify_lock
from src.utils.io_utils import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--gold-qrels", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=run.jsonl")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    lock = verify_lock(args.lock, ROOT)
    qa = load_jsonl(args.qa)
    expected = {item["question_id"] for item in qa}
    if len(expected) != 50 or any(item.get("split") != "holdout" for item in qa):
        raise RuntimeError("Expected immutable 50-question holdout")
    chunks = {chunk["chunk_id"]: chunk for chunk in load_jsonl(args.chunks)}
    gold = QRelsBuilder.load_qrels_tsv(args.gold_qrels)
    pool: dict[str, dict[str, dict]] = defaultdict(dict)
    for value in args.run:
        if "=" not in value:
            raise ValueError("--run must use NAME=PATH")
        name, path = value.split("=", 1)
        RetrievalEvaluator(
            args.gold_qrels, qa_dataset_path=args.qa, split="holdout",
            chunks_path=args.chunks,
        ).evaluate_run_file(path, retriever_name=name)
        for run in load_jsonl(path):
            for result in run.get("results", [])[:10]:
                pool[run["query_id"]].setdefault(result["chunk_id"], {})[name] = {
                    "rank": result["rank"], "score": result["score"],
                }
    records = []
    qa_by_id = {item["question_id"]: item for item in qa}
    for query_id in sorted(expected):
        for index, (chunk_id, provenance) in enumerate(sorted(pool[query_id].items()), 1):
            records.append({
                "candidate_id": f"{query_id}_candidate_{index:03d}",
                "query_id": query_id, "category": qa_by_id[query_id]["category"],
                "question": qa_by_id[query_id]["question"], "chunk_id": chunk_id,
                "candidate_text": chunks[chunk_id]["text"],
                "original_relevance": gold.get(query_id, {}).get(chunk_id),
                "systems": provenance, "review_status": "pending", "reviewer": None,
                "relevance": None, "rationale": None, "second_reviewer_relevance": None,
            })
    output = Path(args.output_dir)
    if output.exists():
        raise FileExistsError("Holdout judgment pool is immutable once created")
    output.mkdir(parents=True)
    with (output / "pool_internal.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            internal = {key: value for key, value in record.items() if key not in {"candidate_text", "question"}}
            handle.write(json.dumps(internal, ensure_ascii=False, sort_keys=True) + "\n")
    blind_fields = (
        "candidate_id", "query_id", "category", "question", "chunk_id", "candidate_text",
        "review_status", "reviewer", "relevance", "rationale",
        "second_reviewer_relevance",
    )
    with (output / "pool_blind.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=blind_fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: record.get(key) for key in blind_fields} for record in records)
    manifest = {
        "configuration_lock_id": lock["lock_id"], "queries": 50,
        "pool_depth": 10, "unique_candidates": len(records),
        "status": "pending_blind_relevance_review",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
