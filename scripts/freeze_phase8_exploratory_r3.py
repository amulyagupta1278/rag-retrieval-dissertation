#!/usr/bin/env python3
"""Freeze hashes and scope for Phase 8 automated exploratory R3."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "runs/phase8_exploratory_automated_r3"
AUDIT = ROOT / "audits/phase8_exploratory/automated_r3_benchmark_audit"
OUTPUT = ROOT / "audits/phase8_exploratory/automated_r3_freeze.json"
MANIFEST = ROOT / "audits/phase8_exploratory/automated_r3_manifest.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    files = sorted(
        [path for base in (RUN, AUDIT) for path in base.rglob("*") if path.is_file()],
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
    if not files:
        raise RuntimeError("R3 artifacts missing")
    records = [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in files
    ]
    MANIFEST.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    candidate = json.loads((RUN / "benchmark/candidate_summary.json").read_text(encoding="utf-8"))
    audit = json.loads((AUDIT / "audit_summary.json").read_text(encoding="utf-8"))
    metrics = json.loads(
        (RUN / "results/reports/phase0_benchmark_metrics.json").read_text(encoding="utf-8")
    )
    freeze = {
        "status": "exploratory_automated_only_pending_human_validation",
        "benchmark_version": "v3_clean_exploratory_automated_r3",
        "documents": 130,
        "chunks": metrics["corpus_chunks"],
        "questions": metrics["queries"],
        "qrels": metrics["qrels_judgments"],
        "questions_repaired": candidate["questions_repaired"],
        "changed_gold_evidence": candidate["changed_gold_evidence"],
        "automatic_failures": audit["automatic_failures"],
        "human_review_complete": False,
        "owner_approved": False,
        "final_dissertation_evidence": False,
        "api_calls": 0,
        "systems": ["bm25", "faiss", "graphrag"],
        "aggregate_metrics": metrics["aggregate"],
        "legacy_index_limitation": "Frozen BM25/FAISS indexes lack configuration_hash; release-level 56-file manifest verifies, but strict index provenance mode cannot pass.",
        "manifest": {
            "path": MANIFEST.relative_to(ROOT).as_posix(),
            "sha256": sha256(MANIFEST),
            "files": len(records),
            "bytes": sum(record["bytes"] for record in records),
        },
        "reporting_boundary": "Diagnostic automated expansion only. Do not replace frozen Phase 1-7 pilot findings or claim human validation.",
    }
    OUTPUT.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(freeze, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
