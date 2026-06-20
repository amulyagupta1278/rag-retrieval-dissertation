"""
QRels Builder — Benchmark Layer
=================================
Research purpose
    TREC-style qrels.tsv (query_id, 0, doc_id, relevance) is the standard
    format for computing MRR, Recall@k, and nDCG@k with off-the-shelf
    IR evaluation libraries. Producing this format makes the benchmark
    compatible with trec_eval and pytrec_eval.

Design choice
    Binary relevance (0/1) is used for mid-semester; graded relevance (0/1/2)
    can be added at the final semester when human annotation is available.

Alternative approaches
    BEIR benchmark format uses separate queries.jsonl + qrels.tsv; this
    implementation produces the same format for direct BEIR compatibility.

Expected strengths
    Machine-readable; compatible with standard IR evaluation toolkits;
    directly supports offline retrieval evaluation separate from generation.

Expected weaknesses
    Binary relevance may understate the advantage of partial-relevance
    retrievers; graded relevance would give a more nuanced nDCG@k signal.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from .qa_generator import QAItem

logger = logging.getLogger(__name__)


class QRelsBuilder:
    """Converts QAItem gold mappings to TREC qrels and evidence map formats."""

    @staticmethod
    def build_qrels(items: list[QAItem]) -> list[tuple[str, str, int]]:
        """
        Return (query_id, chunk_id, relevance) triples.

        All gold evidence chunks receive relevance=1. Non-listed chunks are
        implicitly relevance=0 (standard TREC convention).
        """
        qrels: list[tuple[str, str, int]] = []
        for item in items:
            for chunk_id in item.gold_evidence_ids:
                qrels.append((item.question_id, chunk_id, 1))
        return qrels

    @staticmethod
    def save_qrels_tsv(qrels: list[tuple[str, str, int]], path: str | Path) -> None:
        """Write TREC-format qrels: query_id 0 doc_id relevance."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for qid, did, rel in qrels:
                fh.write(f"{qid}\t0\t{did}\t{rel}\n")
        logger.info("Saved qrels.tsv → %s (%d entries)", p, len(qrels))

    @staticmethod
    def load_qrels_tsv(path: str | Path) -> dict[str, dict[str, int]]:
        """Load qrels.tsv → {query_id: {doc_id: relevance}}."""
        qrels: dict[str, dict[str, int]] = {}
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split("\t")
                if len(parts) != 4:
                    continue
                qid, _, did, rel = parts
                try:
                    qrels.setdefault(qid, {})[did] = int(rel)
                except ValueError:
                    continue
        return qrels

    @staticmethod
    def save_evidence_map(items: list[QAItem], path: str | Path) -> None:
        """Write a human-readable evidence map JSON."""
        evidence_map = {
            item.question_id: {
                "question": item.question,
                "gold_evidence_ids": item.gold_evidence_ids,
                "source_doc_ids": item.source_doc_ids,
                "category": item.category,
                "difficulty": item.difficulty,
            }
            for item in items
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(evidence_map, indent=2), encoding="utf-8")
        logger.info("Saved evidence_map.json → %s", p)
