#!/usr/bin/env python3
"""Create blind initial or one-time residual top-5 relevance pool."""

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
from src.utils.io_utils import load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=run.jsonl")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--include-existing-gold", action="store_true")
    args = parser.parse_args()
    qa = load_jsonl(args.qa)
    qa_by_id = {item["question_id"]: item for item in qa}
    expected = set(qa_by_id)
    chunks = {chunk["chunk_id"]: chunk for chunk in load_jsonl(args.chunks)}
    judged = QRelsBuilder.load_qrels_tsv(args.qrels)
    pool: dict[str, dict[str, dict]] = defaultdict(dict)
    for value in args.run:
        if "=" not in value:
            raise ValueError("--run must use NAME=PATH")
        name, path = value.split("=", 1)
        RetrievalEvaluator(
            args.qrels, qa_dataset_path=args.qa, split="dev", chunks_path=args.chunks,
        ).evaluate_run_file(path, retriever_name=name)
        for run in load_jsonl(path):
            for result in run.get("results", [])[:5]:
                chunk_id = result["chunk_id"]
                if not args.include_existing_gold and chunk_id in judged.get(run["query_id"], {}):
                    continue
                pool[run["query_id"]].setdefault(chunk_id, {})[name] = {
                    "rank": result["rank"], "score": result["score"],
                }
    if args.include_existing_gold:
        for query_id, judgments in judged.items():
            for chunk_id in judgments:
                pool[query_id].setdefault(chunk_id, {})["existing_gold"] = {
                    "rank": None, "score": None,
                }
    records = []
    for query_id in sorted(expected):
        for index, (chunk_id, systems) in enumerate(sorted(pool[query_id].items()), 1):
            records.append({
                "candidate_id": f"{query_id}_{'initial' if args.include_existing_gold else 'residual'}_{index:03d}", "query_id": query_id,
                "category": qa_by_id[query_id]["category"], "question": qa_by_id[query_id]["question"],
                "chunk_id": chunk_id, "candidate_text": chunks[chunk_id]["text"],
                "systems": systems, "original_relevance": None,
                "review_status": "pending", "reviewer": None, "relevance": None,
                "rationale": None, "second_reviewer_relevance": None,
            })
    output = Path(args.output_dir)
    if output.exists():
        raise FileExistsError("Residual pool may be created only once")
    output.mkdir(parents=True)
    with (output / "pool_internal.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            internal = {key: value for key, value in record.items() if key not in {"candidate_text", "question"}}
            handle.write(json.dumps(internal, ensure_ascii=False, sort_keys=True) + "\n")
    fields = (
        "candidate_id", "query_id", "category", "question", "chunk_id", "candidate_text",
        "review_status", "reviewer", "relevance", "rationale", "second_reviewer_relevance",
    )
    with (output / "pool_blind.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: record.get(key) for key in fields} for record in records)
    manifest = {
        "queries": len(expected), "pool_depth": 5, "new_unique_candidates": len(records),
        "pool_stage": "initial" if args.include_existing_gold else "residual",
        "status": "pending_blind_relevance_review",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
