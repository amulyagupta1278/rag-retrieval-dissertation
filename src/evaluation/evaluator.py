"""
Retrieval Evaluator — Evaluation Layer
=========================================
Research purpose
    Orchestrates the full evaluation pipeline: loads runs, loads qrels,
    computes metrics per retriever and per query category, and outputs
    structured MetricBundles for the report generator.

Design choice
    Stateless class that operates on serialised run files so evaluation
    can be re-run offline without re-running retrievers. This mirrors the
    Pyserini pattern of separating retrieval from evaluation.

Alternative approaches
    Online evaluation (evaluate during retrieval) is simpler but prevents
    re-running evaluation with different qrels or metrics without re-running
    retrieval, which is expensive for FAISS and entity-co-occurrence graph retrieval.

Expected strengths
    Reproducible; separates retrieval cost from evaluation cost; supports
    sliced analysis by query category.

Expected weaknesses
    Run files can be large for many queries × many retrievers; at
    dissertation scale this is not a practical concern.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from .metrics import MetricBundle, compute_all_metrics
from ..benchmark.qrels_builder import QRelsBuilder

logger = logging.getLogger(__name__)


class RetrievalEvaluator:
    """
    Evaluates serialised retrieval runs against qrels.

    Parameters
    ----------
    qrels_path : str | Path
        Path to qrels.tsv.
    query_categories_path : str | Path | None
        Path to query_categories.json ({question_id: category_str}).
    k_values : list[int]
        k thresholds to compute metrics at.
    """

    def __init__(
        self,
        qrels_path: str | Path,
        query_categories_path: str | Path | None = None,
        k_values: list[int] | None = None,
        qa_dataset_path: str | Path | None = None,
        split: str | None = None,
    ) -> None:
        self.qrels = QRelsBuilder.load_qrels_tsv(qrels_path)
        self.k_values = k_values or [1, 3, 5, 10]
        self.query_categories: dict[str, str] = {}
        self.allowed_query_ids: set[str] | None = None
        if split and split != "all":
            if not qa_dataset_path:
                raise ValueError("qa_dataset_path is required when filtering by split")
            qa_items = [
                json.loads(line) for line in Path(qa_dataset_path).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.allowed_query_ids = {
                item["question_id"] for item in qa_items if item.get("split") == split
            }
            if not self.allowed_query_ids:
                raise ValueError(f"No queries found for split={split}")
            self.qrels = {qid: value for qid, value in self.qrels.items() if qid in self.allowed_query_ids}
        if query_categories_path:
            p = Path(query_categories_path)
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                self.query_categories = {qid: v["category"] for qid, v in data.items()}

    def evaluate_run_file(
        self,
        run_file_path: str | Path,
        retriever_name: str | None = None,
    ) -> list[MetricBundle]:
        """
        Evaluate one JSONL run file and return MetricBundles (aggregate + per-category).

        Parameters
        ----------
        run_file_path : str | Path
            JSONL file where each line is a RetrievalRun.to_dict().
        retriever_name : str | None
            Override retriever name; if None, inferred from first run line.
        """
        p = Path(run_file_path)
        runs: list[dict] = []
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    runs.append(json.loads(line))

        if not runs:
            logger.warning("Empty run file: %s", p)
            return []

        if self.allowed_query_ids is not None:
            runs = [run for run in runs if run.get("query_id") in self.allowed_query_ids]
            if not runs:
                raise ValueError("Run contains no queries from the selected split")

        ret_name = retriever_name or runs[0].get("retriever", "unknown")

        # Aggregate
        bundles: list[MetricBundle] = [
            compute_all_metrics(
                runs=runs,
                qrels=self.qrels,
                k_values=self.k_values,
                retriever=ret_name,
                query_category="all",
            )
        ]

        # Per-category slices
        if self.query_categories:
            cat_runs: dict[str, list[dict]] = {}
            for run in runs:
                cat = self.query_categories.get(run["query_id"], "unknown")
                cat_runs.setdefault(cat, []).append(run)

            for cat, cat_run_list in cat_runs.items():
                bundles.append(
                    compute_all_metrics(
                        runs=cat_run_list,
                        qrels=self.qrels,
                        k_values=self.k_values,
                        retriever=ret_name,
                        query_category=cat,
                    )
                )

        logger.info(
            "Evaluated %s: %d queries, %d category slices",
            ret_name,
            len(runs),
            len(bundles),
        )
        return bundles

    def save_metrics_csv(self, bundles: list[MetricBundle], path: str | Path) -> None:
        """Write all MetricBundles to a flat CSV suitable for spreadsheet analysis."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if not bundles:
            return

        k_values = list(bundles[0].recall_at_k.keys())
        headers = (
            ["retriever", "query_category", "num_queries", "mrr", "avg_latency_ms"]
            + [f"mrr@{k}" for k in k_values]
            + [f"recall@{k}" for k in k_values]
            + [f"ndcg@{k}" for k in k_values]
            + [f"precision@{k}" for k in k_values]
        )

        with p.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=headers, lineterminator="\n")
            writer.writeheader()
            for b in bundles:
                row: dict = {
                    "retriever": b.retriever,
                    "query_category": b.query_category,
                    "num_queries": b.num_queries,
                    "mrr": round(b.mrr, 4),
                    "avg_latency_ms": round(b.avg_latency_ms, 2),
                }
                for k in k_values:
                    row[f"mrr@{k}"] = round(b.mrr_at_k.get(k, 0.0), 4)
                    row[f"recall@{k}"] = round(b.recall_at_k.get(k, 0.0), 4)
                    row[f"ndcg@{k}"] = round(b.ndcg_at_k.get(k, 0.0), 4)
                    row[f"precision@{k}"] = round(b.precision_at_k.get(k, 0.0), 4)
                writer.writerow(row)

        logger.info("Metrics CSV saved → %s (%d rows)", p, len(bundles))
