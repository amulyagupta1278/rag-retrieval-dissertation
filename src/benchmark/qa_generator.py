"""
QA Generator — Benchmark Layer
================================
Research purpose
    A stratified ground-truth QA dataset is the foundation of reproducible
    retrieval evaluation. Without gold evidence mappings, MRR, Recall@k, and
    nDCG@k cannot be computed. The benchmark directly operationalises H1–H5.

Design choice
    Template-based question generation from chunks combined with a manual
    review slot (the reviewed JSONL). Templates cover each query category
    defined in the dissertation: exact match, terminology-heavy, paraphrase,
    entity-relation, and multi-hop.

Alternative approaches
    LLM-based QA generation (e.g. GPT-4) produces more natural questions but
    introduces non-reproducible randomness and API cost. Template generation
    is auditable and free of external API dependencies at the mid-semester
    milestone.

Expected strengths
    Every generated item includes gold_evidence_ids enabling retrieval-layer
    evaluation (MRR/Recall@k/nDCG@k) independently of generation quality.

Expected weaknesses
    Template questions are more formulaic than human-written ones; diversity
    is limited by template coverage. The reviewed JSONL is the place to add
    manually written questions before the final submission.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

QUERY_CATEGORIES = [
    "exact_match",
    "terminology_heavy",
    "paraphrase",
    "entity_relation",
    "multi_hop",
]

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]


@dataclass
class QAItem:
    """A single benchmark question with gold evidence mapping."""

    question_id: str
    question: str
    category: str
    difficulty: str
    reference_answer: str
    gold_evidence_ids: list[str]
    source_doc_ids: list[str]
    split: str = "test"           # dev | test
    extra_meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "category": self.category,
            "difficulty": self.difficulty,
            "reference_answer": self.reference_answer,
            "gold_evidence_ids": self.gold_evidence_ids,
            "source_doc_ids": self.source_doc_ids,
            "split": self.split,
            "extra_meta": self.extra_meta,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QAItem":
        return cls(**d)


# ---------------------------------------------------------------------------
# Template factories
# ---------------------------------------------------------------------------

def _exact_match_templates(text: str, chunk_id: str, doc_id: str, qnum: int) -> list[QAItem]:
    """Extract noun-phrase definitions for exact-match questions."""
    items: list[QAItem] = []
    # Pattern: "X is defined as Y" or "X refers to Y"
    for m in re.finditer(
        r"([A-Z][a-zA-Z\s]{2,40})\s+(?:is|are|refers? to|denotes?)\s+([^.]{10,120})\.",
        text,
    ):
        term = m.group(1).strip()
        answer = m.group(2).strip()
        if len(term.split()) <= 5:
            qid = f"q_{qnum:04d}"
            items.append(
                QAItem(
                    question_id=qid,
                    question=f"What is {term}?",
                    category="exact_match",
                    difficulty="easy",
                    reference_answer=answer,
                    gold_evidence_ids=[chunk_id],
                    source_doc_ids=[doc_id],
                )
            )
            qnum += 1
            if len(items) >= 2:
                break
    return items


def _terminology_heavy_templates(text: str, chunk_id: str, doc_id: str, qnum: int) -> list[QAItem]:
    """Build questions around technical acronyms."""
    items: list[QAItem] = []
    for m in re.finditer(r"\b([A-Z]{2,6})\b", text):
        acronym = m.group(1)
        # Look for expansion nearby
        expansion_pat = re.compile(
            rf"{re.escape(acronym)}\s*[\(\[–-]\s*([A-Za-z\s]{{5,60}}?)[\)\]]",
        )
        exp_m = expansion_pat.search(text)
        if exp_m:
            qid = f"q_{qnum:04d}"
            items.append(
                QAItem(
                    question_id=qid,
                    question=f"What does {acronym} stand for?",
                    category="terminology_heavy",
                    difficulty="easy",
                    reference_answer=exp_m.group(1).strip(),
                    gold_evidence_ids=[chunk_id],
                    source_doc_ids=[doc_id],
                )
            )
            qnum += 1
            if len(items) >= 2:
                break
    return items


def _paraphrase_templates(text: str, chunk_id: str, doc_id: str, qnum: int) -> list[QAItem]:
    """Create questions whose surface form differs from the evidence text."""
    items: list[QAItem] = []
    sentences = [s.strip() for s in re.split(r"[.!?]", text) if len(s.strip()) > 40]
    for sent in sentences[:2]:
        words = sent.split()
        if len(words) < 6:
            continue
        # Take last 5 words as a paraphrased query cue
        tail = " ".join(words[-5:])
        qid = f"q_{qnum:04d}"
        items.append(
            QAItem(
                question_id=qid,
                question=f"What information is provided about '{tail}'?",
                category="paraphrase",
                difficulty="medium",
                reference_answer=sent,
                gold_evidence_ids=[chunk_id],
                source_doc_ids=[doc_id],
            )
        )
        qnum += 1
    return items[:1]


def _entity_relation_templates(text: str, chunk_id: str, doc_id: str, qnum: int) -> list[QAItem]:
    """Build who/how questions that require entity relation matching."""
    items: list[QAItem] = []
    # Pattern: "X improves/enables/causes Y"
    for m in re.finditer(
        r"([A-Z][a-zA-Z\s]{2,30})\s+(improves?|enables?|causes?|achieves?|outperforms?)\s+([a-zA-Z\s]{5,60})",
        text,
    ):
        subj, rel, obj = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        qid = f"q_{qnum:04d}"
        items.append(
            QAItem(
                question_id=qid,
                question=f"How does {subj} relate to {obj}?",
                category="entity_relation",
                difficulty="medium",
                reference_answer=f"{subj} {rel} {obj}.",
                gold_evidence_ids=[chunk_id],
                source_doc_ids=[doc_id],
            )
        )
        qnum += 1
        if len(items) >= 1:
            break
    return items


def _multi_hop_template(
    chunk_a: dict, chunk_b: dict, qnum: int
) -> Optional[QAItem]:
    """Create a question requiring evidence from two chunks."""
    words_a = chunk_a["text"].split()[:8]
    words_b = chunk_b["text"].split()[:8]
    if not words_a or not words_b:
        return None
    phrase_a = " ".join(words_a[:4])
    phrase_b = " ".join(words_b[:4])
    return QAItem(
        question_id=f"q_{qnum:04d}",
        question=f"How are '{phrase_a}' and '{phrase_b}' connected?",
        category="multi_hop",
        difficulty="hard",
        reference_answer=f"Evidence spans chunk {chunk_a['chunk_id']} and chunk {chunk_b['chunk_id']}.",
        gold_evidence_ids=[chunk_a["chunk_id"], chunk_b["chunk_id"]],
        source_doc_ids=list({chunk_a["doc_id"], chunk_b["doc_id"]}),
    )


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class QAGenerator:
    """
    Generates a stratified QA benchmark from a corpus of chunks.

    Parameters
    ----------
    seed : int
        Random seed for reproducible sampling.
    dev_ratio : float
        Fraction of items assigned to the dev split.
    """

    def __init__(self, seed: int = 42, dev_ratio: float = 0.2) -> None:
        self.seed = seed
        self.dev_ratio = dev_ratio
        random.seed(seed)

    def generate(self, chunks: list[dict], max_per_category: int = 20) -> list[QAItem]:
        """
        Generate QA items from *chunks*.

        Parameters
        ----------
        chunks : list[dict]
            Chunk dicts as produced by Chunker.to_dict().
        max_per_category : int
            Maximum items per query category.

        Returns
        -------
        list[QAItem]
        """
        all_items: list[QAItem] = []
        qnum = 1

        exact: list[QAItem] = []
        term: list[QAItem] = []
        para: list[QAItem] = []
        entrel: list[QAItem] = []
        multi: list[QAItem] = []

        shuffled = list(chunks)
        random.shuffle(shuffled)

        for chunk in shuffled:
            text = chunk.get("text", "")
            cid = chunk["chunk_id"]
            did = chunk["doc_id"]

            if len(exact) < max_per_category:
                items = _exact_match_templates(text, cid, did, qnum)
                exact.extend(items)
                qnum += len(items)

            if len(term) < max_per_category:
                items = _terminology_heavy_templates(text, cid, did, qnum)
                term.extend(items)
                qnum += len(items)

            if len(para) < max_per_category:
                items = _paraphrase_templates(text, cid, did, qnum)
                para.extend(items)
                qnum += len(items)

            if len(entrel) < max_per_category:
                items = _entity_relation_templates(text, cid, did, qnum)
                entrel.extend(items)
                qnum += len(items)

        # Multi-hop: pair consecutive chunks from different docs
        doc_ids = list({c["doc_id"] for c in chunks})
        if len(doc_ids) >= 2:
            for i in range(0, min(len(shuffled) - 1, max_per_category * 2), 2):
                if shuffled[i]["doc_id"] != shuffled[i + 1]["doc_id"]:
                    item = _multi_hop_template(shuffled[i], shuffled[i + 1], qnum)
                    if item and len(multi) < max_per_category:
                        multi.append(item)
                        qnum += 1

        all_items = (
            exact[:max_per_category]
            + term[:max_per_category]
            + para[:max_per_category]
            + entrel[:max_per_category]
            + multi[:max_per_category]
        )

        # Assign splits
        random.shuffle(all_items)
        dev_count = max(1, int(len(all_items) * self.dev_ratio))
        for i, item in enumerate(all_items):
            item.split = "dev" if i < dev_count else "test"

        logger.info(
            "Generated %d QA items (exact=%d, term=%d, para=%d, entrel=%d, multi=%d)",
            len(all_items),
            len(exact),
            len(term),
            len(para),
            len(entrel),
            len(multi),
        )
        return all_items

    # ------------------------------------------------------------------
    # I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def save(items: list[QAItem], path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item.to_dict()) + "\n")
        logger.info("Saved %d QA items → %s", len(items), p)

    @staticmethod
    def load(path: str | Path) -> list[QAItem]:
        p = Path(path)
        items: list[QAItem] = []
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    items.append(QAItem.from_dict(json.loads(line)))
        return items
