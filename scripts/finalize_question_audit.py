#!/usr/bin/env python3
"""Validate 100 primary reviews and stratified 20-question second review."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

REQUIRED_BOOLEANS = (
    "question_natural", "category_correct", "answer_supported", "gold_chunks_correct",
    "scheme_documents_correct", "bridge_valid", "two_chunk_necessity",
    "lexical_leakage_acceptable", "schema_leakage_absent", "boilerplate_absent",
)
EXPECTED = Counter({
    "exact_match": 20, "terminology_heavy": 20, "paraphrase": 20,
    "entity_relation": 20, "multi_hop": 20,
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


def _review_decision(review: dict) -> bool | None:
    values = [_boolean(review.get(field)) for field in REQUIRED_BOOLEANS]
    duplicate = _boolean(review.get("duplicate_intent"))
    if any(value is None for value in values) or duplicate is None:
        return None
    return all(values) and not duplicate


def _second_decision(value) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized in {"accept", "accepted", "true", "yes", "1"}:
        return True
    if normalized in {"reject", "rejected", "false", "no", "0"}:
        return False
    return None


def _cohen_kappa(pairs: list[tuple[bool, bool]]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_true = sum(left for left, _ in pairs) / len(pairs)
    right_true = sum(right for _, right in pairs) / len(pairs)
    expected = left_true * right_true + (1 - left_true) * (1 - right_true)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-questions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = _load(Path(args.reviewed_questions))
    categories = Counter(record.get("category") for record in records)
    errors = []
    if len(records) != 100 or categories != EXPECTED:
        errors.append(f"audit selection mismatch: rows={len(records)} categories={dict(categories)}")
    decisions: dict[str, bool] = {}
    second_pairs: list[tuple[bool, bool]] = []
    second_categories: Counter = Counter()
    rejected: list[str] = []
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
        duplicate = _boolean(review.get("duplicate_intent"))
        if duplicate is None:
            errors.append(f"missing duplicate_intent: {qid}")
        primary = _review_decision(review)
        if primary is not None:
            decisions[qid] = primary
            if not primary:
                rejected.append(qid)
                if not str(review.get("rationale") or "").strip():
                    errors.append(f"rejected question lacks rationale: {qid}")
        second_required = _boolean(record.get("second_review_required")) is True
        if second_required:
            second_categories[record.get("category")] += 1
            second = _second_decision(review.get("second_reviewer_decision"))
            if not str(review.get("second_reviewer") or "").strip() or second is None:
                errors.append(f"second review incomplete: {qid}")
            elif primary is not None:
                second_pairs.append((primary, second))
    expected_second = Counter({category: 4 for category in EXPECTED})
    if second_categories != expected_second:
        errors.append(f"second-review sample mismatch: {dict(second_categories)}")
    raw_agreement = (
        sum(left == right for left, right in second_pairs) / len(second_pairs)
        if second_pairs else 0.0
    )
    kappa = _cohen_kappa(second_pairs)
    if len(second_pairs) == 20 and (raw_agreement < 0.90 or kappa is None or kappa < 0.70):
        errors.append(
            f"inter-review threshold failed: agreement={raw_agreement:.3f} kappa={kappa}; "
            "double-review every item in affected categories"
        )
    if errors:
        raise RuntimeError("Question audit gate failed:\n- " + "\n- ".join(errors[:100]))
    report = {
        "audit_status": "complete_requires_replacement" if rejected else "complete",
        "questions_reviewed": 100,
        "categories": dict(sorted(categories.items())),
        "reviewers": sorted({
            str(record.get("human_review", record).get("reviewer")) for record in records
        }),
        "accepted_questions": 100 - len(rejected), "rejected_questions": rejected,
        "second_reviewed": len(second_pairs), "raw_agreement": raw_agreement,
        "cohen_kappa": kappa,
        "agreement_gate_passed": raw_agreement >= 0.90 and kappa is not None and kappa >= 0.70,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
