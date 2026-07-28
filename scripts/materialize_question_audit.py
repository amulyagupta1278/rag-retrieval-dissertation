#!/usr/bin/env python3
"""Apply reviewed decisions to benchmark draft and prepare/merge replacements."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.io_utils import load_jsonl, save_jsonl

BOOLEAN_FIELDS = (
    "question_natural", "category_correct", "answer_supported", "gold_chunks_correct",
    "scheme_documents_correct", "bridge_valid", "two_chunk_necessity",
    "lexical_leakage_acceptable", "schema_leakage_absent", "boilerplate_absent",
)


def _bool(value) -> bool:
    return value is True or str(value or "").strip().lower() in {"true", "yes", "1"}


def _accepted(row: dict) -> bool:
    return all(_bool(row.get(field)) for field in BOOLEAN_FIELDS) and not _bool(row.get("duplicate_intent"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--reviewed-audit", required=True)
    parser.add_argument("--audit-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--replacements", default=None)
    args = parser.parse_args()
    audit_summary = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    if not audit_summary.get("agreement_gate_passed"):
        raise RuntimeError("Cannot materialize benchmark before audit agreement gate passes")
    draft = {item["question_id"]: item for item in load_jsonl(args.draft)}
    with Path(args.reviewed_audit).open(encoding="utf-8", newline="") as handle:
        reviewed = {row["question_id"]: row for row in csv.DictReader(handle)}
    if set(draft) != set(reviewed) or len(draft) != 100:
        raise RuntimeError("Reviewed audit IDs do not exactly match 100-question draft")
    accepted, templates = [], []
    for question_id in sorted(draft):
        item, row = draft[question_id], reviewed[question_id]
        if _accepted(row):
            item["review_status"] = "complete"
            item["review_revision"] = 1
            accepted.append(item)
            continue
        template = {
            **item,
            "question": "", "reference_answer": "", "gold_evidence_ids": [],
            "source_doc_ids": [], "review_status": "pending_replacement_review",
            "review_revision": 2,
            "extra_meta": {
                "replacement_reason": row.get("rationale") or "",
                "scheme_names": [], "bridge_entity": None,
            },
        }
        templates.append(template)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    save_jsonl(accepted, output / "accepted_questions.jsonl")
    save_jsonl(templates, output / "replacement_template.jsonl")
    status = {
        "accepted": len(accepted), "replacements_required": len(templates),
        "status": "pending_replacements" if templates and not args.replacements else "ready_to_merge",
    }
    if args.replacements:
        replacements = {item["question_id"]: item for item in load_jsonl(args.replacements)}
        expected = {item["question_id"] for item in templates}
        if set(replacements) != expected:
            raise RuntimeError("Replacement IDs must exactly match rejected question IDs")
        for template in templates:
            replacement = replacements[template["question_id"]]
            if replacement.get("category") != template["category"] or replacement.get("fold_id") != template["fold_id"]:
                raise RuntimeError(f"Replacement category/fold changed: {template['question_id']}")
            if replacement.get("review_status") != "complete" or int(replacement.get("review_revision", 0)) < 2:
                raise RuntimeError(f"Replacement review incomplete: {template['question_id']}")
            if not replacement.get("extra_meta", {}).get("replacement_reason"):
                raise RuntimeError(f"Replacement rationale missing: {template['question_id']}")
        final = sorted(accepted + list(replacements.values()), key=lambda item: item["question_id"])
        save_jsonl(final, output / "qa_reviewed_final.jsonl")
        status["status"] = "reviewed_questions_merged"
        status["final_questions"] = len(final)
    (output / "materialization_status.json").write_text(
        json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
