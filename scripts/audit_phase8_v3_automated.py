#!/usr/bin/env python3
"""Audit frozen v3_clean expansion without creating human-validation claims."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE = ROOT / "releases/v3_clean"
DEFAULT_OUTPUT = ROOT / "audits/phase8_exploratory/automated_audit.json"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def normalized(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def duplicate_count(values: list[str]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    release = args.release.resolve()
    documents = load_jsonl(release / "data/processed/documents.jsonl")
    chunks = load_jsonl(release / "data/chunks/chunks_v3_clean.jsonl")
    questions = load_jsonl(release / "data/queries/qa_dataset_v3_clean.jsonl")
    sources = load_jsonl(release / "data/sources/source_catalog_v2.jsonl")
    benchmark_audit = json.loads(
        (ROOT / "audits/v3_clean_benchmark_r1/audit_summary.json").read_text(encoding="utf-8")
    )

    qrels: list[tuple[str, str, int]] = []
    with (release / "data/qrels/qrels_v3_clean.tsv").open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            qrels.append((row[0], row[2], int(row[3])))

    doc_ids = [row["doc_id"] for row in documents]
    chunk_ids = [row["chunk_id"] for row in chunks]
    question_ids = [row["question_id"] for row in questions]
    doc_set, chunk_set, question_set = set(doc_ids), set(chunk_ids), set(question_ids)
    gold_pairs = {
        (question["question_id"], chunk_id)
        for question in questions
        for chunk_id in question["gold_evidence_ids"]
    }
    qrel_pairs = {(query_id, chunk_id) for query_id, chunk_id, _ in qrels}

    exact_support_failures = 0
    chunk_by_id = {row["chunk_id"]: normalized(row["text"]) for row in chunks}
    flagged_questions: list[dict[str, object]] = []
    for question in questions:
        answer = normalized(question["reference_answer"])
        evidence = " ".join(chunk_by_id.get(chunk_id, "") for chunk_id in question["gold_evidence_ids"])
        if answer not in evidence:
            exact_support_failures += 1
        reasons: list[str] = []
        years = sorted({int(year) for year in re.findall(r"\b20\d{2}\b", question["question"] + " " + question["reference_answer"])})
        if any(year >= 2025 for year in years):
            reasons.append("time_sensitive_year_2025_or_later")
        answer_words = answer.split()
        if len(answer_words) < 5:
            reasons.append("reference_answer_under_5_words")
        if len(answer_words) > 120:
            reasons.append("reference_answer_over_120_words")
        if reasons:
            flagged_questions.append(
                {"question_id": question["question_id"], "reasons": reasons, "years": years}
            )

    metric_rows = list(csv.DictReader((release / "runs/metrics/metrics.csv").open(encoding="utf-8")))
    all_metrics = {
        row["retriever"]: {
            "mrr_at_10": float(row["mrr@10"]),
            "recall_at_10": float(row["recall@10"]),
            "ndcg_at_10": float(row["ndcg@10"]),
            "precision_at_10": float(row["precision@10"]),
        }
        for row in metric_rows
        if row["query_category"] == "all"
    }

    source_hosts = Counter(urlparse(row["url"]).hostname or "missing" for row in sources)
    missing_doc_references = sum(row["doc_id"] not in doc_set for row in chunks)
    missing_gold_chunks = sum(chunk_id not in chunk_set for _, chunk_id in gold_pairs)
    missing_source_docs = sum(
        doc_id not in doc_set for row in questions for doc_id in row["source_doc_ids"]
    )
    invalid_qrels = sum(query_id not in question_set or chunk_id not in chunk_set for query_id, chunk_id, _ in qrels)

    report = {
        "schema_version": 1,
        "status": "exploratory_automated_only_pending_human_validation",
        "claim_scope": {
            "final_dissertation_evidence": False,
            "owner_approved": False,
            "human_benchmark_review_complete": False,
            "automated_expansion_verified": True,
            "api_calls_performed": 0,
        },
        "release": {
            "path": str(release.relative_to(ROOT)),
            "manifest_sha256": sha256(release / "manifests/release_manifest.jsonl"),
            "documents": len(documents),
            "chunks": len(chunks),
            "questions": len(questions),
            "qrels": len(qrels),
            "source_catalog_entries": len(sources),
        },
        "integrity": {
            "unique_document_ids": len(doc_set),
            "unique_chunk_ids": len(chunk_set),
            "unique_question_ids": len(question_set),
            "duplicate_document_ids": duplicate_count(doc_ids),
            "duplicate_chunk_ids": duplicate_count(chunk_ids),
            "duplicate_question_ids": duplicate_count(question_ids),
            "duplicate_normalized_chunk_texts": duplicate_count([normalized(row["text"]) for row in chunks]),
            "duplicate_normalized_questions": duplicate_count([normalized(row["question"]) for row in questions]),
            "chunks_with_missing_document": missing_doc_references,
            "missing_gold_chunks": missing_gold_chunks,
            "missing_source_documents": missing_source_docs,
            "invalid_qrel_references": invalid_qrels,
            "gold_pairs_missing_from_qrels": len(gold_pairs - qrel_pairs),
            "qrel_pairs_not_declared_as_gold": len(qrel_pairs - gold_pairs),
            "empty_chunks": sum(not row["text"].strip() for row in chunks),
            "chunks_under_50_words": sum(int(row.get("word_count", 0)) < 50 for row in chunks),
            "reference_answers_not_exact_substrings_of_gold_evidence": exact_support_failures,
        },
        "coverage": {
            "question_categories": dict(sorted(Counter(row["category"] for row in questions).items())),
            "question_splits": dict(sorted(Counter(row["split"] for row in questions).items())),
            "qrel_grades": {str(key): value for key, value in sorted(Counter(grade for _, _, grade in qrels).items())},
            "source_hosts": dict(sorted(source_hosts.items())),
            "documents_without_publication_date": sum(not row.get("publication_date") for row in documents),
        },
        "benchmark_validity": {
            "upstream_audit_status": benchmark_audit["audit_status"],
            "pool_status": benchmark_audit["pool_status"],
            "automatic_failures": benchmark_audit["automatic_failures"],
            "flagged_question_count": len(flagged_questions),
            "flagged_questions": flagged_questions,
        },
        "exploratory_three_system_metrics": all_metrics,
        "limitations": [
            "Questions and qrels are generated artifacts without completed human review.",
            "Existing audit reports 32 category-contract failures.",
            "Only BM25, FAISS, and entity-co-occurrence graph retrieval are present; pilot five-system comparison was not rerun.",
            "Metrics are diagnostic and cannot replace frozen Phase 1-7 pilot findings.",
            "No Phase 7 answer generation or H5 analysis was run on expanded corpus.",
        ],
    }

    hard_integrity_failures = sum(
        report["integrity"][key]
        for key in (
            "duplicate_document_ids", "duplicate_chunk_ids", "duplicate_question_ids",
            "chunks_with_missing_document", "missing_gold_chunks", "missing_source_documents",
            "invalid_qrel_references", "gold_pairs_missing_from_qrels",
        )
    )
    report["hard_integrity_failures"] = hard_integrity_failures
    report["automated_integrity_result"] = "pass" if hard_integrity_failures == 0 else "fail"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "status": report["status"],
        "hard_integrity_failures": hard_integrity_failures,
        "flagged_questions": len(flagged_questions),
    }, indent=2))
    return 0 if hard_integrity_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
