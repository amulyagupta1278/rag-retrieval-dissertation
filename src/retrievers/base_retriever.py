"""
Base Retriever — Retrieval Layer
==================================
Research purpose
    A shared abstract interface guarantees that every retriever plugs into the
    same evaluation harness without bespoke adapter code. This mirrors the
    design principle from the blueprint: "all retrievers conform to the same
    interface, return ranked evidence in a normalized format."

Design choice
    Python ABC with a typed retrieve() method. RetrievalResult carries the
    chunk text, score, rank, and latency so the evaluator never needs to
    re-query the retriever.

Alternative approaches
    LangChain's BaseRetriever is popular but couples retrieval to the
    generation chain. Keeping the interface independent lets the evaluation
    layer assess retrieval quality before any generation happens.

Expected strengths
    Plug-in architecture; adding a new retriever only requires implementing
    two methods (build_index / retrieve).

Expected weaknesses
    The interface assumes single-query-at-a-time retrieval; batch evaluation
    is done by calling retrieve() in a loop, which is acceptable at
    dissertation scale.
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RetrievalResult:
    """Single ranked evidence item returned by a retriever."""

    chunk_id: str
    doc_id: str
    text: str
    score: float
    rank: int           # 1-based
    latency_ms: float   # time attributed to this query
    retriever: str
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "text": self.text,
            "score": self.score,
            "rank": self.rank,
            "latency_ms": self.latency_ms,
            "retriever": self.retriever,
            "extra": self.extra,
        }


@dataclass
class RetrievalRun:
    """
    Complete output of a retrieval experiment for one query.

    This is the TREC run-file analogue serialised as JSONL.
    """

    query_id: str
    query_text: str
    retriever: str
    top_k: int
    results: list[RetrievalResult]
    total_latency_ms: float
    config_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query_id": self.query_id,
            "query_text": self.query_text,
            "retriever": self.retriever,
            "top_k": self.top_k,
            "results": [r.to_dict() for r in self.results],
            "total_latency_ms": self.total_latency_ms,
            "config_snapshot": self.config_snapshot,
        }

    @staticmethod
    def save_run_file(runs: list["RetrievalRun"], path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as fh:
            for run in runs:
                fh.write(json.dumps(run.to_dict()) + "\n")

    @staticmethod
    def load_run_file(path: str | Path) -> list["RetrievalRun"]:
        runs: list[RetrievalRun] = []
        with Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                results = [RetrievalResult(**r) for r in d.pop("results")]
                runs.append(RetrievalRun(**d, results=results))
        return runs


class BaseRetriever(ABC):
    """Abstract base for all dissertation retrievers."""

    name: str = "base"

    @abstractmethod
    def build_index(self, chunks: list[dict]) -> None:
        """Build or load the retrieval index from *chunks*."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 10) -> list[RetrievalResult]:
        """Return top_k ranked RetrievalResult objects for *query*."""

    def retrieve_timed(self, query: str, top_k: int = 10) -> tuple[list[RetrievalResult], float]:
        """Wrapper that measures wall-clock retrieval latency."""
        t0 = time.perf_counter()
        results = self.retrieve(query, top_k=top_k)
        latency_ms = (time.perf_counter() - t0) * 1000
        for r in results:
            r.latency_ms = latency_ms / max(len(results), 1)
        return results, latency_ms

    def run_benchmark(
        self,
        qa_items: list[dict],
        top_k: int = 10,
        config_snapshot: Optional[dict] = None,
    ) -> list[RetrievalRun]:
        """
        Run retrieval for every QA item and return a list of RetrievalRun.

        Parameters
        ----------
        qa_items : list[dict]
            Each dict must have 'question_id' and 'question' keys.
        top_k : int
            Retrieval budget per query.
        config_snapshot : dict | None
            Config dict written into each run for reproducibility.
        """
        runs: list[RetrievalRun] = []
        for item in qa_items:
            qid = item["question_id"]
            query = item["question"]
            results, latency = self.retrieve_timed(query, top_k=top_k)
            runs.append(
                RetrievalRun(
                    query_id=qid,
                    query_text=query,
                    retriever=self.name,
                    top_k=top_k,
                    results=results,
                    total_latency_ms=latency,
                    config_snapshot=config_snapshot or {},
                )
            )
        return runs
