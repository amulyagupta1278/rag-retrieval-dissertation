"""Unit tests for the ingestion layer."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.ingestion.text_cleaner import TextCleaner, CleaningConfig
from src.ingestion.chunker import Chunker
from src.ingestion.metadata_enricher import MetadataEnricher


class TestTextCleaner:
    def test_unicode_normalisation(self):
        cleaner = TextCleaner(CleaningConfig(normalise_unicode=True))
        assert cleaner.clean("ﬁle") == "file"

    def test_removes_page_numbers(self):
        cleaner = TextCleaner(CleaningConfig(remove_boilerplate_lines=True))
        text = "Real content\nPage 3 of 10\nMore content"
        cleaned = cleaner.clean(text)
        assert "Page 3" not in cleaned
        assert "Real content" in cleaned

    def test_collapses_whitespace(self):
        cleaner = TextCleaner()
        text = "A\n\n\n\n\nB"
        cleaned = cleaner.clean(text)
        assert "\n\n\n" not in cleaned


class TestChunker:
    def test_basic_chunking(self):
        chunker = Chunker(chunk_size=10, chunk_overlap=2, min_chunk_length=1)
        text = " ".join(f"word{i}" for i in range(30))
        chunks = chunker.chunk_document("doc1", text, "/tmp/test.txt", "test")
        assert len(chunks) > 1

    def test_chunk_ids_unique(self):
        chunker = Chunker(chunk_size=10, chunk_overlap=2, min_chunk_length=1)
        text = " ".join(f"word{i}" for i in range(50))
        chunks = chunker.chunk_document("doc1", text, "/tmp/test.txt", "test")
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_overlap_creates_continuity(self):
        chunker = Chunker(chunk_size=10, chunk_overlap=5, min_chunk_length=1)
        text = " ".join(f"w{i}" for i in range(25))
        chunks = chunker.chunk_document("doc1", text, "/tmp/test.txt", "test")
        # Each chunk should share words with the previous
        if len(chunks) >= 2:
            words_a = set(chunks[0].text.split())
            words_b = set(chunks[1].text.split())
            assert len(words_a & words_b) > 0

    def test_invalid_overlap_raises(self):
        with pytest.raises(ValueError):
            Chunker(chunk_size=5, chunk_overlap=10)

    def test_to_dict_roundtrip(self):
        chunker = Chunker(chunk_size=20, chunk_overlap=4, min_chunk_length=1)
        text = " ".join(f"token{i}" for i in range(25))
        chunks = chunker.chunk_document("doc_x", text, "/path/file.txt", "ir")
        for c in chunks:
            d = c.to_dict()
            assert d["doc_id"] == "doc_x"
            assert "chunk_id" in d


class TestMetadataEnricher:
    def test_adds_required_fields(self):
        enricher = MetadataEnricher()
        chunk = {"chunk_id": "c1", "doc_id": "d1", "text": "BM25 is a ranking function.", "word_count": 6}
        result = enricher.enrich(chunk)
        assert "domain_tags" in result
        assert "has_numbers" in result
        assert "sentence_count" in result
        assert "estimated_reading_time_s" in result

    def test_domain_tag_ir(self):
        enricher = MetadataEnricher()
        chunk = {"chunk_id": "c1", "doc_id": "d1", "text": "BM25 retrieval ranking recall precision", "word_count": 6}
        result = enricher.enrich(chunk)
        assert "information_retrieval" in result["domain_tags"]
