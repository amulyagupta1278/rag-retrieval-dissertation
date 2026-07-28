from __future__ import annotations

import hashlib
import json
from email.message import Message

import pytest

from src.ingestion.v2_pipeline import AcquisitionError, chunk_document_v2, fetch_https, render_myscheme_record

H = "a" * 64


def record(**content):
    body = {"briefDescription": "This programme provides durable support to eligible households through an official application process. " * 5,
            "benefits_md": "Eligible households receive financial assistance for approved needs.", **content}
    return {"en": {"basicDetails": {"schemeName": "Example Scheme", "nodalMinistryName": {"label": "Ministry of Example"},
                                     "nodalDepartmentName": {"label": "Example Department"}, "implementingAgency": "Example Agency"},
                   "schemeContent": body, "eligibilityCriteria": {"eligibilityDescription_md": "Applicants must satisfy published conditions."},
                   "applicationProcess": [{"process_md": "Applicants submit documents through the official portal."}]}}


def test_renderer_allows_only_clean_prose():
    text, metadata = render_myscheme_record(record())
    assert metadata["title"] == "Example Scheme"
    assert not any(x in text for x in ("briefDescription", "Benefits:", "{", "<script", "null"))


@pytest.mark.parametrize("bad", ['{"schemeContent":"raw"}', "Benefits: <script>alert(1)</script> cookie banner"])
def test_renderer_rejects_json_labels_and_hostile_content(bad):
    with pytest.raises(ValueError):
        render_myscheme_record(record(briefDescription=bad))


def test_chunker_exact_window_overlap_offsets_unicode_stability():
    words = ["repeat", "repeat", "नमस्ते"] + [f"w{i}" for i in range(298)]
    text = " ".join(words)
    first = chunk_document_v2(document_id="d", source_id="s", text=text, source_sha256=H)
    second = chunk_document_v2(document_id="d", source_id="s", text=text, source_sha256=H)
    assert [c.to_dict() for c in first] == [c.to_dict() for c in second]
    assert [c.word_count for c in first] == [300, 61]
    assert first[1].previous_overlap == 60 and first[1].start_word == 240
    assert first[0].text == text[first[0].start_char:first[0].end_char]
    assert first[1].text == text[first[1].start_char:first[1].end_char]
    assert first[0].text_sha256 == hashlib.sha256(first[0].text.encode()).hexdigest()


@pytest.mark.parametrize("count,expected", [(300, [300]), (301, [300, 61]), (50, [50])])
def test_chunker_boundaries(count, expected):
    chunks = chunk_document_v2(document_id="d", source_id="s", text=" ".join(f"w{i}" for i in range(count)), source_sha256=H)
    assert [x.word_count for x in chunks] == expected


def test_chunker_rejects_empty():
    with pytest.raises(ValueError, match="empty"):
        chunk_document_v2(document_id="d", source_id="s", text="", source_sha256=H)


def test_acquisition_retries_then_fails_without_fallback(monkeypatch):
    calls = 0
    def fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise TimeoutError("mock timeout")
    monkeypatch.setattr("src.ingestion.v2_pipeline.time.sleep", lambda _: None)
    with pytest.raises(AcquisitionError, match="after 3 attempts"):
        fetch_https("https://example.gov.in/a", opener=fail)
    assert calls == 3


def test_acquisition_accepts_complete_response():
    class Response:
        status = 200
        headers = Message()
        headers["Content-Type"] = "application/json"
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def read(self): return b"{}"
        def geturl(self): return "https://example.gov.in/final"
    result = fetch_https("https://example.gov.in/a", opener=lambda *a, **k: Response())
    assert (result.status, result.mime_type, result.body) == (200, "application/json", b"{}")
