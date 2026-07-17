"""
Query Categorizer — Benchmark Layer
=====================================
Research purpose
    Per-category metric breakdowns are what elevate this dissertation above
    a standard average-score comparison. The categorizer assigns each query
    to one of five categories so that results tables can show, for example,
    that BM25 leads on exact_match while Entity-Co-occurrence Graph Retrieval leads on multi_hop.

Design choice
    Heuristic rule-based categorizer operating on question surface form.
    Fast and fully deterministic; no model weights required.

Alternative approaches
    Fine-tuned classifier would be more robust but requires labelled data
    and is not justified for a 50–100 item benchmark.

Expected strengths
    Deterministic; easy to inspect and correct; directly emits the five
    dissertation query categories.

Expected weaknesses
    Heuristic classification may mis-categorise borderline questions;
    manual override via the reviewed QA JSONL is the recommended correction path.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class QueryCategory(str, Enum):
    EXACT_MATCH = "exact_match"
    TERMINOLOGY_HEAVY = "terminology_heavy"
    PARAPHRASE = "paraphrase"
    ENTITY_RELATION = "entity_relation"
    MULTI_HOP = "multi_hop"
    UNKNOWN = "unknown"


# Priority-ordered rules; first match wins
_RULES: list[tuple[re.Pattern, QueryCategory]] = [
    (re.compile(r"\b(what does|stand for|acronym|abbreviation)\b", re.I), QueryCategory.TERMINOLOGY_HEAVY),
    (re.compile(r"\b(how (are|does|do|is)|relation|connect|link|between)\b", re.I), QueryCategory.ENTITY_RELATION),
    (re.compile(r"\b(and|both|as well as|together with)\b.*\?", re.I), QueryCategory.MULTI_HOP),
    (re.compile(r"\b(what|who|when|where|which|define|definition)\b", re.I), QueryCategory.EXACT_MATCH),
    (re.compile(r"\b(information|describe|explain|tell me about)\b", re.I), QueryCategory.PARAPHRASE),
]


@dataclass
class CategorizedQuery:
    question_id: str
    question: str
    category: QueryCategory
    confidence: str   # "rule" | "fallback"


class QueryCategorizer:
    """
    Assigns a QueryCategory to each question in the benchmark.
    """

    def categorize(self, question: str) -> QueryCategory:
        for pattern, category in _RULES:
            if pattern.search(question):
                return category
        return QueryCategory.UNKNOWN

    def categorize_dataset(self, qa_items: list[dict]) -> list[CategorizedQuery]:
        """
        Categorize all items in *qa_items*.

        Parameters
        ----------
        qa_items : list[dict]
            Each dict must have "question_id" and "question" keys.

        Returns
        -------
        list[CategorizedQuery]
        """
        results: list[CategorizedQuery] = []
        for item in qa_items:
            qid = item["question_id"]
            question = item["question"]
            # Prefer stored category if it exists and is not "unknown"
            stored = item.get("category", "unknown")
            if stored and stored != "unknown":
                cat = QueryCategory(stored)
                confidence = "stored"
            else:
                cat = self.categorize(question)
                confidence = "rule" if cat != QueryCategory.UNKNOWN else "fallback"
            results.append(
                CategorizedQuery(
                    question_id=qid,
                    question=question,
                    category=cat,
                    confidence=confidence,
                )
            )
        return results

    @staticmethod
    def save(categorized: list[CategorizedQuery], path: str | Path) -> None:
        output = {
            item.question_id: {
                "question": item.question,
                "category": item.category.value,
                "confidence": item.confidence,
            }
            for item in categorized
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(output, indent=2), encoding="utf-8")
        logger.info("Saved query_categories.json → %s (%d queries)", p, len(categorized))

    @staticmethod
    def load(path: str | Path) -> dict[str, str]:
        """Return {question_id: category_str}."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return {qid: v["category"] for qid, v in data.items()}
