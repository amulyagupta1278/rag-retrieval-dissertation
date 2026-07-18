#!/usr/bin/env python3
"""Publish audited pooled judgments only after every record is reviewed."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.qrels_builder import QRelsBuilder
from src.utils.io_utils import load_jsonl


def _load_reviewed(path: str) -> list[dict]:
    source = Path(path)
    if source.suffix.lower() != ".csv":
        return load_jsonl(source)
    records = []
    with source.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            record = dict(row)
            for key in ("original_relevance", "relevance", "second_reviewer_relevance"):
                value = str(record.get(key) or "").strip()
                record[key] = int(value) if value in {"0", "1"} else None
            if record.get("systems"):
                record["systems"] = json.loads(record["systems"])
            records.append(record)
    return records


def _cohen_kappa(pairs: list[tuple[int, int]]) -> float | None:
    if not pairs:
        return None
    labels = sorted({value for pair in pairs for value in pair})
    observed = sum(left == right for left, right in pairs) / len(pairs)
    expected = sum(
        (sum(left == label for left, _ in pairs) / len(pairs))
        * (sum(right == label for _, right in pairs) / len(pairs))
        for label in labels
    )
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-qrels", required=True)
    parser.add_argument("--reviewed-pool", required=True)
    parser.add_argument("--pool-provenance", default=None, help="Internal pool JSONL containing hidden system/rank provenance")
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--pool-stage", choices=("initial", "residual", "holdout"), default="initial")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    records = _load_reviewed(args.reviewed_pool)
    if args.pool_provenance:
        provenance = {
            record["candidate_id"]: record for record in load_jsonl(args.pool_provenance)
        }
        if {record.get("candidate_id") for record in records} != set(provenance):
            raise RuntimeError("Reviewed blind pool does not match internal pool provenance")
        records = [
            {**provenance[record["candidate_id"]], **record}
            for record in records
        ]
    incomplete = [
        record for record in records
        if record.get("review_status") != "complete"
        or record.get("reviewer") in (None, "")
        or record.get("relevance") not in (0, 1)
    ]
    if incomplete:
        raise RuntimeError(f"Cannot publish audited qrels: {len(incomplete)} pooled judgments incomplete")
    qrels = QRelsBuilder.load_qrels_tsv(args.original_qrels)
    known_chunks = {chunk["chunk_id"] for chunk in load_jsonl(args.chunks)}
    additions: list[dict] = []
    second_pairs: list[tuple[int, int]] = []
    for record in records:
        query_id, chunk_id, relevance = record["query_id"], record["chunk_id"], int(record["relevance"])
        original = qrels.setdefault(query_id, {}).get(chunk_id)
        qrels[query_id][chunk_id] = relevance
        if original != relevance:
            if not str(record.get("rationale") or "").strip():
                raise RuntimeError(f"Changed judgment lacks rationale: {query_id}/{chunk_id}")
            additions.append({**record, "previous_relevance": original})
        if record.get("second_reviewer_relevance") in (0, 1):
            second_pairs.append((relevance, int(record["second_reviewer_relevance"])))
    unknown = {
        chunk_id for judgments in qrels.values() for chunk_id in judgments
        if chunk_id not in known_chunks
    }
    if unknown:
        raise RuntimeError(f"Audited qrels reference unknown chunks: {sorted(unknown)[:20]}")
    no_relevant = [
        query_id for query_id, judgments in qrels.items()
        if not any(relevance == 1 for relevance in judgments.values())
    ]
    if no_relevant:
        raise RuntimeError(f"Audited qrels leave queries without relevant evidence: {no_relevant[:20]}")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    triples = [
        (query_id, chunk_id, relevance)
        for query_id, judgments in sorted(qrels.items())
        for chunk_id, relevance in sorted(judgments.items())
    ]
    audited_path = output / "qrels_audited.tsv"
    QRelsBuilder.save_qrels_tsv(triples, audited_path)
    with (output / "judgment_changes.jsonl").open("w", encoding="utf-8") as handle:
        for record in additions:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    consistency = {
        "primary_judgments": len(records), "changed_judgments": len(additions),
        "double_reviewed": len(second_pairs), "cohen_kappa": _cohen_kappa(second_pairs),
    }
    (output / "inter_reviewer_consistency.json").write_text(
        json.dumps(consistency, indent=2) + "\n", encoding="utf-8"
    )
    completion = {
        "qrels_audit_status": "complete", "pooled_judgments_reviewed": len(records),
        "changed_judgments": len(additions),
        "pool_stage": args.pool_stage,
        "relevance_scale": "binary_0_1",
        "audited_qrels_sha256": hashlib.sha256(audited_path.read_bytes()).hexdigest(),
    }
    (output / "qrels_audit_completion.json").write_text(
        json.dumps(completion, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(consistency, indent=2))


if __name__ == "__main__":
    main()
