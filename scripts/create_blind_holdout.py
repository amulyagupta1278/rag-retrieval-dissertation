#!/usr/bin/env python3
"""Validate and publish 25 manually reviewed questions after configuration freeze."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.evaluation.holdout_lock import verify_lock
from src.utils.io_utils import load_jsonl, save_jsonl

CATEGORIES = {"exact_match", "terminology_heavy", "paraphrase", "entity_relation", "multi_hop"}


def _normalise(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--existing-qa", required=True)
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--output", default="data/queries/holdout_qa.jsonl")
    args = parser.parse_args()
    lock = verify_lock(args.lock, ROOT)
    candidate = load_jsonl(args.candidate)
    existing = load_jsonl(args.existing_qa)
    chunks = {chunk["chunk_id"]: chunk for chunk in load_jsonl(args.chunks)}
    counts = Counter(item.get("category") for item in candidate)
    errors = []
    if len(candidate) != 25 or counts != Counter({category: 5 for category in CATEGORIES}):
        errors.append(f"expected 25 balanced questions, got {len(candidate)} {dict(counts)}")
    existing_questions = {_normalise(item["question"]) for item in existing}
    seen = set()
    for item in candidate:
        key = _normalise(item.get("question", ""))
        if not key or key in existing_questions or key in seen:
            errors.append(f"reused/duplicate question: {item.get('question_id')}")
        seen.add(key)
        if item.get("review_status") != "complete" or not item.get("reviewer"):
            errors.append(f"unreviewed holdout question: {item.get('question_id')}")
        gold = item.get("gold_evidence_ids", [])
        if any(chunk_id not in chunks for chunk_id in gold):
            errors.append(f"unknown gold evidence: {item.get('question_id')}")
        if item.get("category") in {"entity_relation", "multi_hop"}:
            docs = [chunks.get(chunk_id, {}).get("doc_id") for chunk_id in gold]
            schemes = [chunks.get(chunk_id, {}).get("scheme_name") for chunk_id in gold]
            if len(gold) != 2 or len(set(docs)) != 2 or len({_normalise(value or "") for value in schemes}) != 2:
                errors.append(f"cross-scheme holdout invariant failed: {item.get('question_id')}")
        item["split"] = "holdout"
    if errors:
        raise RuntimeError("Holdout publication failed:\n- " + "\n- ".join(errors))
    destination = ROOT / args.output
    if destination.exists():
        raise FileExistsError("Holdout is immutable once published")
    save_jsonl(sorted(candidate, key=lambda item: item["question_id"]), destination)
    report = {
        "configuration_lock_id": lock["lock_id"], "questions": 25,
        "categories": dict(sorted(counts.items())), "status": "blind_holdout_published",
    }
    destination.with_suffix(".manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
