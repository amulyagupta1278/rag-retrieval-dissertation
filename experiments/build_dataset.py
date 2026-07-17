#!/usr/bin/env python3
"""Canonical corpus v2 and unchanged benchmark build pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.benchmark.qa_generator import QAGenerator
from src.benchmark.qrels_builder import QRelsBuilder
from src.benchmark.query_categorizer import QueryCategorizer
from src.ingestion.chunker import Chunker
from src.ingestion.corpus_quality import (
    CorpusValidationError, deduplicate_documents, validate_corpus,
)
from src.ingestion.corpus_versioner import CorpusVersioner
from src.ingestion.document_loader import DocumentLoader
from src.ingestion.metadata_enricher import MetadataEnricher
from src.ingestion.text_cleaner import CleaningConfig, TextCleaner
from src.utils.io_utils import load_jsonl, load_yaml, save_jsonl
from src.utils.logging_utils import get_logger, setup_logging

LOGGER = get_logger("build_dataset")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build authoritative corpus v2 and benchmark")
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--metadata", default=None)
    parser.add_argument("--corpus-config", default="configs/corpus.yaml")
    parser.add_argument("--chunking-config", default="configs/chunking.yaml")
    parser.add_argument("--version", default="v2")
    parser.add_argument("--max-qa-per-category", type=int, default=20)
    parser.add_argument("--skip-size-gates", action="store_true", help="Tests/development only")
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def _english_ratio(text: str) -> float:
    letters = [char for char in text if char.isalpha()]
    return sum(char.isascii() for char in letters) / len(letters) if letters else 0.0


def _validate_extraction(raw_doc, cleaned: str, corpus_cfg: dict) -> str | None:
    if len(cleaned) < corpus_cfg.get("min_doc_length", 100):
        return "cleaned text below minimum length"
    if len(cleaned) > corpus_cfg.get("max_doc_length", 500000):
        return "cleaned text exceeds maximum length"
    lower = cleaned[:100_000].lower()
    if raw_doc.source_type in {"html", "htm"} and any(
        marker in lower for marker in ("captcha", "access denied", "login required", "page not found")
    ):
        return "login/CAPTCHA/error content"
    if _english_ratio(cleaned) < corpus_cfg.get("min_english_ratio", 0.8):
        return "text is not predominantly English"
    pages = raw_doc.extra_meta.get("num_pages", 0)
    if pages and len(cleaned) / pages < corpus_cfg.get("min_pdf_chars_per_page", 80):
        return "likely scanned PDF with insufficient extractable text"
    return None


def _metadata_fields(meta: dict) -> dict:
    keys = (
        "document_id", "source", "ministry", "scheme_name", "publication_date",
        "url", "document_type", "language", "scope", "catalog_id", "final_url",
        "retrieved_at",
    )
    return {key: meta.get(key) for key in keys}


def _write_sources(documents: list[dict], chunks: list[dict], path: Path) -> None:
    chunks_per_doc = Counter(chunk["doc_id"] for chunk in chunks)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fields = ["document_id", "source", "ministry", "scheme_name", "publication_date", "URL", "document_type", "sha256", "doc_count", "chunk_count"]
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for doc in documents:
            writer.writerow({
                "document_id": doc["document_id"], "source": doc["source"],
                "ministry": doc["ministry"], "scheme_name": doc["scheme_name"],
                "publication_date": doc["publication_date"], "URL": doc["url"],
                "document_type": doc["document_type"], "sha256": doc["sha256"],
                "doc_count": 1, "chunk_count": chunks_per_doc[doc["doc_id"]],
            })


def _publish(staging: Path, mapping: dict[str, str]) -> None:
    for staged_name, destination in mapping.items():
        source, target = staging / staged_name, Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".new")
        shutil.copy2(source, temporary)
        os.replace(temporary, target)


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)
    corpus_cfg = load_yaml(args.corpus_config).get("corpus", {})
    chunk_cfg = load_yaml(args.chunking_config).get("chunking", {})
    snapshot = Path(args.snapshot_dir or corpus_cfg.get("snapshot_dir", "data/raw/snapshot_v2"))
    metadata_path = Path(args.metadata or snapshot / "metadata.jsonl")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Acquisition metadata not found: {metadata_path}")

    metadata = sorted(load_jsonl(metadata_path), key=lambda item: item["catalog_id"])
    loader = DocumentLoader(domain_tag=corpus_cfg.get("domain", "indian_government_welfare_schemes"))
    cleaner = TextCleaner(CleaningConfig())
    chunker = Chunker(
        chunk_size=chunk_cfg.get("chunk_size", 512),
        chunk_overlap=chunk_cfg.get("chunk_overlap", 64),
        min_chunk_length=chunk_cfg.get("min_chunk_length", 50),
        respect_sentence_boundaries=chunk_cfg.get("respect_sentence_boundaries", True),
    )
    enricher = MetadataEnricher()
    candidates: list[dict] = []
    extraction_rejections: list[dict] = []

    for meta in metadata:
        path = Path(meta.get("local_path") or snapshot / f"{meta['catalog_id']}.{meta['format']}")
        if not path.is_absolute() and not path.exists():
            path = Path.cwd() / path
        raw_doc = loader.load_file(path)
        cleaned = cleaner.clean(raw_doc.raw_text)
        rejection = _validate_extraction(raw_doc, cleaned, corpus_cfg)
        if rejection:
            extraction_rejections.append({"rejected_document_id": meta["document_id"], "method": "extraction_quality", "reason": rejection, "url": meta["url"]})
            continue
        document = raw_doc.to_dict()
        document.update(_metadata_fields(meta))
        document["cleaned_text"] = cleaned
        document["extra_meta"] = {**raw_doc.extra_meta, **_metadata_fields(meta)}
        candidates.append(document)

    documents, duplicate_reports = deduplicate_documents(candidates, corpus_cfg.get("dedup_threshold", 0.95))
    chunks: list[dict] = []
    for document in documents:
        provenance = _metadata_fields(document)
        generated = chunker.chunk_document(
            doc_id=document["doc_id"], text=document["cleaned_text"],
            source_path=document["source_path"], domain_tag=document["domain_tag"],
            section_title=document["scheme_name"], extra_meta=provenance,
        )
        for chunk in generated:
            item = enricher.enrich(chunk.to_dict())
            item.update(provenance)
            item["extra_meta"] = provenance
            chunks.append(item)
        document["num_chunks"] = len(generated)

    if args.skip_size_gates:
        validation_cfg = {**corpus_cfg, "min_documents": 0, "max_documents": 10**9, "min_chunks": 0, "max_chunks": 10**9, "min_ministries": 0}
    else:
        validation_cfg = corpus_cfg
    validate_corpus(documents, chunks, validation_cfg)

    generator = QAGenerator(seed=42)
    qa_items = generator.generate(chunks, max_per_category=args.max_qa_per_category)
    qrels = QRelsBuilder.build_qrels(qa_items)
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}
    missing_evidence = {evidence for _, evidence, _ in qrels} - chunk_ids
    if missing_evidence:
        raise CorpusValidationError(f"qrels reference missing chunks: {sorted(missing_evidence)}")
    categorized = QueryCategorizer().categorize_dataset([item.to_dict() for item in qa_items])

    staging = Path(tempfile.mkdtemp(prefix="corpus-v2-", dir="data"))
    try:
        save_jsonl(documents, staging / "documents.jsonl")
        save_jsonl(chunks, staging / "chunks.jsonl")
        QAGenerator.save(qa_items, staging / "qa_dataset.jsonl")
        QRelsBuilder.save_qrels_tsv(qrels, staging / "qrels.tsv")
        QRelsBuilder.save_evidence_map(qa_items, staging / "evidence_map.json")
        QueryCategorizer.save(categorized, staging / "query_categories.json")
        save_jsonl(extraction_rejections + duplicate_reports, staging / "deduplication_report.jsonl")
        _write_sources(documents, chunks, staging / "sources.csv")
        manifest = {
            "corpus_version": args.version, "total_documents": len(documents),
            "total_chunks": len(chunks), "chunk_size": chunk_cfg.get("chunk_size", 512),
            "chunk_overlap": chunk_cfg.get("chunk_overlap", 64),
            "documents_by_ministry": dict(Counter(doc["ministry"] for doc in documents)),
            "duplicates_removed": len(duplicate_reports),
            "extraction_rejections": len(extraction_rejections),
        }
        (staging / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        mapping = {
            "documents.jsonl": "data/processed/documents.jsonl",
            "chunks.jsonl": "data/chunks/chunks.jsonl",
            "qa_dataset.jsonl": "data/queries/qa_dataset.jsonl",
            "qrels.tsv": "data/qrels/qrels.tsv",
            "evidence_map.json": "data/qrels/evidence_map.json",
            "query_categories.json": "data/queries/query_categories.json",
            "deduplication_report.jsonl": f"data/metadata/deduplication_report_{args.version}.jsonl",
            "sources.csv": "data/metadata/sources.csv",
            "corpus_manifest.json": "data/metadata/corpus_manifest.json",
        }
        _publish(staging, mapping)
        shutil.copy2(staging / "chunks.jsonl", f"data/chunks/chunks_{args.version}.jsonl")
        shutil.copy2(staging / "qa_dataset.jsonl", f"data/queries/qa_dataset_{args.version}.jsonl")
        shutil.copy2(staging / "qrels.tsv", f"data/qrels/qrels_{args.version}.tsv")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    versioner = CorpusVersioner("data/raw", version=args.version)
    versioner.save_manifest(documents)
    versioner.save_corpus_profile(documents)
    LOGGER.info("Pipeline complete: %d documents | %d chunks | %d QA | %d qrels", len(documents), len(chunks), len(qa_items), len(qrels))


if __name__ == "__main__":
    main()
