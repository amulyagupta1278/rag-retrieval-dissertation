#!/usr/bin/env python3
"""Validate and atomically publish 50 reviewed questions after configuration freeze."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.benchmark_contract import CATEGORIES, normalize, validate_question
from src.benchmark.qa_generator import QAItem
from src.benchmark.qrels_builder import QRelsBuilder
from src.evaluation.holdout_lock import verify_lock
from src.utils.artifact_provenance import sha256_file
from src.utils.io_utils import load_jsonl, save_jsonl


def _decision(value) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"accept", "accepted", "true", "yes", "1"}:
        return True
    if normalized in {"reject", "rejected", "false", "no", "0"}:
        return False
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--existing-qa", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--output-dir", default="releases/v3_clean_holdout_r1/benchmark")
    parser.add_argument("--benchmark-version", default="v3_clean_holdout_r1")
    args = parser.parse_args()
    lock = verify_lock(args.lock, ROOT)
    candidate = load_jsonl(args.candidate)
    existing = load_jsonl(args.existing_qa)
    chunks = load_jsonl(args.chunks)
    chunk_map = {chunk["chunk_id"]: chunk for chunk in chunks}
    counts = Counter(item.get("category") for item in candidate)
    errors: list[str] = []
    expected = Counter({category: 10 for category in CATEGORIES})
    if len(candidate) != 50 or counts != expected:
        errors.append(f"expected 50 balanced questions, got {len(candidate)} {dict(counts)}")
    existing_questions = {normalize(item["question"]) for item in existing}
    seen_questions: set[str] = set()
    gold_reuse: Counter = Counter()
    pairs: dict[str, set[tuple[str, str]]] = defaultdict(set)
    second_counts: Counter = Counter()
    for item in candidate:
        qid = item.get("question_id")
        key = normalize(item.get("question", ""))
        if not key or key in existing_questions or key in seen_questions:
            errors.append(f"reused/duplicate question: {qid}")
        seen_questions.add(key)
        if item.get("review_status") != "complete" or not item.get("reviewer"):
            errors.append(f"unreviewed holdout question: {qid}")
        if item.get("benchmark_version") != args.benchmark_version:
            errors.append(f"holdout version mismatch: {qid}")
        item["split"] = "holdout"
        item["fold_id"] = None
        errors.extend(validate_question(item, chunk_map))
        gold_reuse.update(item.get("gold_evidence_ids", []))
        if item.get("category") in {"entity_relation", "multi_hop"}:
            names = tuple(sorted(normalize(value) for value in item.get("extra_meta", {}).get("scheme_names", [])))
            if names in pairs[item["category"]]:
                errors.append(f"duplicate holdout scheme pair: {qid}")
            pairs[item["category"]].add(names)
        if item.get("second_review_required"):
            second_counts[item["category"]] += 1
            if not item.get("second_reviewer") or _decision(item.get("second_reviewer_decision")) is not True:
                errors.append(f"second review missing/rejected: {qid}")
    overused = {chunk_id: count for chunk_id, count in gold_reuse.items() if count > 2}
    if overused:
        errors.append(f"holdout gold reuse exceeds two: {overused}")
    if second_counts != Counter({category: 2 for category in CATEGORIES}):
        errors.append(f"second-review sample must contain two/category: {dict(second_counts)}")
    if errors:
        raise RuntimeError("Holdout publication failed:\n- " + "\n- ".join(errors[:200]))
    output = ROOT / args.output_dir
    if output.exists():
        raise FileExistsError("Holdout is immutable once published")
    output.mkdir(parents=True)
    qa_path = output / "qa_dataset.jsonl"
    save_jsonl(sorted(candidate, key=lambda item: item["question_id"]), qa_path)
    items = [QAItem.from_dict({key: value for key, value in item.items() if key in QAItem.__dataclass_fields__}) for item in candidate]
    qrels_path = output / "qrels_gold.tsv"
    QRelsBuilder.save_qrels_tsv(QRelsBuilder.build_qrels(items), qrels_path)
    QRelsBuilder.save_evidence_map(items, output / "evidence_map.json")
    categories = {
        item["question_id"]: {"category": item["category"], "difficulty": item["difficulty"], "split": "holdout"}
        for item in sorted(candidate, key=lambda value: value["question_id"])
    }
    (output / "query_categories.json").write_text(json.dumps(categories, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {
        "configuration_lock_id": lock["lock_id"], "benchmark_version": args.benchmark_version,
        "questions": 50, "categories": dict(sorted(counts.items())),
        "gold_judgments": sum(len(item.gold_evidence_ids) for item in items),
        "chunks_sha256": sha256_file(args.chunks), "qa_sha256": sha256_file(qa_path),
        "qrels_sha256": sha256_file(qrels_path), "second_reviewed": 10,
        "status": "blind_holdout_published",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
