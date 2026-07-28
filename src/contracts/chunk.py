"""Deterministic V2 chunk contract."""

from __future__ import annotations

from dataclasses import dataclass

from ._validation import require_schema, require_sha256, required_text, stable_dict


@dataclass(frozen=True)
class ChunkV2:
    schema_version: str
    chunk_id: str
    document_id: str
    source_id: str
    chunk_index: int
    start_word: int
    end_word: int
    word_count: int
    start_char: int
    end_char: int
    previous_overlap: int
    text: str
    text_sha256: str
    source_sha256: str
    corpus_version: str
    renderer_version: str
    chunker_version: str

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        for name in ("chunk_id", "document_id", "source_id", "text", "corpus_version", "renderer_version", "chunker_version"):
            required_text(name, getattr(self, name))
        require_sha256("text_sha256", self.text_sha256)
        require_sha256("source_sha256", self.source_sha256)
        if self.chunk_index < 0 or min(self.start_word, self.start_char) < 0:
            raise ValueError("chunk positions must be non-negative")
        if self.word_count != self.end_word - self.start_word or not 1 <= self.word_count <= 300:
            raise ValueError("word_count must match word range and be within 1..300")
        if self.end_char <= self.start_char or self.previous_overlap not in range(0, 61):
            raise ValueError("invalid character range or previous overlap")

    def to_dict(self) -> dict:
        return stable_dict(self)
