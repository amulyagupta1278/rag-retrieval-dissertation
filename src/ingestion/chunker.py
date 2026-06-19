"""
Chunker — Ingestion Layer
==========================
Research purpose
    Chunking granularity is one of the most significant ablation axes in RAG
    research. This module makes chunk_size and chunk_overlap explicit,
    configurable, and reproducible so ablation experiments can vary them
    systematically.

Design choice
    Sliding-window word-based chunking with sentence-boundary respect. Word
    tokens are simpler than sub-word tokens and give chunk sizes that are
    interpretable without a tokenizer dependency.

Alternative approaches
    Sentence-level chunking produces more semantically coherent units but
    yields variable-length chunks. Recursive character splitter (LangChain)
    is more popular but harder to reproduce exactly across library versions.

Expected strengths
    Configurable; preserves sentence boundaries; metadata lineage (doc_id,
    chunk_index, char offsets) allows tracing retrieved chunks back to source.

Expected weaknesses
    Word-counting approximates token count; for long documents with very few
    sentence boundaries a chunk may exceed the target.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Iterator

# Sentence boundary heuristic (handles abbreviations imperfectly but is
# sufficient for dissertation-quality chunking)
_SENT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Chunk:
    """Atomic retrieval unit with full provenance."""

    chunk_id: str
    doc_id: str
    text: str
    chunk_index: int       # 0-based position within parent document
    start_char: int
    end_char: int
    word_count: int
    source_path: str
    domain_tag: str
    section_title: str = ""
    extra_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "text": self.text,
            "chunk_index": self.chunk_index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "word_count": self.word_count,
            "source_path": self.source_path,
            "domain_tag": self.domain_tag,
            "section_title": self.section_title,
            "extra_meta": self.extra_meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Chunk":
        return cls(**d)


class Chunker:
    """
    Splits cleaned document text into overlapping sliding-window chunks.

    Parameters
    ----------
    chunk_size : int
        Target number of words per chunk.
    chunk_overlap : int
        Number of words shared between consecutive chunks.
    min_chunk_length : int
        Discard chunks with fewer characters than this threshold.
    respect_sentence_boundaries : bool
        If True, extend chunk endpoint to the nearest sentence boundary.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        min_chunk_length: int = 50,
        respect_sentence_boundaries: bool = True,
    ) -> None:
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_length = min_chunk_length
        self.respect_sentence_boundaries = respect_sentence_boundaries

    def chunk_document(
        self,
        doc_id: str,
        text: str,
        source_path: str,
        domain_tag: str,
        section_title: str = "",
        extra_meta: dict | None = None,
    ) -> list[Chunk]:
        """Return list of Chunk objects for *text*."""
        words = text.split()
        if not words:
            return []

        # Sentence start positions in word index (approximation)
        sentence_starts = self._find_sentence_starts(words) if self.respect_sentence_boundaries else set()

        chunks: list[Chunk] = []
        step = self.chunk_size - self.chunk_overlap
        idx = 0
        chunk_index = 0

        while idx < len(words):
            end = idx + self.chunk_size
            if self.respect_sentence_boundaries and end < len(words):
                # Advance end to the next sentence start to avoid cutting mid-sentence
                for candidate in range(end, min(end + 20, len(words))):
                    if candidate in sentence_starts:
                        end = candidate
                        break

            chunk_words = words[idx:end]
            chunk_text = " ".join(chunk_words)

            if len(chunk_text) >= self.min_chunk_length:
                # Char offsets (approximate — searching in original text)
                start_char = text.find(chunk_words[0]) if chunk_words else 0
                end_char = start_char + len(chunk_text)

                chunk_id = self._make_chunk_id(doc_id, chunk_index)
                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        text=chunk_text,
                        chunk_index=chunk_index,
                        start_char=start_char,
                        end_char=end_char,
                        word_count=len(chunk_words),
                        source_path=source_path,
                        domain_tag=domain_tag,
                        section_title=section_title,
                        extra_meta=extra_meta or {},
                    )
                )
                chunk_index += 1

            idx += step
            if idx >= len(words):
                break

        return chunks

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_sentence_starts(words: list[str]) -> set[int]:
        """Return word indices that likely start a new sentence."""
        starts = {0}
        for i, word in enumerate(words[:-1]):
            if word.endswith((".", "!", "?")):
                starts.add(i + 1)
        return starts

    @staticmethod
    def _make_chunk_id(doc_id: str, chunk_index: int) -> str:
        raw = f"{doc_id}_{chunk_index:05d}"
        digest = hashlib.md5(raw.encode()).hexdigest()[:8]
        return f"chunk_{digest}"
