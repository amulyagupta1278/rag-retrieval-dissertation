#!/usr/bin/env python3
"""Validate graph entity and seed-trace human audit before configuration freeze."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: str) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _true(value) -> bool:
    return value is True or str(value).strip().lower() in {"true", "yes", "1"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entities", required=True)
    parser.add_argument("--seed-traces", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    entities_payload = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    traces = _load(args.seed_traces)
    errors = []
    if len(entities_payload) != 100:
        errors.append(f"expected 100 entity rows, got {len(entities_payload)}")
    if len(traces) != 30:
        errors.append(f"expected 30 seed traces, got {len(traces)}")
    valid_entities = 0
    for record in entities_payload:
        if record.get("review_status") != "complete" or not record.get("reviewer"):
            errors.append(f"entity review incomplete: {record.get('entity')}")
            continue
        if _true(record.get("valid_entity")) and _true(record.get("schema_leakage_absent")):
            valid_entities += 1
        elif not str(record.get("rationale") or "").strip():
            errors.append(f"invalid entity lacks rationale: {record.get('entity')}")
    valid_traces = 0
    for record in traces:
        review = record.get("human_review", {})
        if review.get("review_status") != "complete" or not review.get("reviewer"):
            errors.append(f"seed trace review incomplete: {record.get('query_id')}")
            continue
        passed = all(_true(review.get(field)) for field in (
            "accepted_seeds_correct", "rejected_seeds_correct", "ranking_path_plausible",
        ))
        if passed:
            valid_traces += 1
        elif not str(review.get("rationale") or "").strip():
            errors.append(f"failed seed trace lacks rationale: {record.get('query_id')}")
    if errors:
        raise RuntimeError("Graph audit failed:\n- " + "\n- ".join(errors[:200]))
    report = {
        "graph_audit_status": "complete", "entities_reviewed": 100,
        "valid_entities": valid_entities, "seed_traces_reviewed": 30,
        "valid_seed_traces": valid_traces,
        "selection_gate_passed": valid_entities == 100 and valid_traces == 30,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
