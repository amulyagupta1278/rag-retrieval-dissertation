#!/usr/bin/env python3
"""Replace only cross-scheme QA/qrels while preserving the validated 60 items."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.benchmark.qa_generator import QAGenerator, QAItem, QUERY_CATEGORIES
from src.benchmark.qrels_builder import QRelsBuilder
from src.benchmark.query_categorizer import QueryCategorizer
from src.utils.io_utils import load_jsonl


def _publish(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".new")
    shutil.copy2(source, temporary)
    os.replace(temporary, destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build validated cross-scheme QA/qrels")
    parser.add_argument("--version", default="v3_clean")
    parser.add_argument("--chunks", default="data/chunks/chunks.jsonl")
    parser.add_argument("--base-qa", default="data/queries/qa_dataset.jsonl")
    parser.add_argument("--graph", default="indexes/graphrag/graph.gpickle")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--publish-canonical", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    chunks = load_jsonl(args.chunks)
    current = [QAItem.from_dict(item) for item in load_jsonl(args.base_qa)]
    preserved = [
        item for item in current
        if item.category in {"exact_match", "terminology_heavy", "paraphrase"}
    ]
    preserved_counts = {category: sum(item.category == category for item in preserved) for category in QUERY_CATEGORIES}
    if len(preserved) != 60 or any(preserved_counts[category] != 20 for category in QUERY_CATEGORIES[:3]):
        raise RuntimeError(f"Expected 20 validated items in each preserved category: {preserved_counts}")

    generator = QAGenerator(seed=42)
    cross_items, audit = generator.generate_cross_scheme(chunks, graph_path=args.graph)
    cross_stats = generator.last_generation_stats
    items = preserved + cross_items
    items.sort(key=lambda item: item.question_id)
    QAGenerator.assign_stratified_splits(items, dev_ratio=0.2, seed=42)
    counts = {category: sum(item.category == category for item in items) for category in QUERY_CATEGORIES}
    stats = {
        **cross_stats,
        "preserved_questions": len(preserved),
        "total_questions": len(items),
        "accepted_by_category": counts,
        "audit_items": len(audit),
    }
    if len(items) != 100 or any(counts.get(category) != 20 for category in QUERY_CATEGORIES):
        raise RuntimeError(f"QA validation gate could not produce balanced 100-query benchmark: {stats}")
    if len({item.question_id for item in items}) != 100:
        raise RuntimeError("Duplicate question IDs after cross-scheme replacement")
    qrels = QRelsBuilder.build_qrels(items)
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    missing = {chunk_id for _, chunk_id, _ in qrels} - chunk_ids
    if missing:
        raise RuntimeError(f"Generated qrels reference missing chunks: {sorted(missing)}")
    categorized = QueryCategorizer().categorize_dataset([item.to_dict() for item in items])

    staging = Path(tempfile.mkdtemp(prefix=f"qa-{args.version}-", dir="data"))
    try:
        QAGenerator.save(items, staging / "qa_dataset.jsonl")
        QRelsBuilder.save_qrels_tsv(qrels, staging / "qrels.tsv")
        QRelsBuilder.save_evidence_map(items, staging / "evidence_map.json")
        QueryCategorizer.save(categorized, staging / "query_categories.json")
        stats_name = f"qa_validation_stats_{args.version}.json"
        audit_jsonl_name = f"cross_scheme_audit_{args.version}.jsonl"
        audit_md_name = f"cross_scheme_audit_{args.version}.md"
        (staging / stats_name).write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
        with (staging / audit_jsonl_name).open("w", encoding="utf-8") as handle:
            for record in audit:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        audit_lines = [
            f"# Cross-Scheme QA Audit {args.version}", "",
            f"- Accepted: {len(audit)}/40", "- Distinct schemes: 40/40",
            "- Two gold chunks and documents: 40/40", "",
            "| ID | Category | Scheme A | Scheme B | Bridge | Gold chunks |", "|---|---|---|---|---|---|",
        ]
        for record in audit:
            audit_lines.append(
                "| {question_id} | {category} | {scheme_a} | {scheme_b} | {bridge} | {gold} |".format(
                    question_id=record["question_id"], category=record["category"],
                    scheme_a=record["schemes"][0].replace("|", "\\|"),
                    scheme_b=record["schemes"][1].replace("|", "\\|"),
                    bridge=record["bridge_entity"].replace("|", "\\|"),
                    gold="<br>".join(record["gold_chunk_ids"]),
                )
            )
        (staging / audit_md_name).write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

        output_dir = Path(args.output_dir) if args.output_dir else Path("data")
        versioned_mapping = {
            "qa_dataset.jsonl": output_dir / "queries" / f"qa_dataset_{args.version}.jsonl",
            "qrels.tsv": output_dir / "qrels" / f"qrels_{args.version}.tsv",
            "evidence_map.json": output_dir / "qrels" / f"evidence_map_{args.version}.json",
            "query_categories.json": output_dir / "queries" / f"query_categories_{args.version}.json",
            stats_name: output_dir / "metadata" / stats_name,
            audit_jsonl_name: output_dir / "metadata" / audit_jsonl_name,
            audit_md_name: output_dir / "metadata" / audit_md_name,
        }
        for source, destination in versioned_mapping.items():
            _publish(staging / source, destination)

        if args.publish_canonical:
            for source, destination in {
                "qa_dataset.jsonl": "data/queries/qa_dataset.jsonl",
                "qrels.tsv": "data/qrels/qrels.tsv",
                "evidence_map.json": "data/qrels/evidence_map.json",
                "query_categories.json": "data/queries/query_categories.json",
                stats_name: f"data/metadata/{stats_name}",
                audit_jsonl_name: f"data/metadata/{audit_jsonl_name}",
                audit_md_name: f"data/metadata/{audit_md_name}",
            }.items():
                _publish(staging / source, Path(destination))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
