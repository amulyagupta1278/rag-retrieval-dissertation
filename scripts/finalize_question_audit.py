#!/usr/bin/env python3
"""Validate a completed 60-question audit and emit the P1 gate record."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REQUIRED_BOOLEANS = (
    "question_natural", "category_correct", "answer_supported", "gold_chunks_correct",
    "scheme_documents_correct", "bridge_valid", "two_chunk_necessity",
    "lexical_leakage_acceptable",
)
EXPECTED = Counter({
    "entity_relation": 20, "multi_hop": 20, "paraphrase": 10,
    "exact_match": 5, "terminology_heavy": 5,
})


def _boolean(value) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"true", "yes", "1"}:
        return True
    if normalized in {"false", "no", "0"}:
        return False
    return None


def _load(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-questions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = _load(Path(args.reviewed_questions))
    categories = Counter(record.get("category") for record in records)
    errors = []
    if len(records) != 60 or categories != EXPECTED:
        errors.append(f"audit selection mismatch: rows={len(records)} categories={dict(categories)}")
    for record in records:
        review = record.get("human_review", record)
        qid = record.get("question_id")
        if review.get("status") != "complete" or not str(review.get("reviewer") or "").strip():
            errors.append(f"incomplete reviewer record: {qid}")
            continue
        for field in REQUIRED_BOOLEANS:
            value = _boolean(review.get(field))
            if value is None:
                errors.append(f"missing {field}: {qid}")
            elif not value:
                errors.append(f"benchmark validity failed {field}: {qid}")
        duplicate = _boolean(review.get("duplicate_intent"))
        if duplicate is None:
            errors.append(f"missing duplicate_intent: {qid}")
        elif duplicate:
            errors.append(f"duplicate intent requires correction: {qid}")
    if errors:
        raise RuntimeError("Question audit gate failed:\n- " + "\n- ".join(errors[:100]))
    report = {
        "audit_status": "complete", "questions_reviewed": 60,
        "categories": dict(sorted(categories.items())),
        "reviewers": sorted({
            str(record.get("human_review", record).get("reviewer")) for record in records
        }),
        "all_validity_checks_passed": True,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
