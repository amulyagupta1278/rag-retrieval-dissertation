import json

import pytest

from src.utils.artifact_provenance import chunk_provenance, validate_chunk_provenance


def test_provenance_detects_same_count_wrong_order(tmp_path):
    chunks = [
        {"chunk_id": "c1", "doc_id": "d1", "text": "one"},
        {"chunk_id": "c2", "doc_id": "d2", "text": "two"},
    ]
    path = tmp_path / "chunks.jsonl"
    path.write_text("".join(json.dumps(chunk) + "\n" for chunk in chunks), encoding="utf-8")
    recorded = chunk_provenance(chunks, path)
    with pytest.raises(RuntimeError, match="corpus_content_sha256|ordered_chunk_ids_sha256"):
        validate_chunk_provenance(recorded, list(reversed(chunks)), require_complete=True)


def test_provenance_requires_complete_contract():
    with pytest.raises(RuntimeError, match="missing required fields"):
        validate_chunk_provenance({}, [{"chunk_id": "c1", "doc_id": "d1", "text": "x"}], require_complete=True)
