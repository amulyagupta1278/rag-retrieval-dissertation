import argparse
import json

import pytest

from scripts.release_manifest import verify_manifest, write_manifest
from scripts.release_pipeline import validate_benchmark_cardinality
from src.ingestion.corpus_quality import build_statistics


def _args(tmp_path):
    root = tmp_path / "release"
    (root / "data").mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "data/chunks.jsonl").write_text('{"chunk_id":"c1"}\n', encoding="utf-8")
    (root / "configs/corpus.yaml").write_text("corpus:\n  version: fixture\n", encoding="utf-8")
    return argparse.Namespace(
        include_root=[str(root / "data"), str(root / "configs")], base_dir=str(root),
        manifest=str(root / "release_manifest.jsonl"), sums=str(root / "SHA256SUMS"),
        version="fixture", chunk_count=1, query_count=1,
        creation_command="fixture", config=[str(root / "configs/corpus.yaml")], verify=False,
    )


def test_release_manifest_is_complete_and_versioned(tmp_path):
    args = _args(tmp_path)
    write_manifest(args)
    verify_manifest(args)
    records = [json.loads(line) for line in open(args.manifest, encoding="utf-8")]
    assert len(records) == 2
    assert {record["corpus_version"] for record in records} == {"fixture"}
    assert {record["relative_path"] for record in records} == {"data/chunks.jsonl", "configs/corpus.yaml"}


def test_release_manifest_rejects_unexpected_or_changed_file(tmp_path):
    args = _args(tmp_path)
    write_manifest(args)
    root = tmp_path / "release"
    (root / "data/untracked.txt").write_text("unexpected", encoding="utf-8")
    with pytest.raises(SystemExit, match="unexpected"):
        verify_manifest(args)


def test_statistics_counts_actual_artifacts_and_version():
    documents = [{
        "doc_id": "d1", "ministry": "M", "scheme_name": "S", "document_type": "faq",
        "source_type": "json", "url": "https://example.gov.in/x", "publication_date": None,
        "ingested_at": "2026-01-01T00:00:00+00:00",
    }]
    chunks = [{"chunk_id": "c1", "doc_id": "d1", "word_count": 4}]
    stats = build_statistics(documents, chunks, corpus_version="fixture")
    assert stats["corpus_version"] == "fixture"
    assert stats["accepted_documents"] == 1
    assert stats["total_chunks"] == 1
    assert stats["build_timestamp"] == "2026-01-01T00:00:00+00:00"


def test_release_rejects_pre_cross_120_qrel_benchmark():
    qa = [{"question_id": f"q_{index:04d}"} for index in range(100)]
    qrels = {item["question_id"]: {f"c_{index:04d}": 1} for index, item in enumerate(qa)}
    for index in range(20):
        qrels[f"q_{index:04d}"][f"extra_{index:04d}"] = 1
    with pytest.raises(RuntimeError, match="judgments=120"):
        validate_benchmark_cardinality(qa, qrels, expected_queries=100, expected_judgments=140)
