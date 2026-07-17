#!/usr/bin/env python3
"""Prepare the fixed 60-question audit and top-3 pooled judgment workbook."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.utils.io_utils import load_jsonl


AUDIT_COUNTS = {
    "entity_relation": 20, "multi_hop": 20, "paraphrase": 10,
    "exact_match": 5, "terminology_heavy": 5,
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
            "query_id", "category", "question", "chunk_id", "systems", "original_relevance",
            "candidate_text", "review_status", "reviewer", "relevance", "rationale",
            "second_reviewer_relevance",
        ]
    else:
        fields = [
            "question_id", "category", "question", "reference_answer", "gold_chunk_ids",
            "source_doc_ids", "scheme_names", "bridge_entity", "evidence_snippets",
            "automatic_checks", "status", "reviewer", "question_natural", "category_correct",
            "answer_supported", "gold_chunks_correct", "scheme_documents_correct", "bridge_valid",
            "two_chunk_necessity", "lexical_leakage_acceptable", "duplicate_intent", "rationale",
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
        audit_records.append({
            "question_id": item["question_id"], "category": item["category"],
            "question": item["question"], "reference_answer": item.get("reference_answer", ""),
            "gold_chunk_ids": gold, "source_doc_ids": source_docs,
            "scheme_names": item.get("extra_meta", {}).get("scheme_names", []),
            "bridge_entity": item.get("extra_meta", {}).get("bridge_entity"),
            "evidence_snippets": [text[:500] for text in evidence],
            "automatic_checks": automatic,
            "human_review": {
                "status": "pending", "reviewer": None,
                "question_natural": None, "category_correct": None,
                "answer_supported": None, "gold_chunks_correct": None,
                "scheme_documents_correct": None, "bridge_valid": None,
                "two_chunk_necessity": None, "lexical_leakage_acceptable": None,
                "duplicate_intent": None, "rationale": None,
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
            for result in run.get("results", [])[:3]:
                run_pools[run["query_id"]].setdefault(result["chunk_id"], {})[system] = {
                    "rank": result.get("rank"), "score": result.get("score"),
                }
    pooled: list[dict] = []
    for item in selected:
        query_id = item["question_id"]
        for chunk_id, systems in sorted(run_pools[query_id].items()):
            original = qrels.get(query_id, {}).get(chunk_id)
            pooled.append({
                "query_id": query_id, "category": item["category"], "question": item["question"],
                "chunk_id": chunk_id, "systems": systems,
                "original_relevance": original,
                "candidate_text": chunks.get(chunk_id, {}).get("text", "")[:700],
                "review_status": "pending", "reviewer": None, "relevance": None,
                "rationale": None, "second_reviewer_relevance": None,
            })

    output = Path(args.output_dir)
    _write_jsonl(audit_records, output / "question_audit_60.jsonl")
    _write_jsonl(pooled, output / "pooled_top3_judgments.jsonl")
    _write_review_csv(audit_records, output / "question_audit_60.csv")
    _write_review_csv(pooled, output / "pooled_top3_judgments.csv", pooled=True)
    summary = {
        "audit_status": "pending_human_review", "questions": len(audit_records),
        "selection": AUDIT_COUNTS, "pooled_candidates": len(pooled),
        "automatic_failures": {
            key: sum(not record["automatic_checks"][key] for record in audit_records)
            for key in next(iter(audit_records))["automatic_checks"]
        },
    }
    (output / "audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "REVIEW_INSTRUCTIONS.md").write_text(
        "# Benchmark Audit Instructions\n\n"
        "The audit remains blocked until a reviewer completes all 60 question rows and all pooled "
        "judgment rows. Do not change question IDs or chunk IDs.\n\n"
        "For `question_audit_60.csv`, set `status=complete`, record the reviewer, complete every "
        "boolean review field, and explain every rejection or correction in `rationale`.\n\n"
        "For `pooled_top3_judgments.csv`, set `review_status=complete`, reviewer, and relevance "
        "(`0`, `1`, or `2`) for every candidate. Explain any judgment that differs from "
        "`original_relevance`. Convert the reviewed sheet back to JSONL before running "
        "`scripts/finalize_qrels_audit.py`.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
