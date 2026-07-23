from __future__ import annotations

import json

import pytest

from src.contracts._validation import ContractError
from src.contracts.artifact import ArtifactManifest, ArtifactRecord
from src.contracts.benchmark import QAItemV2, QrelsJudgment
from src.contracts.chunk import ChunkV2
from src.contracts.source import RawSourceRecord
from src.utils.atomic_io import write_json, write_jsonl

H = "a" * 64


def source(**changes):
    values = dict(schema_version="2.0", source_id="s1", scheme_id="pmay", scheme_title="PMAY",
                  ministry="Housing", department="", official_url="https://example.gov.in/a",
                  retrieved_at="2026-07-23T00:00:00Z", http_status=200,
                  final_url="https://example.gov.in/a", mime_type="application/json", content_length=3,
                  acquisition_method="structured_api", raw_sha256=H, raw_snapshot_path="data/v2/a.json",
                  extraction_method="approved_fields", extraction_tool_version="1", extraction_status="complete",
                  validation_status="valid")
    values.update(changes)
    return RawSourceRecord(**values)


def test_source_contract_rejects_bad_inputs():
    assert source().source_id == "s1"
    for change in ({"schema_version": "1"}, {"official_url": "http://bad"}, {"raw_sha256": "bad"},
                   {"mime_type": "text/plain"}, {"scheme_title": "synthetic fallback"},
                   {"extraction_status": "partial"}):
        with pytest.raises((ValueError, ContractError)):
            source(**change)


def test_chunk_contract_enforces_ranges():
    base = dict(schema_version="2.0", chunk_id="c1", document_id="d1", source_id="s1", chunk_index=0,
                start_word=0, end_word=300, word_count=300, start_char=0, end_char=599,
                previous_overlap=0, text="x " * 299 + "x", text_sha256=H, source_sha256=H,
                corpus_version="pilot-v2", renderer_version="1", chunker_version="1")
    assert ChunkV2(**base).word_count == 300
    with pytest.raises(ValueError, match="1..300"):
        ChunkV2(**{**base, "end_word": 301, "word_count": 301})


def test_benchmark_contracts_enforce_multihop_synthesis_and_grade_zero():
    base = dict(schema_version="2.0", question_id="q1", benchmark_version="pilot-v2", category="multi_hop",
                difficulty="hard", question="Which support connects these beneficiaries?", reference_answer="A and B.",
                gold_evidence_ids=("c1", "c2"), source_document_ids=("d1", "d2"),
                supporting_evidence_quotes=("A", "B"), authoring_method="manual_draft",
                review_status="pending_human_review", review_revision=0, split="dev", notes="", bridge_entity="farmer")
    assert QAItemV2(**base).category == "multi_hop"
    with pytest.raises(ValueError, match="bridge_entity"):
        QAItemV2(**{**base, "bridge_entity": ""})
    with pytest.raises(ValueError, match="three chunks"):
        QAItemV2(**{**base, "category": "synthesis", "bridge_entity": ""})
    with pytest.raises(ValueError, match="explicit review"):
        QrelsJudgment("2.0", "q1", "c1", 0, "pool", "pending", "")


def test_artifact_manifest_rejects_unknown_lineage():
    item = ArtifactRecord("a", "x", H, 1, "test", ("missing",))
    with pytest.raises(ValueError, match="unknown input"):
        ArtifactManifest("2.0", "m", "now", (item,))


def test_atomic_writers_are_stable_collision_safe_and_duplicate_safe(tmp_path):
    path = tmp_path / "a.json"
    write_json(path, {"z": 1, "a": 2})
    assert path.read_text() == '{"a":2,"z":1}\n'
    with pytest.raises(FileExistsError):
        write_json(path, {})
    rows = tmp_path / "rows.jsonl"
    write_jsonl(rows, [{"id": "b"}, {"id": "a"}], key="id")
    assert [json.loads(x)["id"] for x in rows.read_text().splitlines()] == ["a", "b"]
    with pytest.raises(ValueError, match="duplicate"):
        write_jsonl(tmp_path / "dup", [{"id": "a"}, {"id": "a"}], key="id")
