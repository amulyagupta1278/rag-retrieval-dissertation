"""
build_dataset.py — Full Dataset and Benchmark Pipeline
========================================================
Runs the complete data layer:
    1. Load raw documents from data/raw/snapshot_v1/
    2. Clean, chunk, enrich with metadata
    3. Save chunks.jsonl, processed docs, corpus manifest
    4. Generate QA benchmark + qrels + query categories

Usage:
    cd dissertation/
    python experiments/build_dataset.py [--snapshot-dir data/raw/snapshot_v1]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.logging_utils import setup_logging, get_logger
from src.utils.io_utils import save_jsonl, load_yaml
from src.ingestion.document_loader import DocumentLoader
from src.ingestion.text_cleaner import TextCleaner, CleaningConfig
from src.ingestion.chunker import Chunker
from src.ingestion.metadata_enricher import MetadataEnricher
from src.ingestion.corpus_versioner import CorpusVersioner
from src.benchmark.qa_generator import QAGenerator
from src.benchmark.qrels_builder import QRelsBuilder
from src.benchmark.query_categorizer import QueryCategorizer

logger = get_logger("build_dataset")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build corpus and benchmark dataset")
    p.add_argument("--snapshot-dir", default="data/raw/snapshot_v1")
    p.add_argument("--corpus-config", default="configs/corpus.yaml")
    p.add_argument("--chunking-config", default="configs/chunking.yaml")
    p.add_argument("--version", default="v1")
    p.add_argument("--max-qa-per-category", type=int, default=20)
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)

    corpus_cfg = load_yaml(args.corpus_config).get("corpus", {})
    chunk_cfg = load_yaml(args.chunking_config).get("chunking", {})

    logger.info("=== Dataset Pipeline v%s ===", args.version)

    # 1. Load documents
    loader = DocumentLoader(domain_tag=corpus_cfg.get("domain", "general"))
    snapshot_dir = Path(args.snapshot_dir)
    if not snapshot_dir.exists():
        logger.warning("Snapshot dir does not exist: %s — creating empty dir for demo.", snapshot_dir)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

    raw_docs = list(loader.load_directory(snapshot_dir))
    logger.info("Loaded %d raw documents", len(raw_docs))

    if not raw_docs:
        logger.warning(
            "No documents found. Place PDF/DOCX/TXT files in %s and re-run.", snapshot_dir
        )
        # Create placeholder chunk for demo purposes so downstream scripts don't fail
        _write_placeholder_data(args.version)
        return

    # 2. Clean
    cleaner = TextCleaner(CleaningConfig())

    # 3. Chunk
    chunker = Chunker(
        chunk_size=chunk_cfg.get("chunk_size", 512),
        chunk_overlap=chunk_cfg.get("chunk_overlap", 64),
        min_chunk_length=chunk_cfg.get("min_chunk_length", 50),
        respect_sentence_boundaries=chunk_cfg.get("respect_sentence_boundaries", True),
    )

    # 4. Enrich
    enricher = MetadataEnricher()

    all_chunks: list[dict] = []
    processed_docs: list[dict] = []

    for raw_doc in raw_docs:
        cleaned_text = cleaner.clean(raw_doc.raw_text)
        chunks = chunker.chunk_document(
            doc_id=raw_doc.doc_id,
            text=cleaned_text,
            source_path=raw_doc.source_path,
            domain_tag=raw_doc.domain_tag,
            section_title="",
        )
        chunk_dicts = [c.to_dict() for c in chunks]
        enriched = enricher.enrich_batch(chunk_dicts)
        all_chunks.extend(enriched)

        doc_dict = raw_doc.to_dict()
        doc_dict["cleaned_text"] = cleaned_text
        doc_dict["num_chunks"] = len(chunks)
        processed_docs.append(doc_dict)

    logger.info("Total chunks: %d from %d documents", len(all_chunks), len(processed_docs))

    # Save processed outputs
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    save_jsonl(processed_docs, "data/processed/documents.jsonl")

    Path("data/chunks").mkdir(parents=True, exist_ok=True)
    save_jsonl(all_chunks, "data/chunks/chunks.jsonl")
    logger.info("Chunks saved → data/chunks/chunks.jsonl")

    # 5. Corpus versioning
    versioner = CorpusVersioner("data/raw", version=args.version)
    versioner.save_manifest(processed_docs)
    versioner.save_corpus_profile(processed_docs)

    # 6. Generate QA benchmark
    generator = QAGenerator(seed=42)
    qa_items = generator.generate(all_chunks, max_per_category=args.max_qa_per_category)
    Path("data/queries").mkdir(parents=True, exist_ok=True)
    QAGenerator.save(qa_items, "data/queries/qa_dataset.jsonl")

    # 7. Build qrels
    qrels = QRelsBuilder.build_qrels(qa_items)
    Path("data/qrels").mkdir(parents=True, exist_ok=True)
    QRelsBuilder.save_qrels_tsv(qrels, "data/qrels/qrels.tsv")
    QRelsBuilder.save_evidence_map(qa_items, "data/qrels/evidence_map.json")

    # 8. Categorize queries
    categorizer = QueryCategorizer()
    categorized = categorizer.categorize_dataset([item.to_dict() for item in qa_items])
    QueryCategorizer.save(categorized, "data/queries/query_categories.json")

    logger.info(
        "Pipeline complete: %d docs | %d chunks | %d QA items | %d qrels",
        len(processed_docs),
        len(all_chunks),
        len(qa_items),
        len(qrels),
    )


def _write_placeholder_data(version: str) -> None:
    """Write minimal placeholder files so downstream scripts can run in demo mode."""
    import json, hashlib

    dummy_chunk = {
        "chunk_id": "chunk_demo0001",
        "doc_id": "doc_demo",
        "text": (
            "BM25 is a ranking function used by search engines to estimate the relevance of "
            "documents to a given search query. It is based on the probabilistic retrieval "
            "framework developed in the 1970s and 1980s. FAISS (Facebook AI Similarity Search) "
            "is a library for efficient similarity search and clustering of dense vectors. "
            "GraphRAG organises knowledge as a graph of entities and relations."
        ),
        "chunk_index": 0,
        "start_char": 0,
        "end_char": 300,
        "word_count": 62,
        "source_path": "data/raw/snapshot_v1/placeholder.txt",
        "domain_tag": "information_retrieval",
        "section_title": "Introduction",
        "extra_meta": {},
    }
    Path("data/chunks").mkdir(parents=True, exist_ok=True)
    save_jsonl([dummy_chunk], "data/chunks/chunks.jsonl")

    from src.benchmark.qa_generator import QAGenerator, QAItem
    from src.benchmark.qrels_builder import QRelsBuilder
    from src.benchmark.query_categorizer import QueryCategorizer

    qa_items = [
        QAItem(
            question_id="q_0001",
            question="What is BM25?",
            category="exact_match",
            difficulty="easy",
            reference_answer="BM25 is a ranking function used by search engines.",
            gold_evidence_ids=["chunk_demo0001"],
            source_doc_ids=["doc_demo"],
            split="test",
        ),
        QAItem(
            question_id="q_0002",
            question="What does FAISS stand for?",
            category="terminology_heavy",
            difficulty="easy",
            reference_answer="Facebook AI Similarity Search",
            gold_evidence_ids=["chunk_demo0001"],
            source_doc_ids=["doc_demo"],
            split="test",
        ),
        QAItem(
            question_id="q_0003",
            question="What information is provided about similarity search and dense vectors?",
            category="paraphrase",
            difficulty="medium",
            reference_answer="FAISS is a library for efficient similarity search and clustering of dense vectors.",
            gold_evidence_ids=["chunk_demo0001"],
            source_doc_ids=["doc_demo"],
            split="test",
        ),
        QAItem(
            question_id="q_0004",
            question="How does GraphRAG relate to entity and relation knowledge?",
            category="entity_relation",
            difficulty="medium",
            reference_answer="GraphRAG organises knowledge as a graph of entities and relations.",
            gold_evidence_ids=["chunk_demo0001"],
            source_doc_ids=["doc_demo"],
            split="test",
        ),
        QAItem(
            question_id="q_0005",
            question="How are BM25 probabilistic retrieval and FAISS dense vectors connected?",
            category="multi_hop",
            difficulty="hard",
            reference_answer="Both BM25 and FAISS are retrieval methods; BM25 is sparse/lexical while FAISS is dense/semantic.",
            gold_evidence_ids=["chunk_demo0001"],
            source_doc_ids=["doc_demo"],
            split="test",
        ),
    ]

    Path("data/queries").mkdir(parents=True, exist_ok=True)
    QAGenerator.save(qa_items, "data/queries/qa_dataset.jsonl")

    qrels = QRelsBuilder.build_qrels(qa_items)
    Path("data/qrels").mkdir(parents=True, exist_ok=True)
    QRelsBuilder.save_qrels_tsv(qrels, "data/qrels/qrels.tsv")
    QRelsBuilder.save_evidence_map(qa_items, "data/qrels/evidence_map.json")

    categorizer = QueryCategorizer()
    categorized = categorizer.categorize_dataset([i.to_dict() for i in qa_items])
    QueryCategorizer.save(categorized, "data/queries/query_categories.json")

    logger.info("Placeholder data written — add real documents and re-run build_dataset.py")


if __name__ == "__main__":
    main()
