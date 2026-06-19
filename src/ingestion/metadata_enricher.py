"""
Metadata Enricher — Ingestion Layer
=====================================
Research purpose
    Rich metadata on every chunk enables post-hoc slice analysis: which
    domains, sections, or source types does each retriever cover or miss?
    This directly supports the query-type analysis required by the dissertation.

Design choice
    Stateless transformer that adds computed fields to existing chunk dicts
    without mutating the original dataclass instances (returns new dicts).

Alternative approaches
    Embedding-based topic classification would be more accurate but introduces
    a model dependency in the ingestion layer, making offline preprocessing
    heavier than necessary.

Expected strengths
    Zero external dependencies; fast; produces queryable metadata fields.

Expected weaknesses
    Keyword-based domain tagging is approximate; a more precise classifier
    would require labelled domain examples.
"""

from __future__ import annotations

import re
from typing import Any

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "information_retrieval": [
        "retrieval", "bm25", "faiss", "embedding", "indexing", "recall",
        "precision", "mrr", "ndcg", "ranking", "sparse", "dense",
    ],
    "machine_learning": [
        "neural", "transformer", "bert", "gpt", "fine-tuning", "attention",
        "gradient", "loss", "epoch", "training", "inference",
    ],
    "knowledge_graph": [
        "entity", "relation", "graph", "node", "edge", "ontology",
        "knowledge base", "triple", "subject", "predicate", "object",
    ],
    "nlp": [
        "tokenization", "parsing", "ner", "sentiment", "classification",
        "language model", "corpus", "annotation", "pos tagging",
    ],
}


class MetadataEnricher:
    """
    Adds computed metadata fields to chunk dicts.

    Fields added
    ------------
    estimated_reading_time_s : float
        Estimated reading time at 200 words per minute.
    domain_tags : list[str]
        Corpus sub-domains inferred from keyword matching.
    has_numbers : bool
        True if the chunk contains numeric data (useful for factoid queries).
    sentence_count : int
        Approximate sentence count.
    """

    def enrich(self, chunk_dict: dict[str, Any]) -> dict[str, Any]:
        """Return a new dict with additional metadata fields."""
        text: str = chunk_dict.get("text", "")
        word_count: int = chunk_dict.get("word_count", len(text.split()))

        enriched = dict(chunk_dict)
        enriched["estimated_reading_time_s"] = round(word_count / (200 / 60), 2)
        enriched["domain_tags"] = self._infer_domain_tags(text)
        enriched["has_numbers"] = bool(re.search(r"\d+", text))
        enriched["sentence_count"] = len(re.findall(r"[.!?]+", text))
        return enriched

    def enrich_batch(self, chunk_dicts: list[dict]) -> list[dict]:
        return [self.enrich(c) for c in chunk_dicts]

    # ------------------------------------------------------------------

    @staticmethod
    def _infer_domain_tags(text: str) -> list[str]:
        lower = text.lower()
        tags: list[str] = []
        for domain, keywords in _DOMAIN_KEYWORDS.items():
            if any(kw in lower for kw in keywords):
                tags.append(domain)
        return tags or ["general"]
