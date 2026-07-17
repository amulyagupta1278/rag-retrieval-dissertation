"""Corpus v2 quality-control tests."""

import copy

import pytest

from src.ingestion.corpus_quality import (
    CorpusValidationError, canonicalize_url, deduplicate_documents,
    is_authoritative_url, jaccard_similarity, validate_catalog, validate_corpus,
    word_shingles,
)


def catalog_record(**overrides):
    record = {
        "catalog_id": "mohfw_scheme_faq", "document_id": "mohfw_scheme_faq",
        "source": "Ministry", "ministry": "Ministry of Health",
        "scheme_name": "Example Scheme", "publication_date": None,
        "url": "https://example.gov.in/scheme", "document_type": "faq",
        "format": "html", "language": "en", "scope": "central", "enabled": True,
    }
    record.update(overrides)
    return record


def document(identifier, text, **overrides):
    item = {
        "document_id": identifier, "doc_id": f"doc_{identifier}", "source": "Ministry",
        "ministry": "Ministry of Health", "scheme_name": "Scheme",
        "publication_date": None, "url": f"https://example.gov.in/{identifier}",
        "final_url": f"https://example.gov.in/{identifier}", "document_type": "faq",
        "source_type": "html", "sha256": identifier * 8, "cleaned_text": text,
    }
    item.update(overrides)
    return item


def test_catalog_schema_accepts_valid_record():
    validate_catalog([catalog_record()])


@pytest.mark.parametrize("change", [
    {"ministry": None}, {"scope": "state"}, {"language": "hi"},
    {"url": "https://example.com/scheme"}, {"catalog_id": "Not Stable"},
])
def test_catalog_rejects_invalid_records(change):
    record = catalog_record(**change)
    if change == {"ministry": None}:
        record.pop("ministry")
    with pytest.raises(CorpusValidationError):
        validate_catalog([record])


def test_authority_and_url_canonicalization():
    assert is_authoritative_url("https://labour.gov.in/FAQ-0")
    assert is_authoritative_url("https://www.mygov.in/page")
    assert not is_authoritative_url("http://labour.gov.in/page")
    assert not is_authoritative_url("https://government.example.com/page")
    assert canonicalize_url("HTTPS://EXAMPLE.GOV.IN/a//b/#fragment") == "https://example.gov.in/a/b"


def test_exact_raw_duplicate_is_removed_deterministically():
    text = "government welfare scheme eligibility benefit application " * 20
    first = document("first", text, sha256="same")
    second = document("second", text + "ignored", sha256="same")
    kept, report = deduplicate_documents([second, first])
    assert len(kept) == 1
    assert report[0]["method"] == "raw_sha256"


def test_near_duplicate_and_distinct_document():
    base = " ".join(f"benefit{i}" for i in range(200))
    near = base + " small addition"
    distinct = "application eligibility funding beneficiary procedure " * 40
    assert jaccard_similarity(word_shingles(base), word_shingles(near)) >= 0.95
    kept, report = deduplicate_documents([
        document("base", base), document("near", near), document("distinct", distinct)
    ])
    assert len(kept) == 2
    assert report[0]["method"] == "five_word_shingle_jaccard"


def test_corpus_lineage_validation_with_relaxed_fixture_bounds():
    doc = document("one", "scheme content " * 100)
    chunk = {
        "chunk_id": "chunk_one", "doc_id": doc["doc_id"], "text": "scheme content",
        "word_count": 2,
    }
    config = {"min_documents": 1, "max_documents": 2, "min_chunks": 1, "max_chunks": 2, "min_ministries": 1}
    docs = []
    types = ["scheme_description", "operational_guideline", "faq", "implementation_manual", "eligibility_beneficiary", "funding_guideline", "application_procedure"]
    chunks = []
    for index, dtype in enumerate(types):
        current = copy.deepcopy(doc)
        current.update(document(f"d{index}", f"content {index} " * 100, document_type=dtype))
        docs.append(current)
        chunks.append({"chunk_id": f"chunk_{index}", "doc_id": current["doc_id"], "text": "scheme content", "word_count": 2})
    config.update({"max_documents": 10, "max_chunks": 10})
    validate_corpus(docs, chunks, config)
