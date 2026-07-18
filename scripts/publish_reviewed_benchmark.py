#!/usr/bin/env python3
"""Publish reviewed 100-query development benchmark after audit gates pass."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.benchmark.benchmark_contract import validate_benchmark
from src.benchmark.qa_generator import QAItem
from src.benchmark.qrels_builder import QRelsBuilder
from src.utils.artifact_provenance import sha256_file
from src.utils.io_utils import load_jsonl, save_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", required=True, help="Reviewed/replacement QA JSONL")
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--audit-summary", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--benchmark-version", default="v3_clean_benchmark_r1")
    args = parser.parse_args()

    audit = json.loads(Path(args.audit_summary).read_text(encoding="utf-8"))
    if not audit.get("agreement_gate_passed") or audit.get("questions_reviewed") != 100:
        raise RuntimeError("Question audit/inter-review agreement gate has not passed")
    qa = load_jsonl(args.qa)
    chunks = load_jsonl(args.chunks)
    rejected = set(audit.get("rejected_questions", []))
    errors = validate_benchmark(
        qa, chunks, expected_per_category=20, max_gold_reuse=2,
        require_reviewed=True, expected_version=args.benchmark_version,
    )
    for item in qa:
        if item["question_id"] in rejected and (
            int(item.get("review_revision", 0)) < 2
            or not item.get("extra_meta", {}).get("replacement_reason")
        ):
            errors.append(
                f"{item['question_id']}: rejected original lacks reviewed replacement metadata"
            )
    if errors:
        raise RuntimeError("Benchmark publication failed:\n- " + "\n- ".join(errors[:200]))

    output = Path(args.output_dir)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Benchmark release directory already exists: {output}")
    output.mkdir(parents=True, exist_ok=True)
    qa_path = output / "qa_dataset.jsonl"
    save_jsonl(sorted(qa, key=lambda item: item["question_id"]), qa_path)
    items = [QAItem.from_dict(item) for item in qa]
    qrels_path = output / "qrels_gold.tsv"
    QRelsBuilder.save_qrels_tsv(QRelsBuilder.build_qrels(items), qrels_path)
    QRelsBuilder.save_evidence_map(items, output / "evidence_map.json")
    categories = {
        item["question_id"]: {
            "category": item["category"], "difficulty": item["difficulty"],
            "fold_id": item["fold_id"], "split": item["split"],
        }
        for item in sorted(qa, key=lambda value: value["question_id"])
    }
    (output / "query_categories.json").write_text(
        json.dumps(categories, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    qrels = QRelsBuilder.load_qrels_tsv(qrels_path)
    judgment_count = sum(len(values) for values in qrels.values())
    if judgment_count != 140:
        raise RuntimeError(f"Expected 140 generated gold judgments, got {judgment_count}")
    manifest = {
        "benchmark_version": args.benchmark_version,
        "corpus_chunks_sha256": sha256_file(args.chunks),
        "qa_sha256": sha256_file(qa_path),
        "gold_qrels_sha256": sha256_file(qrels_path),
        "queries": len(qa), "gold_judgments": judgment_count,
        "status": "reviewed_development_benchmark_published",
    }
    (output / "benchmark_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
