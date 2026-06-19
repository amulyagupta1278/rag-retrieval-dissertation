"""
Retrieval Metrics — Evaluation Layer
=======================================
Research purpose
    Quantifies retrieval quality independently of generation quality.
    MRR, Recall@k, nDCG@k, and Precision@k are the standard IR metrics for
    evaluating ranked retrieval against a gold relevance judgement set.

Design choice
    Pure-Python implementation with no external evaluation library dependency.
    This keeps the metrics auditable and makes the computation path transparent
    for the dissertation's methods section. Results are cross-validated against
    pytrec_eval where available.

Alternative approaches
    pytrec_eval wraps trec_eval (C) and is the gold standard for IR evaluation.
    It can be added as an optional dependency; this module's results should agree
    with pytrec_eval for binary relevance.

Expected strengths
    Computes per-query and aggregate metrics; supports multiple k values
    simultaneously; returns structured MetricBundle for downstream reporting.

Expected weaknesses
    Graded relevance (0/1/2) requires extending the relevance judgements;
    only binary relevance is supported at the mid-semester milestone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class MetricBundle:
    """Container for all computed metrics for one (retriever, query_category) slice."""

    retriever: str
    query_category: str           # "all" for aggregate
    num_queries: int
    mrr: float
    recall_at_k: dict[int, float]   # k → recall
    ndcg_at_k: dict[int, float]
    precision_at_k: dict[int, float]
    avg_latency_ms: float
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "retriever": self.retriever,
            "query_category": self.query_category,
            "num_queries": self.num_queries,
            "mrr": round(self.mrr, 4),
            "recall_at_k": {str(k): round(v, 4) for k, v in self.recall_at_k.items()},
            "ndcg_at_k": {str(k): round(v, 4) for k, v in self.ndcg_at_k.items()},
            "precision_at_k": {str(k): round(v, 4) for k, v in self.precision_at_k.items()},
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "extra": self.extra,
        }


# ---------------------------------------------------------------------------
# Per-query metric functions
# ---------------------------------------------------------------------------

def compute_mrr(ranked_ids: list[str], gold_ids: set[str]) -> float:
    """Mean Reciprocal Rank for a single query (returns 0.0 if no gold retrieved)."""
    for rank, chunk_id in enumerate(ranked_ids, start=1):
        if chunk_id in gold_ids:
            return 1.0 / rank
    return 0.0


def compute_recall_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    """Recall@k: fraction of gold chunks retrieved in the top-k."""
    if not gold_ids:
        return 0.0
    retrieved = set(ranked_ids[:k])
    return len(retrieved & gold_ids) / len(gold_ids)


def compute_precision_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    """Precision@k: fraction of top-k retrieved chunks that are relevant."""
    if k == 0:
        return 0.0
    retrieved = ranked_ids[:k]
    return sum(1 for cid in retrieved if cid in gold_ids) / k


def compute_ndcg_at_k(ranked_ids: list[str], gold_ids: set[str], k: int) -> float:
    """
    nDCG@k with binary relevance.

    DCG = Σ rel_i / log2(i+1)  for i in 1..k
    Ideal DCG assumes all gold chunks are at the top.
    """
    dcg = 0.0
    for i, chunk_id in enumerate(ranked_ids[:k], start=1):
        if chunk_id in gold_ids:
            dcg += 1.0 / math.log2(i + 1)

    # Ideal DCG: min(|gold|, k) relevant items at positions 1..k
    ideal_hits = min(len(gold_ids), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))

    return dcg / idcg if idcg > 0 else 0.0


# ---------------------------------------------------------------------------
# Aggregate function
# ---------------------------------------------------------------------------

def compute_all_metrics(
    runs: list[dict],
    qrels: dict[str, dict[str, int]],
    k_values: Sequence[int] = (1, 3, 5, 10),
    retriever: str = "unknown",
    query_category: str = "all",
    latencies_ms: list[float] | None = None,
) -> MetricBundle:
    """
    Compute aggregate metrics over a list of retrieval runs.

    Parameters
    ----------
    runs : list[dict]
        Each dict is a RetrievalRun.to_dict() output with 'query_id' and
        'results' (list of RetrievalResult dicts with 'chunk_id').
    qrels : dict
        {query_id: {chunk_id: relevance}} as loaded from qrels.tsv.
    k_values : Sequence[int]
        Which k thresholds to compute metrics at.
    retriever : str
        Name written into the MetricBundle.
    query_category : str
        Category label for sliced reporting.
    latencies_ms : list[float] | None
        Per-query latencies; if None extracted from run total_latency_ms.
    """
    mrr_scores: list[float] = []
    recall_scores: dict[int, list[float]] = {k: [] for k in k_values}
    ndcg_scores: dict[int, list[float]] = {k: [] for k in k_values}
    prec_scores: dict[int, list[float]] = {k: [] for k in k_values}
    lat_list: list[float] = []

    for i, run in enumerate(runs):
        qid = run["query_id"]
        gold_ids = set(qrels.get(qid, {}).keys())
        ranked_ids = [r["chunk_id"] for r in run.get("results", [])]

        mrr_scores.append(compute_mrr(ranked_ids, gold_ids))
        for k in k_values:
            recall_scores[k].append(compute_recall_at_k(ranked_ids, gold_ids, k))
            ndcg_scores[k].append(compute_ndcg_at_k(ranked_ids, gold_ids, k))
            prec_scores[k].append(compute_precision_at_k(ranked_ids, gold_ids, k))

        if latencies_ms:
            lat_list.append(latencies_ms[i])
        else:
            lat_list.append(run.get("total_latency_ms", 0.0))

    n = max(len(runs), 1)

    def _avg(lst: list[float]) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    return MetricBundle(
        retriever=retriever,
        query_category=query_category,
        num_queries=n,
        mrr=_avg(mrr_scores),
        recall_at_k={k: _avg(recall_scores[k]) for k in k_values},
        ndcg_at_k={k: _avg(ndcg_scores[k]) for k in k_values},
        precision_at_k={k: _avg(prec_scores[k]) for k in k_values},
        avg_latency_ms=_avg(lat_list),
    )
