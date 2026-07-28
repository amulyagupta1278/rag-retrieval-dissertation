#!/usr/bin/env python3
"""Prepare full benchmark audit and blind top-k pooled judgment workbook."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.benchmark.benchmark_contract import validate_question
from src.utils.io_utils import load_jsonl


AUDIT_COUNTS = {
    "exact_match": 20, "terminology_heavy": 20, "paraphrase": 20,
    "entity_relation": 20, "multi_hop": 20,
}


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _write_review_csv(records: list[dict], path: Path, *, pooled: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if pooled:
        fields = [
            "candidate_id", "query_id", "category", "question", "chunk_id",
            "candidate_text", "review_status", "reviewer", "relevance", "rationale",
            "second_reviewer_relevance",
        ]
    else:
        fields = [
            "question_id", "category", "question", "reference_answer", "gold_chunk_ids",
            "source_doc_ids", "scheme_names", "bridge_entity", "evidence_snippets",
            "automatic_checks", "second_review_required", "status", "reviewer", "question_natural", "category_correct",
            "answer_supported", "gold_chunks_correct", "scheme_documents_correct", "bridge_valid",
            "two_chunk_necessity", "lexical_leakage_acceptable", "schema_leakage_absent",
            "boilerplate_absent", "duplicate_intent", "rationale", "second_reviewer",
            "second_reviewer_decision", "second_reviewer_rationale",
        ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in records:
            if pooled:
                row = dict(record)
            else:
                row = {key: value for key, value in record.items() if key != "human_review"}
                row.update(record["human_review"])
            writer.writerow({
                field: json.dumps(row.get(field), ensure_ascii=False)
                if isinstance(row.get(field), (dict, list)) else row.get(field)
                for field in fields
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True)
    parser.add_argument("--qrels", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--run", action="append", required=True, help="NAME=run.jsonl")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--pool-depth", type=int, default=5)
    parser.add_argument("--benchmark-version", default="v3_clean_benchmark_r1")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    qa = load_jsonl(args.qa)
    chunks = {chunk["chunk_id"]: chunk for chunk in load_jsonl(args.chunks)}
    qrels = QRelsBuilder.load_qrels_tsv(args.qrels)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for item in sorted(qa, key=lambda value: value["question_id"]):
        by_category[item["category"]].append(item)
    selected: list[dict] = []
    for category, count in AUDIT_COUNTS.items():
        if len(by_category[category]) < count:
            raise RuntimeError(f"Insufficient {category} questions for audit")
        selected.extend(by_category[category][:count])
    selected.sort(key=lambda value: value["question_id"])
    # Existing 100 questions are exploratory development data. Assign balanced
    # folds before review; replacements inherit rejected item's fold.
    rng = random.Random(args.seed)
    for category in sorted(by_category):
        values = sorted(by_category[category], key=lambda value: value["question_id"])
        rng.shuffle(values)
        for index, item in enumerate(values):
            item["parent_question_id"] = item["question_id"]
            item["benchmark_version"] = args.benchmark_version
            item["review_status"] = "pending"
            item["review_revision"] = 0
            item["split"] = "dev"
            item["fold_id"] = index % 5
    second_review_ids: set[str] = set()
    sample_rng = random.Random(args.seed + 1)
    for category in sorted(by_category):
        values = sorted(by_category[category], key=lambda value: value["question_id"])
        second_review_ids.update(item["question_id"] for item in sample_rng.sample(values, 4))

    question_keys = defaultdict(list)
    for item in qa:
        question_keys[_normalized(item["question"])].append(item["question_id"])
    audit_records: list[dict] = []
    for item in selected:
        gold = item.get("gold_evidence_ids", [])
        source_docs = item.get("source_doc_ids", [])
        evidence = [chunks.get(chunk_id, {}).get("text", "") for chunk_id in gold]
        answer_clauses = item.get("reference_answer", "").split(" Additionally, ")
        if len(answer_clauses) == len(evidence):
            answer_supported = all(
                _normalized(clause) in _normalized(text)
                for clause, text in zip(answer_clauses, evidence)
            )
        else:
            answer_supported = any(
                _normalized(item.get("reference_answer", "")) in _normalized(text)
                for text in evidence
            )
        automatic = {
            "gold_ids_resolve": len(evidence) == len(gold) and all(evidence),
            "source_document_ids_resolve": len(gold) == len(source_docs) and all(
                chunks.get(chunk_id, {}).get("doc_id") == doc_id
                for chunk_id, doc_id in zip(gold, source_docs)
            ),
            "answer_exactly_supported": answer_supported,
            "two_chunks_for_cross_scheme": item["category"] not in {"entity_relation", "multi_hop"} or len(gold) == 2,
            "question_intent_unique": len(question_keys[_normalized(item["question"])]) == 1,
        }
        contract_errors = validate_question(item, chunks)
        automatic["category_contract_passes"] = not contract_errors
        audit_records.append({
            "question_id": item["question_id"], "category": item["category"],
            "question": item["question"], "reference_answer": item.get("reference_answer", ""),
            "gold_chunk_ids": gold, "source_doc_ids": source_docs,
            "scheme_names": item.get("extra_meta", {}).get("scheme_names", []),
            "bridge_entity": item.get("extra_meta", {}).get("bridge_entity"),
            "evidence_snippets": [text[:500] for text in evidence],
            "automatic_checks": automatic,
            "contract_errors": contract_errors,
            "second_review_required": item["question_id"] in second_review_ids,
            "human_review": {
                "status": "pending", "reviewer": None,
                "question_natural": None, "category_correct": None,
                "answer_supported": None, "gold_chunks_correct": None,
                "scheme_documents_correct": None, "bridge_valid": None,
                "two_chunk_necessity": None, "lexical_leakage_acceptable": None,
                "schema_leakage_absent": None, "boilerplate_absent": None,
                "duplicate_intent": None, "rationale": None,
                "second_reviewer": None, "second_reviewer_decision": None,
                "second_reviewer_rationale": None,
            },
        })

    run_pools: dict[str, dict[str, dict]] = defaultdict(dict)
    for value in args.run:
        if "=" not in value:
            raise ValueError("--run must use NAME=PATH")
        system, path = value.split("=", 1)
        for run in load_jsonl(path):
            if run["query_id"] not in {item["question_id"] for item in selected}:
                continue
            for result in run.get("results", [])[: args.pool_depth]:
                run_pools[run["query_id"]].setdefault(result["chunk_id"], {})[system] = {
                    "rank": result.get("rank"), "score": result.get("score"),
                }
    pooled: list[dict] = []
    for item in selected:
        query_id = item["question_id"]
        for chunk_id in sorted(qrels.get(query_id, {})):
            run_pools[query_id].setdefault(chunk_id, {})["existing_gold"] = {
                "rank": None, "score": None,
            }
        for candidate_index, (chunk_id, systems) in enumerate(sorted(run_pools[query_id].items()), 1):
            original = qrels.get(query_id, {}).get(chunk_id)
            pooled.append({
                "candidate_id": f"{query_id}_candidate_{candidate_index:03d}",
                "query_id": query_id, "category": item["category"], "question": item["question"],
                "chunk_id": chunk_id, "systems": systems,
                "original_relevance": original,
                "candidate_text": chunks.get(chunk_id, {}).get("text", ""),
                "review_status": "pending", "reviewer": None, "relevance": None,
                "rationale": None, "second_reviewer_relevance": None,
            })

    output = Path(args.output_dir)
    _write_jsonl(selected, output / "benchmark_draft_r1.jsonl")
    _write_jsonl(audit_records, output / "question_audit_100.jsonl")
    _write_jsonl([
        {key: value for key, value in record.items() if key not in {"candidate_text", "question"}}
        for record in pooled
    ], output / "pooled_top5_internal.jsonl")
    _write_review_csv(audit_records, output / "question_audit_100.csv")
    _write_review_csv(pooled, output / "pooled_top5_blind.csv", pooled=True)
    summary = {
        "audit_status": "pending_human_review", "benchmark_version": args.benchmark_version,
        "questions": len(audit_records),
        "selection": AUDIT_COUNTS, "pooled_candidates": len(pooled),
        "pool_depth": args.pool_depth, "second_review_questions": len(second_review_ids),
        "pool_status": "diagnostic_only_until_rejected_questions_are_replaced",
        "automatic_failures": {
            key: sum(not record["automatic_checks"][key] for record in audit_records)
            for key in next(iter(audit_records))["automatic_checks"]
        },
    }
    (output / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "REVIEW_INSTRUCTIONS.md").write_text(
        "# Benchmark Audit Instructions\n\n"
        "Audit remains blocked until primary reviewer completes all 100 question rows and all pooled "
        "judgment rows. Do not change question IDs or chunk IDs.\n\n"
        "For `question_audit_100.csv`, set `status=complete`, record reviewer, complete every "
        "boolean field, and explain every rejection in `rationale`. Replace rejected questions "
        "before publication; do not mark invalid questions complete. Second reviewer completes "
        "20 rows marked `second_review_required`.\n\n"
        "For `pooled_top5_blind.csv`, assign binary relevance (`0` or `1`). System names and ranks "
        "are intentionally absent. Explain judgment changes from original relevance. Run "
        "`scripts/finalize_qrels_audit.py`.\n",
        encoding="utf-8",
    )
    packet_files = sorted(
        path for path in output.iterdir()
        if path.is_file() and path.name != "AUDIT_SHA256SUMS"
    )
    (output / "AUDIT_SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in packet_files
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
