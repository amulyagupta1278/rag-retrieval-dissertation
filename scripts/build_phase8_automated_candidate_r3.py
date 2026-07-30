#!/usr/bin/env python3
"""Build contract-clean Phase 8 benchmark candidate without human-review claims."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.benchmark_contract import validate_question
from src.benchmark.qa_generator import QAItem
from src.benchmark.qrels_builder import QRelsBuilder
from src.utils.io_utils import load_jsonl, save_jsonl


RELEASE = ROOT / "releases/v3_clean"
DEFAULT_OUTPUT = ROOT / "runs/phase8_exploratory_automated_r3/benchmark"
MARKERS = (
    "Detailed description", "Benefits", "Eligibility", "Application Process",
    "Documents Required", "Frequently asked questions",
)


def compact(text: str) -> str:
    return " ".join(text.split())


def overview_clause(text: str) -> str:
    """Extract source-verbatim prose while excluding structured metadata labels."""
    value = compact(text)
    if " Overview " in f" {value} ":
        value = value.split(" Overview ", 1)[1]
    for marker in MARKERS:
        if f" {marker} " in f" {value} ":
            value = value.split(f" {marker} ", 1)[0]
    # Keep contiguous source text. Sentence splitting corrupts abbreviations such
    # as M.Sc. and Ph.D., breaking exact-support audits.
    return value[:600].strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Refusing to overwrite candidate benchmark: {output}")
    output.mkdir(parents=True, exist_ok=True)

    qa_path = RELEASE / "data/queries/qa_dataset_v3_clean.jsonl"
    chunks_path = RELEASE / "data/chunks/chunks_v3_clean.jsonl"
    source_items = load_jsonl(qa_path)
    chunks = load_jsonl(chunks_path)
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    by_doc: dict[str, list[dict]] = {}
    for chunk in chunks:
        by_doc.setdefault(chunk["doc_id"], []).append(chunk)

    repaired: list[dict] = []
    change_log: list[dict] = []
    original_errors = 0
    for source in source_items:
        item = copy.deepcopy(source)
        errors = validate_question(item, chunk_map)
        original_errors += bool(errors)
        if errors:
            before = {
                "question": item["question"],
                "reference_answer": item["reference_answer"],
                "gold_evidence_ids": list(item["gold_evidence_ids"]),
            }
            if item["question_id"] == "q_0001":
                replacement = next(
                    chunk for chunk in by_doc[item["source_doc_ids"][0]]
                    if chunk["chunk_id"] == "chunk_703d79a4"
                )
                item["gold_evidence_ids"] = [replacement["chunk_id"]]
                item["source_doc_ids"] = [replacement["doc_id"]]
                text = compact(replacement["text"])
                match = re.search(
                    r"As you may be aware that the Govemment of India has launched ['’]Mission Shakti['’]\s*-\s*an integrated women empowerment programme[^.]*\.",
                    text,
                    re.I,
                )
                if not match:
                    raise RuntimeError("Mission Shakti source-verbatim definition not found")
                item["reference_answer"] = match.group(0)
            elif item["category"] in {"entity_relation", "multi_hop"}:
                item["reference_answer"] = " Additionally, ".join(
                    overview_clause(chunk_map[chunk_id]["text"])
                    for chunk_id in item["gold_evidence_ids"]
                )
            else:
                item["reference_answer"] = overview_clause(
                    chunk_map[item["gold_evidence_ids"][0]]["text"]
                )
            item["review_revision"] = int(item.get("review_revision", 0)) + 1
            item.setdefault("extra_meta", {})["automated_repair_reason"] = errors
            after_errors = validate_question(item, chunk_map)
            if after_errors:
                raise RuntimeError(f"Automated repair failed for {item['question_id']}: {after_errors}")
            change_log.append({
                "question_id": item["question_id"],
                "original_contract_errors": errors,
                "before": before,
                "after": {
                    "question": item["question"],
                    "reference_answer": item["reference_answer"],
                    "gold_evidence_ids": list(item["gold_evidence_ids"]),
                },
            })
        item["benchmark_version"] = "v3_clean_exploratory_automated_r3"
        item["review_status"] = "automated_candidate_pending_human_validation"
        repaired.append(item)

    remaining = [
        error
        for item in repaired
        for error in validate_question(item, chunk_map)
    ]
    if remaining:
        raise RuntimeError("Candidate still violates contract:\n" + "\n".join(remaining))
    if len(repaired) != 100 or len(change_log) != 32:
        raise RuntimeError(f"Unexpected repair cardinality: questions={len(repaired)} repairs={len(change_log)}")

    qa_out = output / "qa_dataset.jsonl"
    save_jsonl(repaired, qa_out)
    qrels = QRelsBuilder.build_qrels([QAItem.from_dict(item) for item in repaired])
    qrels_out = output / "qrels_gold.tsv"
    QRelsBuilder.save_qrels_tsv(qrels, qrels_out)
    categories = {
        item["question_id"]: {
            "category": item["category"], "difficulty": item["difficulty"], "split": item["split"]
        }
        for item in repaired
    }
    categories_out = output / "query_categories.json"
    categories_out.write_text(json.dumps(categories, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    changes_out = output / "automated_repair_log.jsonl"
    save_jsonl(change_log, changes_out)

    summary = {
        "status": "exploratory_automated_candidate_pending_human_validation",
        "human_review_complete": False,
        "owner_approved": False,
        "api_calls": 0,
        "source_questions": len(source_items),
        "source_contract_failures": original_errors,
        "questions_repaired": len(change_log),
        "remaining_contract_failures": len(remaining),
        "categories": dict(sorted(Counter(item["category"] for item in repaired).items())),
        "gold_judgments": len(qrels),
        "changed_gold_evidence": sum(
            row["before"]["gold_evidence_ids"] != row["after"]["gold_evidence_ids"]
            for row in change_log
        ),
        "inputs": {
            "qa_sha256": sha256(qa_path),
            "chunks_sha256": sha256(chunks_path),
        },
        "outputs": {
            "qa_sha256": sha256(qa_out),
            "qrels_sha256": sha256(qrels_out),
            "categories_sha256": sha256(categories_out),
            "repair_log_sha256": sha256(changes_out),
        },
    }
    (output / "candidate_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
