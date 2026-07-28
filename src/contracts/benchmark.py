"""Reviewed QA draft and graded qrels contracts."""

from __future__ import annotations

from dataclasses import dataclass

from ._validation import require_schema, require_unique, required_text, stable_dict

CATEGORIES = {"exact_lookup", "terminology", "paraphrase", "entity_relation", "multi_hop", "synthesis"}


@dataclass(frozen=True)
class QAItemV2:
    schema_version: str
    question_id: str
    benchmark_version: str
    category: str
    difficulty: str
    question: str
    reference_answer: str
    gold_evidence_ids: tuple[str, ...]
    source_document_ids: tuple[str, ...]
    supporting_evidence_quotes: tuple[str, ...]
    authoring_method: str
    review_status: str
    review_revision: int
    split: str
    notes: str
    bridge_entity: str = ""

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        for name in ("question_id", "benchmark_version", "difficulty", "question", "reference_answer", "authoring_method", "review_status", "split"):
            required_text(name, getattr(self, name))
        if self.category not in CATEGORIES:
            raise ValueError(f"unsupported QA category: {self.category!r}")
        require_unique("gold_evidence_ids", self.gold_evidence_ids)
        require_unique("source_document_ids", self.source_document_ids)
        if not self.gold_evidence_ids or len(self.supporting_evidence_quotes) != len(self.gold_evidence_ids):
            raise ValueError("each QA item needs one evidence quote per gold chunk")
        if self.review_revision < 0 or self.split not in {"dev", "test"}:
            raise ValueError("invalid review revision or split")
        if self.category == "multi_hop" and (len(self.gold_evidence_ids) < 2 or not self.bridge_entity.strip()):
            raise ValueError("multi-hop item needs at least two chunks and bridge_entity")
        if self.category == "synthesis" and len(self.gold_evidence_ids) < 3:
            raise ValueError("synthesis item needs at least three chunks")

    def to_dict(self) -> dict:
        return stable_dict(self)


@dataclass(frozen=True)
class QrelsJudgment:
    schema_version: str
    query_id: str
    chunk_id: str
    relevance: int
    judgment_source: str
    review_status: str
    reviewer_notes: str

    def __post_init__(self) -> None:
        require_schema(self.schema_version)
        for name in ("query_id", "chunk_id", "judgment_source", "review_status"):
            required_text(name, getattr(self, name))
        if type(self.relevance) is not int or self.relevance not in {0, 1, 2}:
            raise ValueError("relevance must be integer 0, 1, or 2")
        if self.relevance == 0 and self.review_status != "reviewed":
            raise ValueError("grade-0 judgment requires explicit review")

    def to_dict(self) -> dict:
        return stable_dict(self)
