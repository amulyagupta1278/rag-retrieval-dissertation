"""Extracted document and corpus contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ._validation import require_schema, require_sha256, require_unique, required_text, stable_dict


@dataclass(frozen=True)
class ExtractedDocument:
    schema_version: str
    document_id: str
    source_id: str
    scheme_id: str
    title: str
    ministry: str
    department: str
    text: str
    text_sha256: str
    source_sha256: str
    renderer_version: str
    extraction_status: str
    validation_status: str
    page_count: int | None = None
    pages_extracted: int | None = None
    empty_page_count: int | None = None
    extraction_warnings: tuple[str, ...] = ()
    ocr_used: bool = False

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        for name in ("document_id", "source_id", "scheme_id", "title", "ministry", "text", "renderer_version"):
            required_text(name, getattr(self, name))
        require_sha256("text_sha256", self.text_sha256)
        require_sha256("source_sha256", self.source_sha256)
        if self.extraction_status != "complete" or self.validation_status != "valid":
            raise ValueError("extracted document must be complete and valid")
        pdf_counts = (self.page_count, self.pages_extracted, self.empty_page_count)
        if any(v is not None for v in pdf_counts):
            if any(type(v) is not int or v < 0 for v in pdf_counts):
                raise ValueError("PDF page counts must all be non-negative integers")
            if self.pages_extracted + self.empty_page_count != self.page_count:
                raise ValueError("PDF extracted plus empty pages must equal page count")

    def to_dict(self) -> dict:
        return stable_dict(self)


@dataclass(frozen=True)
class CorpusManifest:
    schema_version: str
    corpus_version: str
    created_at: str
    document_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    document_count: int
    ministry_count: int

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        required_text("corpus_version", self.corpus_version)
        required_text("created_at", self.created_at)
        require_unique("document_ids", self.document_ids)
        require_unique("source_ids", self.source_ids)
        if not 20 <= self.document_count <= 25:
            raise ValueError("pilot corpus must contain 20 through 25 documents")
        if self.document_count != len(self.document_ids) or self.document_count != len(self.source_ids):
            raise ValueError("corpus counts and ID collections disagree")
        if self.ministry_count < 4:
            raise ValueError("pilot corpus must cover at least four ministries")

    def to_dict(self) -> dict:
        return stable_dict(self)
